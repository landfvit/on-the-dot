"""Read-only examples use the same rules and scoring functions as real games."""
from copy import deepcopy

from api.solo_engine import RULES, rewards, shootout


def guide_context():
    rules = deepcopy(RULES)
    examples = []
    cases = (
        ('early', 'Early finish', [True] * 6,
         'An unbeatable lead ends the game early.'),
        ('last', 'Last kick', [True, False] * 4 + [True],
         'Save to win. A goal forces sudden death.'),
        ('sudden', 'Sudden death', [True, False] * 5 + [True, True],
         'After five kicks each, score and save to win.'),
    )
    for code, title, answers, caption in cases:
        state = {'history': [{'correct': answer, 'option_id': '0'} for answer in answers]}
        score = shootout(state)
        slots = max(rules['initial_kicks'], *score['kicks'].values())
        rows = {}
        for side in ('player', 'opponent'):
            taken = [a['goal'] for a in score['attempts'] if a['side'] == side]
            rows[side] = taken + [None] * (slots - len(taken))
        examples.append({'code': code, 'title': title, 'caption': caption, 'score': score, 'rows': rows})
    example_rules = {**rules, 'xp_per_correct': rules['xp_by_difficulty']['medium']}
    reward = rewards({'phase': 'FINISHED', 'difficulty': 'medium', 'rules': example_rules,
                      'history': [{'correct': answer, 'option_id': '0'}
                                  for answer in [True, True, True, False, True, True, True, False]]})
    return {'active_page': 'guide', 'rules': rules, 'examples': examples, 'reward_example': reward}
