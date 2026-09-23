"""Offline TF-IDF metric-phrase baseline; its output never becomes SQL."""
import hashlib
import json
import warnings
import platform
from collections import Counter, defaultdict

import numpy as np
import sklearn
from rapidfuzz.fuzz import ratio
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.exceptions import ConvergenceWarning

from api.sports_query import METRICS, normalize

CONTEXT_PHRASES = {'kit colour':'kit_colour','kit color':'kit_colour','shirt colour':'kit_colour',
    'shirt color':'kit_colour','historical weather':'historical_weather','kickoff temperature':'historical_weather'}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',',':'))


def prepare(rows):
    if not rows:
        raise ValueError('No human-verified latest annotations. Review examples in Training first.')
    if len(rows)>10000:
        raise ValueError('Pilot is limited to 10000 examples; use a separately budgeted training job for larger datasets.')
    families, phrases, phrase_families, labels = {}, {}, {}, defaultdict(set)
    for row in rows:
        if not row.get('reviewed_by') or not row.get('reviewed_at'):
            raise ValueError('Training accepts human-verified annotations only')
        split = row['split']
        if split not in ('train','validation','test'):
            raise ValueError('Unknown split')
        family, phrase = row['family_key'], normalize(row['phrase'])
        if family in families and families[family] != split:
            raise ValueError('A paraphrase family crosses dataset splits')
        families[family] = split
        if phrase in phrases and phrases[phrase] != (split,row['label']):
            raise ValueError('Duplicate phrase has conflicting labels or crosses dataset splits')
        if phrase in phrase_families and phrase_families[phrase] != family:
            raise ValueError('Duplicate phrases must share a paraphrase family')
        phrase_families[phrase] = family
        phrases[phrase] = (split,row['label'])
        labels[row['label']].add((family,split))
    if len(labels)<2:
        raise ValueError('At least two labels are required')
    for label, membership in labels.items():
        counts = Counter(split for _,split in membership)
        if counts['train']<2 or counts['validation']<1 or counts['test']<1:
            raise ValueError(f'{label}: need two training families, one validation family and one test family')
    # Catch trivial paraphrase leakage in addition to explicit family ownership.
    ordered = sorted(phrases)
    if len(ordered)>2000:
        raise ValueError('Pilot supports at most 2000 distinct phrases for leakage review')
    for index,a in enumerate(ordered):
        for b in ordered[index+1:]:
            if phrases[a][0]!=phrases[b][0] and ratio(a,b)>=90:
                raise ValueError(f'Near-duplicate phrases cross splits: {a!r} / {b!r}; group and re-review them')
    return sorted(rows,key=lambda row:str(row['annotation_id']))


def train(rows):
    rows = prepare(rows)
    corpus = [{k:str(v) if k in ('annotation_id','example_id','reviewed_at') else v for k,v in row.items()} for row in rows]
    unique = {}
    for row in rows:
        unique.setdefault((normalize(row['phrase']),row['label'],row['split']),row)
    splits = {s:[r for r in unique.values() if r['split']==s] for s in ('train','validation','test')}
    vectorizer = TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),max_features=6000,sublinear_tf=True)
    features = vectorizer.fit_transform([normalize(r['phrase']) for r in splits['train']])
    classifier = LogisticRegression(C=1.0,max_iter=1000,random_state=42,class_weight='balanced')
    with warnings.catch_warnings():
        warnings.simplefilter('error',ConvergenceWarning)
        try:
            classifier.fit(features,[r['label'] for r in splits['train']])
        except ConvergenceWarning as error:
            raise ValueError('Classifier did not converge; no model was registered') from error
    classes = classifier.classes_.tolist()
    report = {'scope':'metric_phrase_classification_only', 'deployed':False,
              'duplicate_phrases_removed':len(rows)-len(unique),
              'warning':'Small human-labelled pilot; not full-query accuracy or a calibrated confidence estimate.',
              'counts':{s:len(values) for s,values in splits.items()}, 'classes':classes}
    for split in ('validation','test'):
        actual = [r['label'] for r in splits[split]]
        predicted = classifier.predict(vectorizer.transform([normalize(r['phrase']) for r in splits[split]])).tolist()
        report[split] = {'accuracy':accuracy_score(actual,predicted),
            'exact_metric_dictionary_accuracy':accuracy_score(actual,[METRICS.get(normalize(r['phrase']),'unsupported') for r in splits[split]]),
            'classification':classification_report(actual,predicted,labels=classes,output_dict=True,zero_division=0),
            'confusion_matrix':confusion_matrix(actual,predicted,labels=classes).tolist(),
            'predictions':[{'annotation_id':str(r['annotation_id']),'expected':a,'predicted':p} for r,a,p in zip(splits[split],actual,predicted)]}
    artifact = {'format':'points-metric-tfidf-v1','classes':classes,
        'vocabulary':{k:int(v) for k,v in vectorizer.vocabulary_.items()},'idf':vectorizer.idf_.tolist(),
        'coef':classifier.coef_.tolist(),'intercept':classifier.intercept_.tolist()}
    digest = hashlib.sha256(canonical(corpus).encode()).hexdigest()
    manifest = {'scope':'metric_phrase_only','schema_version':1,'sklearn_version':sklearn.__version__,
        'python_version':platform.python_version(),'numpy_version':np.__version__,'max_iter':1000,
        'normalizer':'sports-query-normalize-v1','C':1.0,'random_state':42,'max_features':6000,
        'ngram_range':[2,5],'analyzer':'char_wb','class_weight':'balanced','sublinear_tf':True,
        'artifact_sha256':hashlib.sha256(canonical(artifact).encode()).hexdigest(),
        'split_families':{s:sorted({r['family_key'] for r in values}) for s,values in splits.items()}}
    return {'corpus':corpus,'dataset_hash':digest,'manifest':manifest,'report':report,'artifact':artifact}


def predict(artifact,phrase):
    if artifact['format']!='points-metric-tfidf-v1':
        raise ValueError('Unsupported model format')
    vectorizer = TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),sublinear_tf=True,vocabulary=artifact['vocabulary'])
    vectorizer.idf_ = np.asarray(artifact['idf'])
    x = vectorizer.transform([normalize(phrase)])
    if not x.nnz:
        return {'label':None,'status':'no_known_features','executable':False}
    classifier = LogisticRegression()
    classifier.classes_ = np.asarray(artifact['classes'])
    classifier.coef_ = np.asarray(artifact['coef'])
    classifier.intercept_ = np.asarray(artifact['intercept'])
    classifier.n_features_in_ = len(artifact['vocabulary'])
    scores = classifier.predict_proba(x)[0]
    return {'label':str(classifier.classes_[int(np.argmax(scores))]),'status':'suggestion_only',
            'scores_uncalibrated':dict(zip(artifact['classes'],scores.tolist())),'executable':False}


def diagnose(artifact, phrase, corpus):
    result = predict(artifact, phrase)
    normalized = normalize(phrase)
    training = {}
    for row in corpus:
        if row['split'] == 'train':
            training.setdefault(normalize(row['phrase']), row)
    vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2,5), sublinear_tf=True,
                                vocabulary=artifact['vocabulary'])
    vectorizer.idf_ = np.asarray(artifact['idf'])
    neighbors = []
    if training:
        rows = list(training.values())
        similarities = (vectorizer.transform(list(training)) @ vectorizer.transform([normalized]).T).toarray().ravel()
        neighbors = [{'phrase':row['phrase'], 'label':row['label'], 'similarity':round(float(score),4)}
                     for row,score in sorted(zip(rows,similarities),key=lambda pair:(-pair[1],pair[0]['phrase']))[:3] if score>0]
    rule_label = METRICS.get(normalized) or CONTEXT_PHRASES.get(normalized)
    return {**result, 'rule_label':rule_label, 'trained_labels':artifact['classes'],
            'seen_in_training':normalized in training, 'training_phrase_count':len(training),
            'neighbors':neighbors, 'scope':'metric_phrase_only'}
