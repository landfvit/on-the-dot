"""Coverage policy is separate from metric computation and is frozen with each revision."""
from collections import Counter, defaultdict
import hashlib
import json

POLICY_VERSION = 'coverage-v1'


def evidence_hash(rows):
    content = json.dumps(sorted(rows, key=lambda r: r['fixture_id']), sort_keys=True,
                         default=lambda v: v.isoformat() if hasattr(v, 'isoformat') else str(v))
    return hashlib.sha256(content.encode()).hexdigest()


def season_audits(rows, rules):
    groups = defaultdict(list)
    for row in rows:
        groups[row['season']].append(row)
    audits = []
    for season, matches in sorted(groups.items()):
        rule = next((r for r in rules if r['first_season'] <= season <= r['last_season']), None)
        teams = {r[key] for r in matches for key in ('team_id', 'opponent_id')}
        pairs = Counter((r['team_id'], r['opponent_id']) for r in matches)
        problems = []
        expected = rule['team_count'] * (rule['team_count'] - 1) if rule else None
        if not rule:
            problems.append('unverified_competition_format')
        elif len(teams) != rule['team_count'] or len(matches) != expected:
            problems.append('incomplete_fixture_catalogue')
        if any(a == b or count != 1 for (a, b), count in pairs.items()):
            problems.append('duplicate_or_invalid_pairing')
        if any((b, a) not in pairs for a, b in pairs):
            problems.append('missing_reverse_fixture')
        if any(not r.get('team_facts_valid', True) for r in matches):
            problems.append('inconsistent_team_facts')
        audits.append({'season': season, 'teams': len(teams), 'expected_teams': rule['team_count'] if rule else None,
            'fixtures': len(matches), 'expected_fixtures': expected,
            'finished': sum(r.get('status') == 'FT' for r in matches),
            'results': sum(r['result_valid'] for r in matches),
            'timelines': sum(r['timeline_valid'] for r in matches),
            'scorers': sum(bool(r.get('scorers_valid')) for r in matches),
            'problems': problems, 'catalogue_complete': not problems})
    return audits


def audit_dataset(conn, data, league_id):
    rows = conn.execute('''WITH sides AS (
            SELECT f.*,COUNT(*) OVER (PARTITION BY fixture_id) side_count
            FROM trivia_match_team_facts f WHERE dataset_id=%s AND league_id=%s
        ) SELECT f.season,f.team_id,f.opponent_id,f.status,q.result_valid,q.timeline_valid,p.scorers_valid,
            (f.side_count=2 AND a.team_id IS NOT NULL AND a.opponent_id=f.team_id AND
             a.league_id=f.league_id AND a.season=f.season AND a.match_date=f.match_date AND a.status=f.status AND
             a.goals_for IS NOT DISTINCT FROM f.goals_against AND a.goals_against IS NOT DISTINCT FROM f.goals_for AND
             a.result IS NOT DISTINCT FROM CASE f.result WHEN 'W' THEN 'L' WHEN 'L' THEN 'W' ELSE f.result END) team_facts_valid
        FROM sides f JOIN trivia_match_data_quality q USING(dataset_id,fixture_id)
        LEFT JOIN trivia_player_data_quality p USING(dataset_id,fixture_id)
        LEFT JOIN trivia_match_team_facts a ON a.dataset_id=f.dataset_id AND a.fixture_id=f.fixture_id
            AND a.team_id=f.opponent_id AND NOT a.is_home
        WHERE f.is_home''', (data['dataset_id'], league_id)).fetchall()
    rules = conn.execute('SELECT * FROM trivia_competition_rules WHERE league_id=%s ORDER BY first_season',
                         (league_id,)).fetchall()
    return season_audits(rows, rules)


def enrich_result(conn, data, spec, result):
    if spec.template == 'kit_colour':
        if not data.get('sealed_at'):
            result['coverage']['warnings'].append('unsealed_dataset')
            result['coverage']['publishable']=False
        source=result['context_source']
        result['analysis']={'policy_version':POLICY_VERSION,'engine_version':'kit-colours-v1',
            'evidence_hash':evidence_hash([]),'context_evidence':result['context_evidence'],
            'source':{**source,'name':'Wikimedia Commons kit artwork','url':result['context_evidence'].get('source_url') if result['context_evidence'] else None},
            'verification':'Dominant broad colour family in the shirt torso artwork; excludes collar, background, shorts and socks. Automatic pixel classification, not independent product verification.',
            'seasons':[],'leaderboard':[]}
        if result['context_evidence'] and result['context_evidence'].get('method') in ('shirt-torso-colours-v2','shirt-torso-colours-v3'):
            result['analysis']['engine_version']=result['context_evidence']['method'].replace('shirt-torso-','kit-')
            result['analysis']['verification']='One, two or three substantial broad colour families in the shirt torso artwork; excludes collar, background, shorts and socks. Automatic pixel classification, not independent product verification.'
        return result
    available = data['summary']['leagues'][str(spec.league_id)]['seasons']
    period = spec.period
    selected = (period.seasons if period.mode == 'seasons' else list(range(period.start, period.end + 1))
                if period.mode == 'season_range' else available if period.mode == 'all'
                else sorted({r['season'] for r in result['evidence']}))
    audits = [a for a in audit_dataset(conn, data, spec.league_id) if a['season'] in selected]
    problems = {p for audit in audits for p in audit['problems']}
    if set(selected) != {a['season'] for a in audits}:
        problems.add('incomplete_fixture_catalogue')
    if period.mode != 'dates' and any(a['finished'] != a['fixtures'] for a in audits):
        problems.add('season_not_complete')
    if not data.get('sealed_at'):
        problems.add('unsealed_dataset')
    coverage = result['coverage']
    coverage['warnings'] = sorted(set(coverage['warnings']) | problems)
    coverage['publishable'] = not coverage['warnings']
    unit = ('scoring matches' if spec.goal_filter and spec.goal_filter.count == 'scoring_matches' else 'goals')
    if spec.template in ('comeback_wins', 'most_comeback_wins', 'total_wins'):
        unit = 'wins'
    elif spec.template in ('win_rate', 'conditional_win_rate', 'loss_rate', 'draw_rate'):
        unit = '%'
    elif spec.template in ('goals_per_game', 'points_per_game', 'clean_sheets', 'goals_conceded'):
        unit = {'goals_per_game': 'goals / match', 'points_per_game': 'points / match',
                'clean_sheets': 'clean sheets', 'goals_conceded': 'goals conceded'}[spec.template]
    result['answer']['unit'] = unit
    result['analysis'] = {'policy_version': POLICY_VERSION, 'engine_version': data['engine_version'],
        'evidence_hash': evidence_hash(result['evidence']),
        'source': {'name': 'API-Football', 'url': 'https://www.api-football.com/',
                   'snapshot_id': str(data['dataset_id']), 'source_hash': data['source_hash'],
                   'created_at': data['created_at'].isoformat(), 'sealed_at': data['sealed_at'].isoformat() if data.get('sealed_at') else None},
        'seasons': audits, 'leaderboard': result.get('leaderboard', []),
        'verification': 'Internal consistency checks against the imported provider snapshot; not an independent source verification.'}
    if spec.query_version or spec.opponents or spec.template in ('loss_rate', 'draw_rate', 'goals_per_game', 'points_per_game', 'goals_conceded', 'clean_sheets'):
        result['analysis']['calculation_version'] = 'team-query-v1'
        result['analysis']['summary'] = result.get('summary', {})
    if spec.name_policy != 'exact-v1':
        result['analysis']['name_policy'] = spec.name_policy
    if spec.weather:
        result['analysis']['context_source']=result['context_source']
        result['analysis']['weather_policy']='ERA5 nearest hourly sample within 30 minutes of kickoff; precipitation is the preceding-hour total, not rain observed during play.'
        result['analysis']['source']['name']='API-Football + Open-Meteo ERA5'
        result['analysis']['verification']+=' Weather is a gridded historical reanalysis, not a stadium observation.'
    return result
