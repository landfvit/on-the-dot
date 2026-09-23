"""Meaning-preserving aliases for league-wide questions, without guessing a club.

Only complete phrases with one explicit season match. Extra opponent, venue,
time-window or score conditions are never stripped to obtain a simpler question.
The returned wording is executed by the existing bank evaluator and quality gates.
"""
import re

from api.trivia_bank_engine import normalized

LEAGUE = r'(?:the )?(?:(?:english )?premier league|epl|pl)'
SUBJECT = r'(?:who|which (?:club|team))'
SEASON = r'(?P<season>20\d{2}/\d{2})'
METRICS = r'(?:draws|home wins|away wins|home clean sheets|away clean sheets|home goals|away goals|scoring draws)'

RULES = [
    (rf'{SUBJECT} (?:won|has won) {LEAGUE}(?: title)?', 'Which club finished as Premier League champions in {season}?'),
    (rf'{SUBJECT} (?:was|were|became|finished as) (?:the )?(?:champions?|winners?) (?:of|in) {LEAGUE}', 'Which club finished as Premier League champions in {season}?'),
    (rf'{SUBJECT} (?:was|were|became|finished as) {LEAGUE} (?:champions?|winners?)', 'Which club finished as Premier League champions in {season}?'),
    (rf'{SUBJECT} finished (?:first|top) in {LEAGUE}(?: table)?', 'Which club finished as Premier League champions in {season}?'),
    (rf'{SUBJECT} finished (?:second|2nd) in {LEAGUE}(?: table)?', 'Which club finished second in the {season} Premier League table?'),
    (rf'{SUBJECT} (?:was|were|finished as) (?:the )?runners?-up (?:in|of) {LEAGUE}', 'Which club finished second in the {season} Premier League table?'),
    (rf'{SUBJECT} (?:was|were|finished as) {LEAGUE} runners?-up', 'Which club finished second in the {season} Premier League table?'),
    (rf'{SUBJECT} (?:had|recorded|finished with|kept) the most (?P<metric>{METRICS}) in {LEAGUE}', 'Which club recorded the most {metric} in the {season} Premier League?'),
    (rf'which (?:premier league|epl|pl) (?:club|team) (?:had|recorded|kept) the most (?P<metric>{METRICS})', 'Which club recorded the most {metric} in the {season} Premier League?'),
    (rf'{SUBJECT} drew the most (?:games|matches) in {LEAGUE}', 'Which club recorded the most draws in the {season} Premier League?'),
    (r'which (?:premier league|epl|pl) (?:club|team) drew the most (?:games|matches)', 'Which club recorded the most draws in the {season} Premier League?'),
    (rf'how many (?:games|matches) in {LEAGUE} (?:ended|finished) (?:0-0|goalless|with no goals)', 'How many matches in the {season} Premier League finished with no goals?'),
    (r'how many (?:premier league|epl|pl) (?:games|matches) (?:ended|finished) (?:0-0|goalless|with no goals)', 'How many matches in the {season} Premier League finished with no goals?'),
    (rf'what was the golden boot-winning goal tally in {LEAGUE}', 'What was the Golden Boot-winning goal tally in the {season} Premier League?'),
]


def league_question(question):
    text = re.sub(r'\s+', ' ', normalized(question)).rstrip('?.!').strip()
    if len(re.findall(r'20\d{2}/\d{2}', text)) != 1:
        return None
    # Season suffix, prefix, or a season embedded in the competition name.
    suffix = re.fullmatch(rf'(?P<body>.+?) (?:in|during|for) (?:the )?(?:season )?{SEASON}(?: season)?', text)
    prefix = re.fullmatch(rf'(?:in|during|for) (?:the )?(?:season )?{SEASON}(?: season)?,? (?P<body>.+)', text)
    embedded = re.search(rf'(?:the )?{SEASON} (?:(?:english )?premier league|epl|pl)(?: season)?\b', text)
    if suffix or prefix:
        match = suffix or prefix
        body, season = match['body'], match['season']
    elif embedded:
        season = embedded['season']
        body = text[:embedded.start()] + 'the premier league' + text[embedded.end():]
    else:
        return None
    start, end = map(int, season.split('/'))
    if end != (start + 1) % 100:
        return None
    for pattern, canonical in RULES:
        if match := re.fullmatch(pattern, body):
            return canonical.format(season=season, **match.groupdict())
    return None
