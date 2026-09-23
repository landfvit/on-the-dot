"""Prepare, run and audit an offline generative pilot. Never publishes questions."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
from uuid import uuid4

from api.database import get_connection
from api.trivia_bank_engine import BankEvaluator, season_label
from api.trivia_generation_experiment import BY_KEY, NoveltyIndex, snapshot_answer, wording
from api.trivia_llm_contract import FAMILIES, SPLITS, identity, messages, parse_proposal
from src.check_generated_trivia import independent_answer
from src.trivia_llm_worker import sha256

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'data/private/llm'


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + '\n')


def jsonl(path, values):
    path.write_text(''.join(json.dumps(value, ensure_ascii=False, default=str) + '\n' for value in values))


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def scope_for(team, season, name):
    return {'league_id': 39, 'team_id': team, 'team_name': name,
            'season': season, 'season_label': season_label(season)}


def snapshot(conn, seasons, dataset_id=None):
    if not seasons or len(set(seasons)) != len(seasons):
        raise ValueError('Select distinct, explicit season start years')
    dataset = conn.execute('''SELECT * FROM trivia_datasets WHERE sealed_at IS NOT NULL
        AND (%s::uuid IS NULL OR dataset_id=%s) ORDER BY created_at DESC LIMIT 1''',
        (dataset_id, dataset_id)).fetchone()
    if not dataset:
        raise ValueError('Sealed dataset not found')
    facts = conn.execute('''SELECT f.*,q.result_valid FROM trivia_match_team_facts f
        JOIN trivia_match_data_quality q USING(dataset_id,fixture_id)
        WHERE dataset_id=%s AND league_id=39 AND season=ANY(%s)
        ORDER BY season,match_date,fixture_id,team_id''', (dataset['dataset_id'], seasons)).fetchall()
    groups = defaultdict(list)
    by_season = defaultdict(list)
    for row in facts:
        groups[row['team_id'], row['season']].append(row)
        by_season[row['season']].append(row)
    for season in seasons:
        failure = BankEvaluator.audit_season(by_season[season])
        if failure:
            raise ValueError(f'Incomplete season {season}: {failure}')
    raw = conn.execute('''SELECT fixture_id,season,match_date,status,home_team_id,away_team_id,home_goals,away_goals
        FROM fixtures WHERE league_id=39 AND season=ANY(%s) ORDER BY fixture_id''', (seasons,)).fetchall()
    live = {row['fixture_id']: row for row in raw}
    if len(live) != 380 * len(seasons) or set(live) != {row['fixture_id'] for row in facts}:
        raise ValueError('Raw fixtures and sealed dataset scopes differ')
    for row in facts:
        match = live[row['fixture_id']]
        home = row['is_home']
        gf, ga = (match['home_goals'], match['away_goals']) if home else (match['away_goals'], match['home_goals'])
        expected = (match['season'], match['match_date'], match['status'],
                    match['home_team_id'] if home else match['away_team_id'],
                    match['away_team_id'] if home else match['home_team_id'], gf, ga)
        actual = tuple(row[key] for key in ('season', 'match_date', 'status', 'team_id', 'opponent_id', 'goals_for', 'goals_against'))
        if actual != expected or not row['result_valid'] or row['result'] != ('W' if gf > ga else 'D' if gf == ga else 'L'):
            raise ValueError('Raw/snapshot drift: audit and seal data before generating')
    digest = hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()
    return dataset, groups, digest


def checked_answer(conn, plan, rows):
    answer = snapshot_answer(plan, rows)
    other = independent_answer(conn, plan, rows[0]['team_id'], rows[0]['season'])
    if (answer['value'], answer['evidence_fixture_ids']) != (other['value'], other['evidence_fixture_ids']):
        raise ValueError('Independent answer or evidence mismatch')
    return answer, other


def existing_questions(conn, exclude_bundle=None):
    existing = [{'id': str(row['question_id']), 'question': row['text']} for row in conn.execute(
        "SELECT question_id,content->>'question' text FROM trivia_bank_questions")]
    for table, key in [('trivia_question_versions', 'version_id'), ('trivia_bank_authored_drafts', 'draft_id')]:
        existing += [{'id': str(row[key]), 'question': row['question_text']} for row in conn.execute(
            f'SELECT {key},question_text FROM {table}')]
    identities = set()
    for path in sorted((ROOT / 'reports/generated-trivia').glob('*/questions.json')):
        document = json.loads(path.read_text())
        for question in document['questions']:
            existing.append({'id': question['id'], 'question': question['question']})
            spec = question['specification']
            identities.add((spec['plan'], spec['team_id'], spec['seasons'][0]))
    for path in sorted((PRIVATE / 'bundles').glob('*/runs/*/report.json')):
        if exclude_bundle and path.parents[2].resolve() == exclude_bundle.resolve():
            continue
        for question in json.loads(path.read_text())['questions']:
            if question.get('database_check') != 'matched':
                continue
            existing.append({'id': f'{path.parent.name}:{question["id"]}', 'question': question['question']})
            identities.add(identity(question['query']))
    return existing, identities


def prepare(source, seasons, seed=42):
    source_doc = json.loads(source.read_text())
    examples = defaultdict(list)
    provenance = []
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        dataset, groups, digest = snapshot(conn, seasons, source_doc['dataset_id'])
        existing, seen = existing_questions(conn)
        for question in source_doc['questions']:
            spec = question['specification']
            if len(spec['seasons']) != 1 or spec['league_id'] != 39:
                raise ValueError('Unsupported training scope')
            team, season, plan = spec['team_id'], spec['seasons'][0], spec['plan']
            if season not in seasons:
                continue
            rows = groups[team, season]
            text = wording(plan, rows[0]['team_name'], season)
            if question['question'] != text:
                raise ValueError('Training text requires a fresh semantic review')
            answer, _ = checked_answer(conn, plan, rows)
            if answer != question['answer']:
                raise ValueError('Training answer changed')
            family = next(key for key, plans in FAMILIES.items() if plan in plans)
            split = SPLITS[family]
            scope = scope_for(team, season, rows[0]['team_name'])
            target = {'question': text, 'query': {'version': 'local-trivia-v1', 'plan': plan,
                      'team_id': team, 'season': season, 'league_id': 39}}
            example = {'messages': messages(scope, FAMILIES[family]) + [
                {'role': 'assistant', 'content': json.dumps(target)}]}
            examples[split].append(example)
            provenance.append({'source_id': question['id'], 'split': split, 'family': family,
                               'scope': scope, 'plan': plan, 'answer': answer,
                               'label_origin': 'assistant_authored_template_database_checked',
                               'human_reviewed': False})
        if any(len(examples[split]) < 5 for split in ('train', 'valid', 'test')):
            raise ValueError('Need at least five examples in every family-separated split')
        rng = random.Random(seed)
        scopes = list(groups)
        rng.shuffle(scopes)
        jobs = []
        used_scopes = {(item['scope']['team_id'], item['scope']['season']) for item in provenance}
        # Unseen club-season combinations. Held-out operation families and free-choice jobs
        # are reported separately; neither is used to fit or select a checkpoint.
        for family in ['chronology'] * 8 + ['transitions'] * 8 + ['free_choice'] * 4:
            allowed = FAMILIES[family] if family != 'free_choice' else list(BY_KEY)
            for team, season in scopes:
                if (team, season) in used_scopes or any((plan, team, season) in seen for plan in allowed):
                    continue
                rows = groups[team, season]
                valid_plans = []
                for plan in allowed:
                    try:
                        checked_answer(conn, plan, rows)
                        valid_plans.append(plan)
                    except ValueError:
                        continue
                if not valid_plans:
                    continue
                scope = scope_for(team, season, rows[0]['team_name'])
                jobs.append({'id': f'LLM-{len(jobs)+1:03}', 'family': family, 'scope': scope,
                             'allowed_plans': valid_plans, 'messages': messages(scope, valid_plans)})
                used_scopes.add((team, season))
                break
            else:
                raise ValueError('Not enough new club-season scopes for this benchmark')
    destination = PRIVATE / 'bundles' / str(uuid4())
    destination.mkdir(parents=True, mode=0o700)
    for split, values in examples.items():
        rng.shuffle(values)
        jsonl(destination / f'{split}.jsonl', values)
    jsonl(destination / 'jobs.jsonl', jobs)
    dump(destination / 'provenance.json', provenance)
    dump(destination / 'existing.json', {'questions': existing, 'identities': sorted(seen)})
    files = ['train.jsonl', 'valid.jsonl', 'test.jsonl', 'jobs.jsonl', 'provenance.json', 'existing.json']
    manifest = {'created_at': datetime.now(timezone.utc), 'dataset_id': dataset['dataset_id'],
                'snapshot_sha256': digest, 'source': str(source.resolve()), 'source_sha256': sha256(source),
                'seasons': seasons, 'seed': seed, 'family_splits': SPLITS,
                'counts': {key: len(value) for key, value in examples.items()}, 'benchmark_jobs': len(jobs),
                'sha256': {name: sha256(destination / name) for name in files},
                'limitations': ['Small synthetic pilot, not all 3930 imported questions.',
                    'Held-out template families; shared JSON protocol and operation descriptions are intentionally visible.',
                    'Automatic DB agreement is not human semantic approval or independent-provider verification.',
                    'No publication or production model replacement.']}
    dump(destination / 'manifest.json', manifest)
    return {'bundle': str(destination), 'counts': manifest['counts'], 'jobs': len(jobs)}


def verify_bundle(bundle):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    for filename, digest in manifest['sha256'].items():
        path = (bundle / filename).resolve()
        if not path.is_relative_to(bundle.resolve()) or sha256(path) != digest:
            raise ValueError('Frozen benchmark/training bundle changed')
    return manifest


def runtime_env():
    # Do not inherit database credentials, API keys, editor passwords or cloud tracking settings.
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'SYSTEMROOT') if key in os.environ}
    env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
               WANDB_DISABLED='true', TOKENIZERS_PARALLELISM='false')
    return env


def infer(bundle, model, label, adapter=None):
    verify_bundle(bundle)
    if not label or any(char not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for char in label):
        raise ValueError('Use a simple lowercase run label')
    run = bundle / 'runs' / label
    run.mkdir(parents=True, exist_ok=False)
    command = [str(ROOT / '.venv-llm/bin/python'), '-m', 'src.trivia_llm_worker', '--model', str(model),
               '--jobs', str(bundle / 'jobs.jsonl'), '--output', str(run / 'raw.jsonl')]
    if adapter:
        command += ['--adapter', str(adapter)]
    try:
        subprocess.run(command, cwd=ROOT, env=runtime_env(), check=True, timeout=3600)
    except (subprocess.SubprocessError, OSError) as error:
        dump(run / 'failure.json', {'error': str(error), 'state': 'failed_no_publication'})
        raise
    return audit(bundle, run)


def audit(bundle, run):
    manifest = verify_bundle(bundle)
    jobs = {job['id']: job for job in read_jsonl(bundle / 'jobs.jsonl')}
    records = read_jsonl(run / 'raw.jsonl')
    if len(records) != len(jobs) or {record['id'] for record in records} != set(jobs):
        raise ValueError('Missing or duplicate generation records')
    existing = json.loads((bundle / 'existing.json').read_text())
    seen = {tuple(item) for item in existing['identities']}
    texts = list(existing['questions'])
    results = []
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        _, groups, digest = snapshot(conn, manifest['seasons'], manifest['dataset_id'])
        if digest != manifest['snapshot_sha256']:
            raise ValueError('Benchmark facts changed')
        current, identities = existing_questions(conn, exclude_bundle=bundle)
        texts += current
        seen.update(identities)
        for record in records:
            job = jobs[record['id']]
            result = {'id': record['id'], 'family': job['family'], 'raw': record['raw'],
                      'state': 'rejected', 'publishable': False, 'semantic_review': 'not_performed',
                      'seconds': record['seconds']}
            try:
                if record['jobs_sha256'] != sha256(bundle / 'jobs.jsonl'):
                    raise ValueError('Inference used another benchmark')
                if record['finish_reason'] != 'stop':
                    raise ValueError('Incomplete model output')
                proposal = parse_proposal(record['raw'], job)
                query = proposal.query.model_dump()
                result.update(question=proposal.question, query=query, schema_and_scope_valid=True)
                if identity(query) in seen:
                    raise ValueError('This calculation already exists for this club-season')
                novelty = NoveltyIndex(texts).check(query['plan'], query['team_id'], query['season'], proposal.question)
                result['novelty'] = novelty
                if not novelty['accepted']:
                    raise ValueError(f'Question duplicate: {novelty["reason"]}')
                answer, independent = checked_answer(conn, query['plan'], groups[query['team_id'], query['season']])
                result.update(answer=answer, answer_text=answer['details'].get('opponent_name', str(answer['value'])),
                              independent_verification=independent, database_check='matched',
                              reference_wording=wording(query['plan'], job['scope']['team_name'], query['season']),
                              state='database_checked_needs_wording_review', semantic_review='required')
                seen.add(identity(query))
                texts.append({'id': record['id'], 'question': proposal.question})
            except ValueError as error:
                result['reason'] = str(error)
            results.append(result)
    summary = {'total': len(results), 'schema_and_scope_valid': sum(bool(q.get('schema_and_scope_valid')) for q in results),
               'database_checked_drafts': sum(q.get('database_check') == 'matched' for q in results),
               'rejected': sum(q['state'] == 'rejected' for q in results), 'human_approved': 0, 'published': 0,
               'by_family': {family: dict(Counter(q['state'] for q in results if q['family'] == family))
                             for family in sorted({q['family'] for q in results})},
               'selected_operations': dict(Counter(q['query']['plan'] for q in results if 'query' in q)),
               'raw_sha256': sha256(run / 'raw.jsonl'), 'bundle_manifest_sha256': sha256(bundle / 'manifest.json'),
               'wording_accuracy': None, 'note': 'DB check verifies the structured query answer, NOT free-form wording correctness.'}
    dump(run / 'report.json', {'summary': summary, 'questions': results})
    lines = ['# Local Model: Draft Review', '', json.dumps(summary, indent=2), '',
             'These are model-written drafts, not published questions. Check every restriction against the reference.',
             'The reference below is NOT substituted for the generated wording.', '']
    for question in results:
        lines += [f'## {question["id"]}', question.get('question', question['raw']), '',
                  f'Status: {question["state"]}', f'Answer: {question.get("answer_text", "not accepted")}',
                  f'Reference meaning: {question.get("reference_wording", "n/a")}',
                  f'Issue: {question.get("reason", "Human wording review required")}', '']
    (run / 'review.md').write_text('\n'.join(lines) + '\n')
    return {'run': str(run), **summary}


def compare(bundle, candidate):
    verify_bundle(bundle)
    if not candidate or any(char not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for char in candidate):
        raise ValueError('Use a simple run label')
    runs = [bundle / 'runs' / label for label in ('baseline', candidate)]
    reports = [json.loads((run / 'report.json').read_text()) for run in runs]
    records = [read_jsonl(run / 'raw.jsonl') for run in runs]
    if [r['id'] for r in records[0]] != [r['id'] for r in records[1]]:
        raise ValueError('Different benchmark items')
    for left, right in zip(*records):
        if (left['jobs_sha256'], left['seed'], left['model'], left['mlx_lm_version']) != (
                right['jobs_sha256'], right['seed'], right['model'], right['mlx_lm_version']):
            raise ValueError('Different base model, prompts, sampling seeds or runtime')
    for report, run in zip(reports, runs):
        if report['summary']['raw_sha256'] != sha256(run / 'raw.jsonl'):
            raise ValueError('Inference output changed after audit')
    result = {'baseline': reports[0]['summary'], 'candidate': reports[1]['summary'],
              'median_seconds': {run.name: round(statistics.median(row['seconds'] for row in items), 2)
                                 for run, items in zip(runs, records)},
              'verdict': 'Pilot comparison only. No automatic promotion; wording and diversity need separate review.',
              'automatic_answer_accuracy': None}
    dump(bundle / f'comparison-{candidate}.json', result)
    lines = ['# Local Trivia Generator: Pilot Comparison', '',
             '| Check | Base model | LoRA candidate |', '|---|---:|---:|']
    for key, label in [('total', 'Generated'), ('schema_and_scope_valid', 'Valid JSON and requested scope'),
                       ('database_checked_drafts', 'Novel drafts with matching DB calculations'),
                       ('rejected', 'Rejected'), ('published', 'Published')]:
        lines.append(f'| {label} | {reports[0]["summary"][key]} | {reports[1]["summary"][key]} |')
    lines += ['', result['verdict'], '',
              'Database agreement does not certify that the model wording asks the same question.',
              'Both database calculations use the same provider data. No external-source fact check is claimed.',
              '', '## Candidate Questions', '']
    for question in reports[1]['questions']:
        lines += [f'### {question["id"]}', question.get('question', question['raw']), '',
                  f'**Answer:** {question.get("answer_text", "rejected")}',
                  f'**Reference meaning:** {question.get("reference_wording", "n/a")}',
                  f'**Status:** {question["state"]}', '']
    (bundle / f'comparison-{candidate}.md').write_text('\n'.join(lines) + '\n')
    return result


def resume_source(source, bundle, model_manifest):
    source = source.resolve()
    weights = source / 'adapters.safetensors'
    if not weights.is_file() or (source / 'failure.json').exists():
        raise ValueError('A completed source adapter is required')
    metadata = json.loads((source / 'training-manifest.json').read_text())
    config = json.loads((source / 'adapter_config.json').read_text())
    if metadata['model_manifest'] != model_manifest:
        raise ValueError('Source adapter uses another base model')
    if metadata['bundle_manifest_sha256'] != sha256(bundle / 'manifest.json'):
        raise ValueError('Continuation requires the same frozen training and evaluation splits')
    if not metadata.get('target_format', '').startswith('Exact inference prompt + JSON completion + EOS;'):
        raise ValueError('Source adapter predates the corrected JSON completion format')
    if (config.get('fine_tune_type'), config.get('num_layers'), config.get('lora_parameters')) != (
            'lora', 4, {'rank': 8, 'dropout': 0.0, 'scale': 20.0}):
        raise ValueError('Source LoRA configuration is incompatible')
    digest = sha256(weights)
    completion = source / 'completion.json'
    if metadata.get('completion_required') and not completion.is_file():
        raise ValueError('Source training did not complete')
    if completion.is_file() and json.loads(completion.read_text())['adapter_sha256'] != digest:
        raise ValueError('Source adapter changed since training completed')
    return {'path': str(source), 'weights': str(weights), 'sha256': digest,
            'training_manifest_sha256': sha256(source / 'training-manifest.json'),
            'previous_updates': metadata.get('total_updates', config['iters']),
            'optimizer_state': 'New Adam optimizer; continue learned weights, not an exact optimizer-state resume.'}


def train(bundle, model, iterations, label='adapter', resume_adapter=None):
    manifest = verify_bundle(bundle)
    if not 1 <= iterations <= 200:
        raise ValueError('Pilot training is bounded to 1-200 updates')
    baseline = bundle / 'runs/baseline/report.json'
    if not baseline.is_file():
        raise ValueError('Measure the base model on the frozen benchmark before training')
    if not label or any(char not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for char in label):
        raise ValueError('Use a simple adapter label')
    model_manifest = json.loads((model / 'points-model.json').read_text())
    parent = resume_source(resume_adapter, bundle, model_manifest) if resume_adapter else None
    adapter = bundle / label
    adapter.mkdir(exist_ok=False)
    command = [str(ROOT / '.venv-llm/bin/python'), '-u', '-m', 'src.trivia_llm_train_worker', '--model', str(model.resolve()), '--train',
               '--data', str(bundle.resolve()), '--adapter-path', str(adapter.resolve()), '--iters', str(iterations),
               '--batch-size', '1', '--num-layers', '4', '--max-seq-length', '2048', '--learning-rate', '0.00005',
               '--mask-prompt', '--grad-checkpoint', '--steps-per-report', '5', '--steps-per-eval', str(iterations),
               '--val-batches', '5', '--save-every', str(iterations), '--seed', '42']
    if parent:
        command += ['--resume-adapter-file', parent['weights']]
    dump(adapter / 'training-manifest.json', {'command': command, 'bundle_manifest_sha256': sha256(bundle / 'manifest.json'),
        'baseline_sha256': sha256(baseline), 'family_splits': manifest['family_splits'],
        'model_manifest': model_manifest, 'resume': parent, 'iterations': iterations,
        'total_updates': iterations + (parent['previous_updates'] if parent else 0), 'completion_required': True,
        'target_format': 'Exact inference prompt + JSON completion + EOS; no assistant chat-template injection.',
        'code_sha256': {path: sha256(ROOT / path) for path in (
            'src/trivia_llm_train_worker.py', 'src/trivia_llm_dataset.py', 'requirements-llm.lock.txt')},
        'checkpoint_policy': 'Fixed final iteration only; never select using test results.'})
    with (adapter / 'training.log').open('x') as log:
        try:
            subprocess.run(command, cwd=ROOT, env=runtime_env(), stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=3600)
        except (subprocess.SubprocessError, OSError) as error:
            dump(adapter / 'failure.json', {'error': str(error)})
            raise
    result = {'adapter': str(adapter), 'iterations': iterations,
              'total_updates': iterations + (parent['previous_updates'] if parent else 0),
              'adapter_sha256': sha256(adapter / 'adapters.safetensors')}
    dump(adapter / 'completion.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--source', type=Path, required=True)
    prep.add_argument('--seasons', type=int, nargs='+', required=True)
    prep.add_argument('--seed', type=int, default=42)
    run = sub.add_parser('infer')
    training = sub.add_parser('train')
    check = sub.add_parser('audit')
    comparison = sub.add_parser('compare')
    comparison.add_argument('--candidate', required=True)
    for command in (run, training, check, comparison):
        command.add_argument('--bundle', type=Path, required=True)
    for command in (run, training):
        command.add_argument('--model', type=Path, default=PRIVATE / 'models/qwen3-4b')
    run.add_argument('--label', required=True)
    run.add_argument('--adapter', type=Path)
    training.add_argument('--iterations', type=int, default=40)
    training.add_argument('--label', default='adapter')
    training.add_argument('--resume-adapter', type=Path, help='Continue weights from a compatible completed local adapter')
    check.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.source, args.seasons, args.seed)
    elif args.command == 'infer':
        result = infer(args.bundle, args.model, args.label, args.adapter)
    elif args.command == 'train':
        result = train(args.bundle, args.model, args.iterations, args.label, args.resume_adapter)
    elif args.command == 'compare':
        result = compare(args.bundle, args.candidate)
    else:
        result = audit(args.bundle, args.run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
