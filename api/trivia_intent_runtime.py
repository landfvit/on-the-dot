"""Bounded inference using a manually selected recognition adapter."""
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from api.trivia_intent_contract import messages, parse
from src.trivia_llm import PRIVATE, ROOT, jsonl, read_jsonl, runtime_env, verify_bundle
from src.trivia_llm_worker import sha256

# Set only after inspecting the held-out evaluation. Training never changes this.
ACTIVE_BUNDLE = PRIVATE / 'intent-bundles/e6311f00-07b8-449b-8e10-d901d7139a66'
MODEL = PRIVATE / 'models/qwen3-4b'


def available():
    if ACTIVE_BUNDLE is None:
        return False
    try:
        verify_bundle(ACTIVE_BUNDLE)
        adapter = ACTIVE_BUNDLE / 'adapter'
        completion = json.loads((adapter / 'completion.json').read_text())
        return not (adapter / 'failure.json').exists() and completion['adapter_sha256'] == sha256(adapter / 'adapters.safetensors')
    except (OSError, ValueError, KeyError):
        return False


def guard(query, question):
    """Ground slots in the user's text; confirmation still checks semantic intent."""
    if query is None:
        return
    text = re.sub(r'\s+', ' ', question.casefold())
    if not re.search(r'\b(premier league|epl|pl)\b', text):
        raise ValueError('Specify the competition; none is assumed.')
    for field in ('player', 'team'):
        if query[field] and not re.search(r'(?<!\w)' + re.escape(query[field].casefold()) + r'(?!\w)', text):
            raise ValueError('The model changed an entity name.')
    seasons = re.findall(r'\b(20\d{2}|19\d{2})/(20\d{2}|19\d{2}|\d{2})\b', text)
    if any(int(end) % 100 != (int(start) + 1) % 100 for start, end in seasons):
        raise ValueError('Invalid season range.')
    career = bool(re.search(r'\b(career|all.time|all (?:his |her |their )?seasons)\b', text))
    if query['time_scope'] == 'career' and (not career or seasons):
        raise ValueError('Career scope must be explicit and cannot discard a season.')
    if query['time_scope'] == 'season' and (career or len(seasons) != 1 or int(seasons[0][0]) != query['season']):
        raise ValueError('The model changed the requested time scope.')
    if query['time_scope'] == 'unspecified' and (career or seasons):
        raise ValueError('The model dropped the requested time scope.')
    remaining = re.sub(r'\b(?:20\d{2}|19\d{2})/(?:20\d{2}|19\d{2}|\d{2})\b', '', text)
    ordinal = {'league_champion': '1st', 'league_runner_up': '2nd'}.get(query['operation'])
    if ordinal:
        remaining = re.sub(r'\b' + ordinal + r'\b', '', remaining)
    if re.search(r'\d', remaining):
        raise ValueError('This query cannot preserve an extra numeric threshold or date cutoff.')
    # These slots are not expressible in this deliberately small first contract.
    if re.search(r'\b(home|away|against|before|after|between|since|until|minute|minutes|penalties|penalty|non-penalty|only|will|predict)\b', text):
        raise ValueError('This interpretation cannot represent all the question filters.')


def recognize(question):
    if not available():
        raise ValueError('No reviewed recognition adapter is available.')
    with TemporaryDirectory(prefix='recognition-', dir=PRIVATE) as directory:
        directory = Path(directory)
        jobs, output = directory / 'jobs.jsonl', directory / 'raw.jsonl'
        jsonl(jobs, [{'id': 'question', 'messages': messages(question)}])
        subprocess.run([str(ROOT / '.venv-llm/bin/python'), '-m', 'src.trivia_llm_worker',
            '--model', str(MODEL), '--adapter', str(ACTIVE_BUNDLE / 'adapter'),
            '--jobs', str(jobs), '--output', str(output)], cwd=ROOT, env=runtime_env(),
            timeout=150, check=True, capture_output=True)
        records = read_jsonl(output)
        if len(records) != 1 or records[0]['jobs_sha256'] != sha256(jobs):
            raise ValueError('Invalid recognition record')
        try:
            query = parse(records[0]['raw'])
        except ValueError as exc:
            raise ValueError('The predicted query has incompatible fields. Clarify its time scope or additional conditions.') from exc
        guard(query, question)
        return query, records[0]['adapter_sha256']


def wording(query):
    if query['time_scope'] == 'career':
        metric = query['operation'].removeprefix('player_')
        return f"Total Premier League {metric} for {query['player']} across their entire career, including every club."
    if query['time_scope'] == 'unspecified':
        return f"{query['operation'].replace('_', ' ')}; player: {query['player'] or 'not specified'}; team: {query['team'] or 'not specified'}; time scope not specified."
    year = query['season']
    season = f'{year}/{(year+1)%100:02d}'
    if query['operation'] == 'league_champion':
        return f'Which club finished as Premier League champions in {season}?'
    if query['operation'] == 'league_runner_up':
        return f'Which club finished second in the {season} Premier League table?'
    return f"{query['operation'].replace('_', ' ')} in the {season} Premier League; player: {query['player'] or 'none'}; team: {query['team'] or 'none'}."


def executable(query):
    return (query['time_scope'] == 'career' and query['operation'] == 'player_goals') or (
        query['time_scope'] == 'season' and query['operation'] in ('league_champion', 'league_runner_up'))
