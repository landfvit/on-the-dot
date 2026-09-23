"""Strict import and deterministic checks for externally authored question banks.

The reference answer and check note are never inputs to the calculation.
Unrecognised wording abstains instead of applying a fuzzy statistical query.
"""
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import unicodedata

VERSION = 'bank-validator-v2'
CLUBS = {
    33: 'Manchester United', 34: 'Newcastle United', 35: 'Bournemouth', 36: 'Fulham',
    37: 'Huddersfield Town', 38: 'Watford', 39: 'Wolverhampton Wanderers', 40: 'Liverpool',
    41: 'Southampton', 42: 'Arsenal', 43: 'Cardiff City', 44: 'Burnley', 45: 'Everton',
    46: 'Leicester City', 47: 'Tottenham Hotspur', 48: 'West Ham United', 49: 'Chelsea',
    50: 'Manchester City', 51: 'Brighton & Hove Albion', 52: 'Crystal Palace',
    55: 'Brentford', 57: 'Ipswich Town', 60: 'West Bromwich Albion', 62: 'Sheffield United',
    63: 'Leeds United', 64: 'Hull City', 65: 'Nottingham Forest', 66: 'Aston Villa',
    70: 'Middlesbrough', 71: 'Norwich City', 75: 'Stoke City', 76: 'Swansea City',
    746: 'Sunderland', 1359: 'Luton Town',
}
ALIASES = {'Newcastle': 34, 'Huddersfield': 37, 'Cardiff': 43, 'Tottenham': 47,
           'Ipswich': 57, 'Sheffield Utd': 62, 'Swansea': 76, 'Luton': 1359,
           'Man United': 33, 'Man Utd': 33, 'Man City': 50, 'Wolves': 39,
           'Spurs': 47, 'Brighton': 51, 'West Ham': 48}
BIG_SIX = {33, 40, 42, 47, 49, 50}


def normalized(value):
    value = unicodedata.normalize('NFKD', str(value)).casefold()
    return ''.join(c for c in value if not unicodedata.combining(c)).replace('–', '-').replace('’', "'").strip()


def canonical(value):
    v = normalized(value)
    for name, ident in {**{name: ident for ident, name in CLUBS.items()}, **ALIASES}.items():
        if v == normalized(name):
            return f'club:{ident}'
    try:
        return str(Decimal(v.rstrip('%')).normalize()) + ('%' if v.endswith('%') else '')
    except Exception:
        return re.sub(r'\s+', ' ', v)


def parse_bank(text):
    sources = {key: {'url': url, 'title': title} for key, url, title in re.findall(
        r'^\[([^\]]+)\]:\s+(https?://\S+)\s+"([^"]*)"\s*$', text, re.M)}
    headers = list(re.finditer(r'^### ((?:[A-Z]+-)+\d{3}) · ([^\n]+)$', text, re.M))
    if not headers:
        raise ValueError('No question entries found')
    items, ids = [], set()
    sections = list(re.finditer(r'^## (.*?) — (\d+) questions\s*$', text, re.M))
    for n, header in enumerate(headers):
        ident, topic = header.groups()
        if ident in ids:
            raise ValueError(f'Duplicate ID: {ident}')
        ids.add(ident)
        body = text[header.end():headers[n+1].start() if n+1 < len(headers) else len(text)]
        fields = {}
        for label, field in [('Question', 'question'), ('Correct answer', 'answer'), ('Check', 'check')]:
            matches = re.findall(rf'^\*\*{label}:\*\*\s*(.+)$', body, re.M)
            if len(matches) != 1 or not matches[0].strip():
                raise ValueError(f'{ident}: expected one {label}')
            fields[field] = matches[0].strip()
        difficulty = re.findall(r'^\*\*Difficulty:\*\*\s*(Easy|Medium|Hard)\s*$', body, re.M)
        if ident.startswith('EM-') and len(difficulty)!=1:
            raise ValueError(f'{ident}: expected one valid Difficulty')
        if difficulty:fields['difficulty']=difficulty[0].lower()
        basis = re.search(r'^\*\*Basis:\*\* (.*?) \*\*Sources?:\*\* (.+)$', body, re.M)
        if not basis:
            raise ValueError(f'{ident}: missing basis/source')
        refs = list(dict.fromkeys(re.findall(r'\[[^\]]+\]\[([^\]]+)\]', basis[2])))
        if not refs or any(ref not in sources for ref in refs):
            raise ValueError(f'{ident}: unresolved source reference')
        section = next((m[1] for m in reversed(sections) if m.start() < header.start()), None)
        if not section:
            raise ValueError(f'{ident}: missing section')
        items.append(dict(id=ident, topic=topic, section=section, **fields, basis=basis[1],
                          sources=[dict(key=ref, **sources[ref]) for ref in refs]))
    counts = Counter(item['section'] for item in items)
    for section in sections:
        if counts[section[1]] != int(section[2]):
            raise ValueError(f'Question count does not match section {section[1]}')
    return items


def question_tokens(text):
    text = normalized(text)
    names = {**{name: ident for ident, name in CLUBS.items()}, **ALIASES}
    for name, ident in sorted(names.items(), key=lambda item: -len(item[0])):
        text = re.sub(r'(?<!\w)' + re.escape(normalized(name)) + r'(?!\w)', f'club{ident}', text)
    return text


def family_key(text):
    text = re.sub(r'club\d+', '<club>', question_tokens(text))
    text = re.sub(r'20\d{2}/\d{2}', '<season>', text)
    text = re.sub(r'\d+(?:\.\d+)?', '<number>', text)
    return text


class CannotCheck(Exception):
    def __init__(self, reason, status='unsupported'):
        self.reason, self.status = reason, status


def percentage(n, d):
    if not d:
        raise CannotCheck('Empty denominator', 'ambiguous')
    return f'{(Decimal(n) * 100 / Decimal(d)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)}%'


def points(rows):
    return sum(3 if r['result'] == 'W' else 1 if r['result'] == 'D' else 0 for r in rows)


def season_label(season):
    return f'{season}/{str(season+1)[-2:]}'


def unique(values):
    values = sorted(set(values))
    if len(values) != 1:
        raise CannotCheck('Expected one answer; database candidates: ' + json.dumps(values), 'ambiguous')
    return values[0]


def highest(values):
    if not values:
        raise CannotCheck('No eligible candidates', 'incomplete')
    maximum = max(values.values())
    return unique([key for key, value in values.items() if value == maximum])


def stat(rows, metric):
    home = [r for r in rows if r['is_home']]
    away = [r for r in rows if not r['is_home']]
    predicates = {
        'away wins': lambda r: not r['is_home'] and r['result'] == 'W',
        'home wins': lambda r: r['is_home'] and r['result'] == 'W',
        'home clean sheets': lambda r: r['is_home'] and r['goals_against'] == 0,
        'away clean sheets': lambda r: not r['is_home'] and r['goals_against'] == 0,
        'draws': lambda r: r['result'] == 'D',
        'scoring draws': lambda r: r['result'] == 'D' and r['goals_for'] > 0,
        'matches in which both teams scored': lambda r: min(r['goals_for'], r['goals_against']) > 0,
        'matches with at least five total goals': lambda r: r['goals_for'] + r['goals_against'] >= 5,
        'wins by at least three goals': lambda r: r['goals_for'] - r['goals_against'] >= 3,
        'wins by exactly one goal': lambda r: r['goals_for'] - r['goals_against'] == 1,
    }
    if metric in predicates:
        return sum(predicates[metric](r) for r in rows)
    if metric == 'home-minus-away points difference': return points(home) - points(away)
    if metric == 'away-minus-home points difference': return points(away) - points(home)
    if metric == 'goal difference': return sum(r['goals_for'] - r['goals_against'] for r in rows)
    if metric in ('away goals', 'goals scored away from home'): return sum(r['goals_for'] for r in away)
    if metric == 'home goals': return sum(r['goals_for'] for r in home)
    raise CannotCheck('Unsupported metric: ' + metric)


class BankEvaluator:
    def __init__(self, facts, standings=(), events=(), player_quality=()):
        self.seasons = defaultdict(list)
        for row in facts:
            self.seasons[row['season']].append(row)
        self.standings = defaultdict(list)
        for row in standings:
            self.standings[row['season']].append(row)
        self.events = defaultdict(list)
        for row in events:
            self.events[row['fixture_id']].append(row)
        self.player_quality = {r['fixture_id']: r for r in player_quality}
        self.coverage = {s: self.audit_season(rows) for s, rows in self.seasons.items()}

    @staticmethod
    def audit_season(rows):
        teams = {r['team_id'] for r in rows}
        fixtures = defaultdict(list)
        for r in rows: fixtures[r['fixture_id']].append(r)
        if len(teams) != 20 or len(rows) != 760 or len(fixtures) != 380:
            return 'Expected 20 teams, 380 fixtures and 760 team perspectives'
        pairs = Counter((r['team_id'], r['opponent_id'], r['is_home']) for r in rows)
        if len(pairs) != 760 or any(n != 1 for n in pairs.values()) or any(
            (t, o, h) not in pairs for t in teams for o in teams - {t} for h in (True, False)):
            return 'Missing or duplicate home/away pairing'
        for sides in fixtures.values():
            a, b = sides if len(sides) == 2 else (None, None)
            if not a or a['team_id'] != b['opponent_id'] or a['opponent_id'] != b['team_id'] or a['is_home'] == b['is_home']:
                return 'Invalid fixture perspectives'
            if a['goals_for'] != b['goals_against'] or a['goals_against'] != b['goals_for']:
                return 'Inconsistent score perspectives'
        for r in rows:
            gf, ga = r['goals_for'], r['goals_against']
            if not r.get('result_valid') or gf is None or ga is None or min(gf, ga) < 0:
                return 'Unfinished or invalid result'
            if r['result'] != ('W' if gf > ga else 'L' if gf < ga else 'D'):
                return 'Result and score disagree'
        return None

    def final_table(self, season):
        table = self.standings[season]
        expected = {r['team_id'] for r in self.seasons[season]}
        if len(table) != 20 or {r['team_id'] for r in table} != expected or {
            r['league_rank'] for r in table} != set(range(1, 21)) or any(r['played_total'] != 38 for r in table):
            raise CannotCheck('Complete final standings unavailable', 'incomplete')
        # Reconcile football totals, but deliberately retain administrative points deductions.
        for row in table:
            matches = [r for r in self.seasons[season] if r['team_id'] == row['team_id']]
            for column, value in [('goals_for_total', sum(r['goals_for'] for r in matches)),
                                  ('goals_against_total', sum(r['goals_against'] for r in matches)),
                                  ('wins_total', sum(r['result'] == 'W' for r in matches)),
                                  ('draws_total', sum(r['result'] == 'D' for r in matches))]:
                if row.get(column) != value:
                    raise CannotCheck('Final standings disagree with snapshot results', 'incomplete')
        return {r['team_id']: r for r in table}

    def check(self, item):
        try:
            result = self.calculate(item['question'])
            status = 'matched' if canonical(item['answer']) in {
                canonical(v) for v in [result['answer'], *result.get('accepted', [])]} else 'conflict'
            if status == 'conflict' and result.get('accepted'):
                known_players = {ev['player_id'] for events in self.events.values() for ev in events
                    if normalized(item['answer']) in {normalized(n) for n in [ev['player_name'] or '', *ev['aliases']]}}
                if not known_players:
                    return dict(status='ambiguous', reason='Database player found, but reference name is not a registered alias; identity review required', **result)
            return dict(status=status, reason='Database calculation agrees' if status == 'matched' else
                        'Reference answer differs from database calculation', **result)
        except CannotCheck as exc:
            return dict(status=exc.status, reason=exc.reason, answer=None)

    def calculate(self, question):
        from api.bank_recognition import calculate
        recognition=calculate(self,question)
        if recognition is not None:return recognition
        q = question_tokens(question)
        matches = list(re.finditer(r'(20\d{2})/(\d{2})', q))
        if not matches or any(int(m[2]) != (int(m[1])+1) % 100 for m in matches):
            raise CannotCheck('Explicit valid season is required')
        seasons = sorted({int(m[1]) for m in matches})
        window = re.search(r'(20\d{2})/\d{2}-(20\d{2})/\d{2}', q)
        if window:
            seasons = list(range(int(window[1]), int(window[2])+1))
        if not seasons or len(seasons) > 30: raise CannotCheck('Invalid season window')
        for s in seasons:
            if s not in self.seasons or self.coverage[s]:
                raise CannotCheck(f'{season_label(s)}: ' + (self.coverage.get(s) or 'Missing season'), 'incomplete')
        rows = [r for s in seasons for r in self.seasons[s]]
        clubs = list(dict.fromkeys(int(i) for i in re.findall(r'club(\d+)', q)))
        team = clubs[0] if clubs else None
        tr = [r for r in rows if r['team_id'] == team]
        if team and not tr: raise CannotCheck('Club absent from selected seasons', 'incomplete')
        shape = re.sub(r'club\d+', 'CLUB', q)
        shape = re.sub(r'20\d{2}/\d{2}', 'SEASON', shape)
        used = tr if team else rows
        detail, accepted = {}, []

        def grouped(selected, key):
            groups = defaultdict(list)
            for row in selected: groups[row[key]].append(row)
            return groups

        def opponent_group(label):
            if label == 'big six clubs': return BIG_SIX
            table = self.final_table(seasons[0])
            if label == 'clubs that finished in the top four':
                return {t for t, r in table.items() if r['league_rank'] <= 4}
            if label == 'clubs that finished in the bottom three':
                return {t for t, r in table.items() if r['league_rank'] >= 18}
            raise CannotCheck('Unknown opponent group')

        def rate(selected):
            detail.update(numerator=sum(r['result'] == 'W' for r in selected), denominator=len(selected))
            return percentage(detail['numerator'], detail['denominator'])

        def score(r): return f"{r['goals_for']}-{r['goals_against']}"
        def venue(selected, v):
            return [r for r in selected if r['is_home'] == (v in ('home', 'at home'))] if v else selected

        m = re.fullmatch(r'what was the win rate of CLUB( at home| away from home)? against (big six clubs|clubs that finished in the (?:top four|bottom three)) in the SEASON premier league, rounded to one decimal place\?', shape)
        multi = re.fullmatch(r'across SEASON-SEASON, what was the (home|away) premier league win rate of CLUB against the other clubs in the fixed big six group, rounded to one decimal place\?', shape)
        mini = re.fullmatch(r'how many premier league points did CLUB earn against (big six clubs|clubs that finished in the (?:top four|bottom three)) in SEASON\?', shape)
        conditional = re.fullmatch(r'what was the win rate of CLUB in SEASON premier league matches in which (.+), rounded to one decimal place\?', shape)
        if m or multi or mini:
            label = m[2] if m else mini[1] if mini else 'big six clubs'
            selected = [r for r in tr if r['opponent_id'] in opponent_group(label)]
            v = m[1].strip() if m and m[1] else multi[1] if multi else None
            selected = venue(selected, v)
            answer = points(selected) if mini else rate(selected)
            detail['selected_matches'] = len(selected)
        elif conditional:
            predicates = {
                'both teams scored': lambda r: min(r['goals_for'], r['goals_against']) > 0,
                'the team kept a clean sheet': lambda r: r['goals_against'] == 0,
                'the team scored exactly two goals': lambda r: r['goals_for'] == 2,
                'the team conceded exactly one goal': lambda r: r['goals_against'] == 1,
                'at least four goals were scored in total': lambda r: r['goals_for'] + r['goals_against'] >= 4,
            }
            if conditional[1] not in predicates: raise CannotCheck('Unknown match condition')
            answer = rate([r for r in tr if predicates[conditional[1]](r)])
        elif re.fullmatch(r'(?:how many premier league clean sheets did CLUB keep against CLUB across SEASON-SEASON|what was the premier league win rate of CLUB against CLUB across SEASON-SEASON, rounded to one decimal place)\?', shape):
            if len(clubs) != 2: raise CannotCheck('Two distinct clubs required')
            selected = [r for r in tr if r['opponent_id'] == clubs[1]]
            if not selected: raise CannotCheck('No meetings in selected window', 'incomplete')
            answer = rate(selected) if 'win rate' in shape else sum(r['goals_against'] == 0 for r in selected)
            detail['selected_matches'] = len(selected)
        elif (m := re.fullmatch(r'what percentage of the premier league (wins recorded|goals scored) by CLUB in SEASON came (at home|away from home), rounded to one decimal place\?', shape)):
            if m[1] == 'wins recorded' and m[2] == 'at home':
                detail.update(numerator=sum(r['result'] == 'W' and r['is_home'] for r in tr), denominator=sum(r['result'] == 'W' for r in tr))
            elif m[1] == 'goals scored' and m[2] == 'away from home':
                detail.update(numerator=sum(r['goals_for'] for r in tr if not r['is_home']), denominator=sum(r['goals_for'] for r in tr))
            else: raise CannotCheck('Unsupported ratio')
            answer = percentage(detail['numerator'], detail['denominator'])
        elif (m := re.fullmatch(r'what was the single most frequent (home|away) premier league scoreline for CLUB in SEASON, writing their goals first\?', shape)):
            counts = Counter(score(r) for r in venue(tr, m[1]))
            answer = highest(counts); detail['frequency'] = counts[answer]
        elif (m := re.fullmatch(r'which club did CLUB beat (\d+)-(\d+) (at home|away from home) in the SEASON premier league\?', shape)):
            answer = CLUBS[unique([r['opponent_id'] for r in venue(tr, m[3]) if score(r) == f'{m[1]}-{m[2]}' and r['result'] == 'W'])]
        elif (m := re.fullmatch(r'which club won (\d+)-(\d+) away at CLUB in the SEASON premier league\?', shape)):
            answer = CLUBS[unique([r['opponent_id'] for r in tr if r['is_home'] and score(r) == f'{m[2]}-{m[1]}' and r['result'] == 'L'])]
        elif (m := re.fullmatch(r"what was the final score of the (home|away) premier league defeat for CLUB against CLUB in SEASON, with CLUB's goals first\?", shape)):
            if len(clubs) != 2 or int(re.findall(r'club(\d+)', q)[-1]) != team:
                raise CannotCheck('Two clubs and matching score perspective required')
            answer = unique([score(r) for r in venue(tr, m[1]) if r['opponent_id'] == clubs[1] and r['result'] == 'L'])
        elif (m := re.fullmatch(r"against which club did CLUB record a (\d+-\d+) home result and a (\d+-\d+) away result in the SEASON premier league, with CLUB's score written first\?", shape)):
            if len(clubs) != 1: raise CannotCheck('Score perspective must match the subject club')
            answer = CLUBS[unique([opp for opp, games in grouped(tr, 'opponent_id').items()
                if any(r['is_home'] and score(r) == m[1] for r in games) and any(not r['is_home'] and score(r) == m[2] for r in games)])]
        elif re.fullmatch(r'which opponent conceded the most goals to CLUB across their two premier league meetings in SEASON\?', shape):
            totals = {o: sum(r['goals_for'] for r in games) for o, games in grouped(tr, 'opponent_id').items()}
            ident = highest(totals); answer = CLUBS[ident]; detail['goals'] = totals[ident]
        elif (m := re.fullmatch(r'(?:which was the only opponent that CLUB managed to (.+)|how many different opponents did CLUB (.+)) in the SEASON premier league\?', shape)):
            pattern = m[1] or m[2]
            predicates = {
                'avoid defeat against in both league meetings': lambda games: all(r['result'] != 'L' for r in games),
                'draw against both home and away': lambda games: all(r['result'] == 'D' for r in games),
                'beat both home and away': lambda games: all(r['result'] == 'W' for r in games),
                'beat both home and away without conceding in either match': lambda games: all(r['result'] == 'W' and r['goals_against'] == 0 for r in games),
            }
            if pattern not in predicates: raise CannotCheck('Unsupported two-match predicate')
            candidates = [opp for opp, games in grouped(tr, 'opponent_id').items() if len(games) == 2 and predicates[pattern](games)]
            answer = CLUBS[unique(candidates)] if m[1] else len(candidates)
            detail['opponents'] = [CLUBS[t] for t in candidates]
        elif (m := re.fullmatch(r'in which season within SEASON-SEASON did CLUB record their (highest goal difference|most .+) in the premier league\?', shape)):
            metric = m[1].removeprefix('highest ').removeprefix('most ')
            totals = {s: stat(games, metric) for s, games in grouped(tr, 'season').items()}
            answer = season_label(highest(totals)); detail['season_totals'] = totals
        elif (m := re.fullmatch(r'which club recorded the (?:most|largest) (.+) in the SEASON premier league\?', shape)):
            totals = {t: stat(games, m[1]) for t, games in grouped(rows, 'team_id').items()}
            winner = highest(totals); answer = CLUBS[winner]; detail['value'] = totals[winner]
        elif shape == 'which club earned the most points in the big six head-to-head mini-league in the SEASON premier league?':
            totals = {t: points([r for r in rows if r['team_id'] == t and r['opponent_id'] in BIG_SIX]) for t in BIG_SIX}
            winner = highest(totals); answer = CLUBS[winner]; detail['points'] = totals[winner]
        elif (m := re.fullmatch(r'how many premier league points did CLUB take from the eventual (champions|runners-up), CLUB, in SEASON\?', shape)):
            table = self.final_table(seasons[0])
            if len(clubs) != 2 or table.get(clubs[1], {}).get('league_rank') != (1 if m[1] == 'champions' else 2):
                raise CannotCheck('Opponent final-position premise disagrees with database', 'conflict')
            answer = points([r for r in tr if r['opponent_id'] == clubs[1]])
        elif (m := re.fullmatch(r'among clubs finishing in the (bottom|top) half, which (scored|conceded) the most goals in the SEASON premier league\?', shape)):
            table = self.final_table(seasons[0])
            totals = {t: sum(r['goals_for' if m[2] == 'scored' else 'goals_against'] for r in games)
                      for t, games in grouped(rows, 'team_id').items() if (table[t]['league_rank'] <= 10) == (m[1] == 'top')}
            answer = CLUBS[highest(totals)]
        elif (m := re.fullmatch(r'(?:which was the only club that|how many clubs) (.+) in the SEASON premier league\?', shape)):
            table = self.final_table(seasons[0]) if 'top half' in m[1] else {}
            predicates = {
                'completed the season without a goalless draw': lambda t, games: all(r['goals_for'] + r['goals_against'] > 0 for r in games),
                'conceded at least 80 goals': lambda t, games: sum(r['goals_against'] for r in games) >= 80,
                'scored at least 70 goals': lambda t, games: sum(r['goals_for'] for r in games) >= 70,
                'earned more points away from home than at home': lambda t, games: stat(games, 'away-minus-home points difference') > 0,
                'kept at least ten clean sheets away from home': lambda t, games: stat(games, 'away clean sheets') >= 10,
                'won more away matches than home matches': lambda t, games: stat(games, 'away wins') > stat(games, 'home wins'),
                'finished with a negative goal difference despite ending in the top half': lambda t, games: table[t]['league_rank'] <= 10 and stat(games, 'goal difference') < 0,
            }
            if m[1] not in predicates: raise CannotCheck('Unsupported season predicate')
            candidates = [t for t, games in grouped(rows, 'team_id').items() if predicates[m[1]](t, games)]
            answer = CLUBS[unique(candidates)] if shape.startswith('which') else len(candidates)
        elif (m := re.fullmatch(r'how many matches in the SEASON premier league finished with (no goals|exactly \d+ total goals)\?', shape)):
            target = 0 if m[1] == 'no goals' else int(re.search(r'\d+', m[1])[0])
            answer = sum(r['is_home'] and r['goals_for'] + r['goals_against'] == target for r in rows)
        elif (m := re.fullmatch(r'which premier league season within SEASON-SEASON had the most (.+)\?', shape)):
            predicates = {'3-3 draws': lambda r: int(r['goals_for'] == r['goals_against'] == 3),
                'away wins': lambda r: int(r['result'] == 'L'), 'home wins': lambda r: int(r['result'] == 'W'),
                'drawn matches': lambda r: int(r['result'] == 'D'),
                'goalless draws': lambda r: int(r['goals_for'] == r['goals_against'] == 0),
                'goals in total': lambda r: r['goals_for'] + r['goals_against'],
                'matches in which both teams scored': lambda r: int(min(r['goals_for'], r['goals_against']) > 0),
                'matches with six or more total goals': lambda r: int(r['goals_for'] + r['goals_against'] >= 6)}
            if m[1] not in predicates: raise CannotCheck('Unsupported season record')
            totals = {s: sum(predicates[m[1]](r) for r in self.seasons[s] if r['is_home']) for s in seasons}
            answer = season_label(highest(totals)); detail['season_totals'] = totals
        elif (m := re.fullmatch(r'by how many points did CLUB finish above CLUB in the SEASON premier league title race\?', shape)):
            table = self.final_table(seasons[0])
            if len(clubs) != 2: raise CannotCheck('Two clubs required')
            answer = table[clubs[0]]['points'] - table[clubs[1]]['points']
        elif shape == 'how many premier league points did champions CLUB drop away from home in SEASON?':
            if self.final_table(seasons[0])[team]['league_rank'] != 1:
                raise CannotCheck('Champion premise disagrees with final table', 'conflict')
            answer = 57 - points(venue(tr, 'away'))
        else:
            try:
                answer, detail = self.simple_count(shape, tr)
            except CannotCheck:
                answer, detail, accepted, used = self.scoring(q, shape, tr, rows, clubs)
        return dict(answer=str(answer), accepted=accepted, details=detail, seasons=seasons,
                    evidence_fixture_ids=sorted({r['fixture_id'] for r in used}),
                    checked_seasons=seasons, validator_version=VERSION)

    def scoring(self, q, shape, tr, rows, clubs):
        top = re.fullmatch(r'who finished as the sole leading premier league goalscorer for CLUB in SEASON\?', shape)
        boot = re.fullmatch(r'what was the golden boot-winning goal tally in the SEASON premier league\?', shape)
        shared = re.fullmatch(r'how many players shared the premier league golden boot in SEASON\?', shape)
        total = re.fullmatch(r'how many premier league goals did (.+) score for club\d+ in 20\d{2}/\d{2}\?', q)
        compare = re.fullmatch(r'who scored more premier league goals in 20\d{2}/\d{2}: (.+) or (.+)\?', q)
        hat = re.fullmatch(r'who scored a hat-trick for CLUB in their (\d+)-(\d+) (home|away) premier league result against CLUB in SEASON\?', shape)
        if not any((top, boot, shared, total, compare, hat)):
            raise CannotCheck('No approved deterministic template for this wording; editorial/source review required')
        selected = tr if top or total or hat else rows
        if hat:
            if len(clubs) != 2: raise CannotCheck('Two clubs required')
            selected = [r for r in tr if r['opponent_id'] == clubs[1] and r['is_home'] == (hat[3] == 'home')
                        and r['goals_for'] == int(hat[1]) and r['goals_against'] == int(hat[2])]
            if len(selected) != 1: raise CannotCheck('Match premise not unique in database', 'ambiguous')
        fixture_ids = {r['fixture_id'] for r in selected}
        invalid = [fid for fid in fixture_ids if not self.player_quality.get(fid, {}).get('scorers_valid')
                   or not self.player_quality.get(fid, {}).get('timeline_valid')]
        if invalid:
            raise CannotCheck(f'Scorer coverage incomplete: {len(invalid)} of {len(fixture_ids)} matches; no partial total used', 'incomplete')
        totals, names, aliases = Counter(), {}, defaultdict(set)
        selected_teams = {r['team_id'] for r in selected}
        for fid in fixture_ids:
            for ev in self.events[fid]:
                if ev['event_type'] != 'Goal' or ev['event_detail'] not in ('Normal Goal', 'Penalty') or ev['team_id'] not in selected_teams:
                    continue
                pid = ev['player_id']
                totals[pid] += 1
                names[pid] = ev['player_name']
                aliases[pid].update([ev['player_name'], *ev['aliases']])
        if not totals: raise CannotCheck('No scorer facts', 'incomplete')
        detail = {'scorer_matches': len(fixture_ids)}
        if boot: return max(totals.values()), detail, [], selected
        if shared: return sum(v == max(totals.values()) for v in totals.values()), detail, [], selected
        if total or compare:
            requested = [total[1]] if total else [compare[1], compare[2]]
            ids = []
            for name in requested:
                matches = [pid for pid, options in aliases.items() if normalized(name) in {normalized(a) for a in options}]
                if len(matches) != 1: raise CannotCheck('Player identity not resolved unambiguously: ' + name, 'incomplete')
                ids.append(matches[0])
            if total: return totals[ids[0]], detail, [], selected
            winner = highest({pid: totals[pid] for pid in ids})
        elif hat:
            winner = unique([pid for pid, count in totals.items() if count >= 3])
        else:
            winner = highest(totals)
        detail.update(goals=totals[winner], player_id=winner)
        return names[winner], detail, sorted(aliases[winner]), selected

    @staticmethod
    def simple_count(shape, rows):
        rules = {
            'in how many premier league matches in SEASON did CLUB fail to score?': lambda r: r['goals_for'] == 0,
            'how many of the premier league draws recorded by CLUB in SEASON were goalless?': lambda r: r['goals_for'] == r['goals_against'] == 0,
            'how many premier league matches involving CLUB in SEASON produced at least five total goals?': lambda r: r['goals_for'] + r['goals_against'] >= 5,
            'how many premier league wins did CLUB achieve by exactly one goal in SEASON?': lambda r: r['goals_for'] - r['goals_against'] == 1,
            'how many premier league wins did CLUB achieve by a margin of at least three goals in SEASON?': lambda r: r['goals_for'] - r['goals_against'] >= 3,
            'how many of the premier league goals scored by CLUB in SEASON came at home?': lambda r: r['goals_for'] if r['is_home'] else 0,
            'how many premier league goals did CLUB concede away from home in SEASON?': lambda r: r['goals_against'] if not r['is_home'] else 0,
            'how many away premier league clean sheets did CLUB keep in SEASON?': lambda r: not r['is_home'] and r['goals_against'] == 0,
            'how many home premier league clean sheets did CLUB keep in SEASON?': lambda r: r['is_home'] and r['goals_against'] == 0,
            'how many away premier league wins did CLUB record in SEASON?': lambda r: not r['is_home'] and r['result'] == 'W',
            'how many of the 19 home premier league matches did CLUB win in SEASON?': lambda r: r['is_home'] and r['result'] == 'W',
            'in how many premier league matches involving CLUB in SEASON did both teams score?': lambda r: min(r['goals_for'], r['goals_against']) > 0,
            'how many premier league defeats did CLUB suffer by exactly one goal in SEASON?': lambda r: r['goals_against'] - r['goals_for'] == 1,
            'how many premier league wins did CLUB record without conceding a goal in SEASON?': lambda r: r['goals_for'] > 0 and r['goals_against'] == 0,
            'how many premier league matches involving CLUB in SEASON contained exactly one goal in total?': lambda r: r['goals_for'] + r['goals_against'] == 1,
            'how many home premier league draws did CLUB record in SEASON?': lambda r: r['is_home'] and r['result'] == 'D',
            'how many away premier league draws did CLUB record in SEASON?': lambda r: not r['is_home'] and r['result'] == 'D',
            'in how many premier league defeats in SEASON did CLUB still score at least one goal?': lambda r: r['result'] == 'L' and r['goals_for'] > 0,
            'in how many premier league matches in SEASON did CLUB concede at least four goals?': lambda r: r['goals_against'] >= 4,
            'in how many premier league matches in SEASON did CLUB score exactly two goals?': lambda r: r['goals_for'] == 2,
        }
        if shape in rules: return sum(rules[shape](r) for r in rows), {}
        if shape == 'what was the difference between home and away premier league points earned by CLUB in SEASON, calculated as home minus away?':
            return stat(rows, 'home-minus-away points difference'), {}
        raise CannotCheck('No approved deterministic template for this wording; editorial/source review required')


def load_evaluator(conn, dataset_id):
    facts = conn.execute('''SELECT f.*,q.result_valid FROM trivia_match_team_facts f
        JOIN trivia_match_data_quality q USING(dataset_id,fixture_id)
        WHERE f.dataset_id=%s AND f.league_id=39''', (dataset_id,)).fetchall()
    standings = conn.execute('SELECT * FROM season_standings WHERE league_id=39').fetchall()
    events = conn.execute('''SELECT * FROM trivia_event_facts WHERE dataset_id=%s AND event_type='Goal' ''', (dataset_id,)).fetchall()
    quality = conn.execute('''SELECT p.*,q.timeline_valid FROM trivia_player_data_quality p
        JOIN trivia_match_data_quality q USING(dataset_id,fixture_id) WHERE dataset_id=%s''', (dataset_id,)).fetchall()
    evaluator = BankEvaluator(facts, standings, events, quality)
    payload = json.dumps(standings, default=str, sort_keys=True)
    return evaluator, {'standings_hash': hashlib.sha256(payload.encode()).hexdigest(), 'standings': standings,
                       'validator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       'recognition_sha256': hashlib.sha256(Path(__file__).with_name('bank_recognition.py').read_bytes()).hexdigest()}
