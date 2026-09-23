"""Publication rules separate from factual verification and supplied answers."""
from api.trivia_bank_engine import normalized,canonical


def text_key(text):return ' '.join(normalized(text).split())


def exclusion(item):
    if item['topic']=='League essentials':
        return 'Trivial football/league rule: excluded at owner request'
    return None


def section_code(external_id):return external_id.split('-')[-2]


def game_topic(item):
    if item['topic']!='Season landmarks':return item['topic']
    q=normalized(item['question'])
    if any(t in q for t in ('cup','champions league','europa league','conference league','community shield','european competition','uefa competition','play-off final','which competition')):
        return 'Cup history'
    if 'shirt' in q or 'sponsored' in q:return 'Kits and design'
    if 'manager' in q:return 'Managers'
    if 'home ground' in q:return 'Home grounds'
    if 'which country' in q:return 'Club identity'
    if 'which half of the table' in q:return 'Season comparison'
    if any(t in q for t in ('loan','moved to','joined','supplied both')):return 'Transfers and loans'
    if canonical(item.get('answer','')).startswith('club:') or any(q.startswith(t) for t in ('which club','which team','which opponent','against which','in 2019/20, was')):
        return 'Match recognition'
    return 'Player milestones'
