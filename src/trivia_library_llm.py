"""Train a local question writer on the real library, with frozen DB provenance.

This is query-to-question generation, not answer prediction or autonomous SQL.
Nothing in this offline experiment publishes questions or replaces the live model.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess
from uuid import uuid4

from sklearn.model_selection import GroupShuffleSplit

from api.database import get_connection
from api.trivia_bank_engine import CannotCheck, canonical, family_key, load_evaluator
from src.trivia_bank_model import grouped_families
from src.trivia_library_queries import compile_question, messages, parse_output, render
from src.trivia_llm import ROOT, PRIVATE, dump, jsonl, read_jsonl, runtime_env, snapshot, verify_bundle
from src.trivia_llm_worker import sha256, verify_model


def identity(query):
    return json.dumps(query, sort_keys=True)


def split_rows(rows):
    families = grouped_families(rows)
    groups = [families[family_key(row['question'])] for row in rows]
    trainval, test = next(GroupShuffleSplit(n_splits=1, test_size=.15, random_state=42).split(rows, groups=groups))
    train, valid = next(GroupShuffleSplit(n_splits=1, test_size=.12, random_state=43).split(
        trainval, groups=[groups[i] for i in trainval]))
    splits = {'train': trainval[train], 'valid': trainval[valid], 'test': test}
    result = {}
    for name, indices in splits.items():
        result[name] = [dict(rows[int(i)], family=groups[int(i)]) for i in indices]
    assert all(not ({r['family'] for r in result[a]} & {r['family'] for r in result[b]})
               for a, b in [('train', 'valid'), ('train', 'test'), ('valid', 'test')])
    return result


def diverse(rows, limit):
    buckets = defaultdict(list)
    for row in rows:
        buckets[row['query']['op']].append(row)
    result = []
    rng = random.Random(42)
    for values in buckets.values():
        rng.shuffle(values)
    while buckets and len(result) < limit:
        for key in sorted(list(buckets)):
            result.append(buckets[key].pop())
            if not buckets[key]:
                del buckets[key]
            if len(result) == limit:
                break
    return result


def new_queries(rows, known, evaluator, limit=32):
    result = []
    for row in diverse(rows, len(rows)):
        query = row['query']
        if 'season' not in query['params']:
            continue
        for season in sorted(evaluator.seasons, reverse=True):
            candidate = {'op': query['op'], 'params': dict(query['params'], season=season)}
            key = identity(candidate)
            if key in known:
                continue
            try:
                question = render(candidate)
                answer = evaluator.calculate(question)
                # Score-choice questions must actually contain the computed answer.
                if candidate['op'] == 'fixture_score_choices' and answer['answer'] not in (
                        candidate['params']['score'], candidate['params']['score2']):
                    continue
            except (CannotCheck, ValueError, KeyError):
                continue
            known.add(key)
            result.append({'query': candidate, 'expected': answer, 'kind': 'new_scope'})
            break
        if len(result) == limit:
            break
    return result


def prepare():
    eligible, excluded, known = [], [], set()
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        dataset = conn.execute('SELECT dataset_id FROM trivia_datasets WHERE sealed_at IS NOT NULL ORDER BY created_at DESC LIMIT 1').fetchone()['dataset_id']
        evaluator, inputs = load_evaluator(conn, dataset)
        source = conn.execute('SELECT question_id, batch_id, content FROM trivia_bank_questions ORDER BY question_id').fetchall()
        for row in source:
            item = row['content']
            checked = evaluator.check(item)
            try:
                query = compile_question(item['question'])
                key = identity(query)
                duplicate = key in known
                known.add(key)
                if checked['status'] != 'matched':
                    raise ValueError(checked['status'])
                if duplicate:
                    raise ValueError('duplicate_query')
                recalculated = evaluator.calculate(render(query))
                if canonical(recalculated['answer']) != canonical(checked['answer']):
                    raise ValueError('query_roundtrip_answer_mismatch')
                if query['op'] == 'fixture_score_choices' and checked['answer'] not in (query['params']['score'], query['params']['score2']):
                    raise ValueError('correct_score_not_in_choices')
                eligible.append({'id': str(row['question_id']), 'external_id': item['id'],
                    'batch_id': str(row['batch_id']), 'question': item['question'], 'topic': item['topic'],
                    'query': query, 'reference_answer': item['answer'], 'checked': checked})
            except ValueError as exc:
                excluded.append({'id': str(row['question_id']), 'status': checked['status'], 'reason': str(exc)})
        splits = split_rows(eligible)
        jobs = [{'query': r['query'], 'expected': r['checked'], 'kind': 'heldout_family', 'source_id': r['id']}
                for r in diverse(splits['test'], 16)]
        jobs += new_queries(splits['train'], known.copy(), evaluator)
        seasons = sorted({s for r in eligible for s in r['checked']['seasons']} |
                         {s for r in jobs for s in r['expected']['seasons']})
        _, _, digest = snapshot(conn, seasons, dataset)
    bundle = PRIVATE / 'library-bundles' / str(uuid4())
    bundle.mkdir(parents=True, mode=0o700)
    for split, rows in splits.items():
        random.Random(42).shuffle(rows)
        jsonl(bundle / f'{split}.jsonl', [{'messages': messages(row['query']) + [
            {'role': 'assistant', 'content': json.dumps({'question': row['question']}, ensure_ascii=False)}]}
            for row in rows])
    jsonl(bundle / 'jobs.jsonl', [{'id': f'library-{i:03}', **row, 'messages': messages(row['query'])}
                                for i, row in enumerate(jobs, 1)])
    dump(bundle / 'provenance.json', splits)
    dump(bundle / 'excluded.json', excluded)
    dump(bundle / 'source.json', source)
    dump(bundle / 'inputs.json', inputs)
    files = ['train.jsonl', 'valid.jsonl', 'test.jsonl', 'jobs.jsonl', 'provenance.json', 'excluded.json', 'source.json', 'inputs.json']
    manifest = {'format': 'points-library-writer-v1', 'created_at': datetime.now(timezone.utc),
        'dataset_id': dataset, 'seasons': seasons, 'snapshot_sha256': digest,
        'source_count': len(source), 'fresh_db_statuses': dict(Counter(r['status'] for r in excluded) + Counter(matched=len(eligible))),
        'eligible_count': len(eligible), 'excluded_count': len(excluded),
        'excluded_reasons': dict(Counter(r['reason'] for r in excluded)),
        'counts': {k: len(v) for k, v in splits.items()},
        'topic_counts': {k: dict(Counter(r['topic'] for r in v)) for k, v in splits.items()},
        'operator_counts': {k: dict(Counter(r['query']['op'] for r in v)) for k, v in splits.items()},
        'family_counts': {k: len({r['family'] for r in v}) for k, v in splits.items()},
        'split_policy': 'Club/season/number masked; >=90% similar families grouped transitively, no split overlap; seeds 42/43.',
        'prompt_policy': 'Semantic query and club names only. No reference wording or answer in any prompt.',
        'benchmark': dict(Counter(r['kind'] for r in jobs)),
        'sha256': {name: sha256(bundle / name) for name in files},
        'code_sha256': {name: sha256(ROOT / name) for name in ('src/trivia_library_queries.py', 'src/trivia_library_llm.py', 'api/trivia_bank_engine.py', 'api/bank_recognition.py')},
        'limitations': ['Query-to-question writer, not autonomous query invention or answer prediction.',
                       'Strict wording compiler abstains on unrecognized paraphrases; pass rate is not semantic accuracy.',
                       'New-scope jobs are new queries, not necessarily lexically dissimilar questions.',
                       'No publication, no production promotion, no independent external-provider verification.']}
    dump(bundle / 'manifest.json', manifest)
    return {'bundle': str(bundle), **{k: manifest[k] for k in ('source_count', 'eligible_count', 'counts', 'family_counts', 'benchmark', 'excluded_reasons')}}


def verify(bundle):
    manifest = verify_bundle(bundle)
    if manifest['format'] != 'points-library-writer-v1':
        raise ValueError('Wrong library format')
    for name, digest in manifest['code_sha256'].items():
        if sha256(ROOT / name) != digest:
            raise ValueError('Calculation or data preparation code changed since freeze')
    return manifest


def infer(bundle, model, label, adapter=None):
    verify(bundle)
    if not label or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in label):
        raise ValueError('Invalid run label')
    run = bundle / 'runs' / label
    run.mkdir(parents=True, exist_ok=False)
    command = [str(ROOT / '.venv-llm/bin/python'), '-u', '-m', 'src.trivia_llm_worker', '--model', str(model),
               '--jobs', str(bundle / 'jobs.jsonl'), '--output', str(run / 'raw.jsonl')]
    if adapter:
        command += ['--adapter', str(adapter)]
    subprocess.run(command, cwd=ROOT, env=runtime_env(), check=True, timeout=3600)
    return audit(bundle, run)


def audit(bundle, run):
    manifest = verify(bundle)
    jobs = {r['id']: r for r in read_jsonl(bundle / 'jobs.jsonl')}
    raw = read_jsonl(run / 'raw.jsonl')
    if len(raw) != len(jobs) or {r['id'] for r in raw} != set(jobs):
        raise ValueError('Missing or duplicate generation jobs')
    results = []
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        _, _, digest = snapshot(conn, manifest['seasons'], manifest['dataset_id'])
        evaluator, inputs = load_evaluator(conn, manifest['dataset_id'])
        if digest != manifest['snapshot_sha256'] or inputs['standings_hash'] != json.loads((bundle / 'inputs.json').read_text())['standings_hash']:
            raise ValueError('Database inputs changed')
        for record in raw:
            job = jobs[record['id']]
            if record['jobs_sha256'] != sha256(bundle / 'jobs.jsonl'):
                raise ValueError('Generation used another benchmark')
            result = {'id': record['id'], 'kind': job['kind'], 'query': job['query'],
                      'raw': record['raw'], 'passed': False, 'publishable': False}
            try:
                result['question'] = parse_output(record['raw'], job['query'])
                answer = evaluator.calculate(result['question'])
                if canonical(answer['answer']) != canonical(job['expected']['answer']):
                    raise ValueError('Database answer drift')
                result.update(passed=True, answer=answer['answer'], details=answer['details'],
                    evidence_fixture_ids=answer['evidence_fixture_ids'], state='database_checked_needs_editorial_review')
            except (ValueError, CannotCheck) as exc:
                result['reason'] = str(exc) if isinstance(exc, ValueError) else exc.reason
            results.append(result)
    summary = {kind: {'passed': sum(r['passed'] for r in results if r['kind'] == kind),
                       'total': sum(r['kind'] == kind for r in results)} for kind in ('heldout_family', 'new_scope')}
    dump(run / 'report.json', {'summary': summary, 'questions': results, 'automatic_publication': False})
    lines = ['# Library-trained generator: actual outputs', '',
             'Strict query/wording/DB check only. Unrecognized paraphrases abstain. No automatic publication.', '',
             '```json', json.dumps(summary, indent=2), '```', '']
    for row in results:
        lines += [f"## {row['id']} / {row['kind']} / {'PASS' if row['passed'] else 'REVIEW'}", '', row['raw'], '',
                  f"Database answer: {row.get('answer', 'not approved')}", '', f"Check: {row.get('reason', row.get('state'))}", '']
    (run / 'review.md').write_text('\n'.join(lines))
    return {'run': str(run), 'summary': summary}


def train(bundle, model):
    manifest = verify(bundle)
    iterations = manifest['counts']['train']
    if not 500 <= iterations <= 2500:
        raise ValueError('Library training requires 500-2500 distinct rows, one full epoch')
    baseline = bundle / 'runs/baseline/report.json'
    if not baseline.exists():
        raise ValueError('Run the frozen base-model benchmark first')
    model_manifest = verify_model(model)
    adapter = bundle / 'adapter-one-epoch'
    adapter.mkdir(exist_ok=False)
    command = [str(ROOT / '.venv-llm/bin/python'), '-u', '-m', 'src.trivia_llm_train_worker',
        '--model', str(model.resolve()), '--train', '--data', str(bundle.resolve()),
        '--adapter-path', str(adapter.resolve()), '--iters', str(iterations), '--batch-size', '1',
        '--num-layers', '4', '--max-seq-length', '1024', '--learning-rate', '0.00005', '--mask-prompt',
        '--grad-checkpoint', '--steps-per-report', '25', '--steps-per-eval', str(iterations),
        '--val-batches', '25', '--save-every', str(iterations), '--seed', '42']
    dump(adapter / 'training-manifest.json', {'command': command, 'model_manifest': model_manifest,
        'bundle_manifest_sha256': sha256(bundle / 'manifest.json'), 'baseline_sha256': sha256(baseline),
        'protocol': 'library-one-epoch-v1', 'iterations': iterations, 'total_updates': iterations,
        'completion_required': True, 'resume': None, 'training_rows': iterations,
        'target_format': 'Exact inference prompt + JSON completion + EOS; no assistant chat-template injection.',
        'selection_policy': 'Fixed one full shuffled pass, batch size 1; no checkpoint selected using test results.',
        'code_sha256': {name: sha256(ROOT / name) for name in ('src/trivia_llm_train_worker.py', 'src/trivia_llm_dataset.py', 'requirements-llm.lock.txt')}})
    with (adapter / 'training.log').open('x') as log:
        try:
            subprocess.run(command, cwd=ROOT, env=runtime_env(), stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=7200)
        except (subprocess.SubprocessError, OSError) as exc:
            dump(adapter / 'failure.json', {'error': str(exc)})
            raise
    result = {'adapter': str(adapter), 'iterations': iterations, 'unique_training_rows_seen': iterations,
        'total_updates': iterations, 'adapter_sha256': sha256(adapter / 'adapters.safetensors')}
    dump(adapter / 'completion.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'infer', 'train', 'audit'])
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--model', type=Path, default=PRIVATE / 'models/qwen3-4b')
    parser.add_argument('--label', default='baseline')
    parser.add_argument('--adapter', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare()
    elif not args.bundle:
        parser.error('--bundle is required')
    elif args.command == 'train':
        result = train(args.bundle, args.model)
    elif args.command == 'infer':
        result = infer(args.bundle, args.model, args.label, args.adapter)
    else:
        result = audit(args.bundle, args.bundle / 'runs' / args.label)
    print(json.dumps(result, indent=2, default=str), flush=True)


if __name__ == '__main__':
    main()
