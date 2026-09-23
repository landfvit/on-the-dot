"""Local question-authoring baseline. Learns topics and retrieves examples, not answers."""
from collections import Counter
import hashlib
import json

import numpy as np
import sklearn
from rapidfuzz.fuzz import ratio
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit

from api.trivia_bank_engine import family_key


def grouped_families(items):
    families = sorted({family_key(item['question']) for item in items})
    parent = list(range(len(families)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # All club/season/number variants AND near paraphrases stay in one split.
    for i, a in enumerate(families):
        for j in range(i):
            if ratio(a, families[j]) >= 90:
                parent[root(i)] = root(j)
    return {f: root(i) for i, f in enumerate(families)}


def vectorizer(artifact=None):
    kwargs = dict(analyzer='char_wb', ngram_range=(3, 5), sublinear_tf=True)
    if artifact:
        v = TfidfVectorizer(**kwargs, vocabulary=artifact['vocabulary'])
        v.idf_ = np.asarray(artifact['idf'])
        return v
    return TfidfVectorizer(**kwargs, max_features=12000)


def classifier():
    return LogisticRegression(C=4, max_iter=1500, class_weight='balanced', random_state=42)


def artifact_for(v, model):
    return {'format': 'points-bank-authoring-v1', 'classes': model.classes_.tolist(),
            'vocabulary': {k: int(value) for k, value in v.vocabulary_.items()},
            'idf': v.idf_.tolist(), 'coef': model.coef_.tolist(), 'intercept': model.intercept_.tolist()}


def train(items, checks):
    families = grouped_families(items)
    texts = [family_key(i['question']) for i in items]
    groups = [families[t] for t in texts]
    labels = [i['topic'] for i in items]
    if len(set(groups)) < 5 or len(set(labels)) < 2:
        raise ValueError('Need at least five independent families and two topics')
    trainval, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42).split(texts, labels, groups))
    trainlocal, vallocal = next(GroupShuffleSplit(n_splits=1, test_size=.125, random_state=43).split(
        trainval, groups=[groups[i] for i in trainval]))
    splits = {'train': trainval[trainlocal].tolist(), 'validation': trainval[vallocal].tolist(), 'test': test.tolist()}
    v, model = vectorizer(), classifier()
    x = v.fit_transform([texts[i] for i in splits['train']])
    model.fit(x, [labels[i] for i in splits['train']])
    report = {'scope': 'question_topic_classification_and_example_retrieval', 'generative_llm': False,
        'answer_prediction': False, 'sklearn_version': sklearn.__version__, 'random_state': 42,
        'split_policy': 'club/season/number masked; >=90% similar templates grouped transitively',
        'family_count': len(set(groups)), 'question_count': len(items),
        'counts': {split: len(indices) for split, indices in splits.items()},
        'validation_statuses': dict(Counter(r['status'] for r in checks.values())),
        'warning': 'Topic accuracy is not answer accuracy. Source answers are user-attested; no answer is learned. Sparse topics may have no held-out family.'}
    for split in ('validation', 'test'):
        indices = splits[split]
        actual = [labels[i] for i in indices]
        predicted = model.predict(v.transform([texts[i] for i in indices])).tolist()
        report[split] = {'accuracy': accuracy_score(actual, predicted),
            'macro_f1': f1_score(actual, predicted, average='macro', zero_division=0),
            'unseen_training_topics': sorted(set(actual) - set(model.classes_)),
            'predictions': [{'id': items[i]['id'], 'expected': a, 'predicted': p} for i, a, p in zip(indices, actual, predicted)]}
    membership = {i: split for split, indices in splits.items() for i in indices}
    corpus = [{'id': item['id'], 'question': item['question'], 'topic': item['topic'],
               'family': families[texts[i]], 'split': membership[i],
               'validation_status': checks[item['id']]['status']} for i, item in enumerate(items)]
    report['corpus_sha256'] = hashlib.sha256(json.dumps(corpus, sort_keys=True).encode()).hexdigest()
    # Evaluation above uses held-out families. The authoring artifact is then refit on all texts.
    final_v, final_model = vectorizer(), classifier()
    final_model.fit(final_v.fit_transform(texts), labels)
    report['artifact_training_rows'] = len(items)
    report['artifact_policy'] = 'refit_all_texts_after_heldout_evaluation; suggestion_only; never_SQL'
    return corpus, report, artifact_for(final_v, final_model)


def suggest(artifact, corpus, question, limit=5):
    if artifact['format'] != 'points-bank-authoring-v1': raise ValueError('Unknown model format')
    v = vectorizer(artifact)
    x = v.transform([family_key(question)])
    if not x.nnz: return {'topic': None, 'neighbors': [], 'scope': 'suggestion_only'}
    model = LogisticRegression()
    model.classes_ = np.asarray(artifact['classes'])
    model.coef_ = np.asarray(artifact['coef'])
    model.intercept_ = np.asarray(artifact['intercept'])
    model.n_features_in_ = len(artifact['vocabulary'])
    scores = (v.transform([family_key(row['question']) for row in corpus]) @ x.T).toarray().ravel()
    neighbors, seen = [], set()
    for i in np.argsort(-scores, kind='stable'):
        row = corpus[int(i)]
        if row['family'] in seen or scores[i] <= 0: continue
        seen.add(row['family'])
        neighbors.append({'id': row['id'], 'question': row['question'], 'topic': row['topic'],
                          'validation_status': row['validation_status'], 'similarity': round(float(scores[i]), 4)})
        if len(neighbors) == limit: break
    return {'topic': str(model.predict(x)[0]), 'neighbors': neighbors, 'scope': 'suggestion_only'}
