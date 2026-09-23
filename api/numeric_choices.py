"""Readable numeric distractors, frozen once when a new quiz deck is built."""
from copy import deepcopy
from decimal import Decimal
import re
import secrets

POLICY_VERSION = 'numeric-choices-v2'
NUMBER = re.compile(r'-?\d+(?:\.\d+)?(?:\s*%)?')


def spacing(value, percentage=False):
    if percentage:
        return Decimal(10)
    if value == value.to_integral_value() and 1900 <= value <= 2100:
        return Decimal(2)
    minimum = Decimal(1) if value == value.to_integral_value() else Decimal('0.5')
    target = max(minimum, abs(value) / 10)
    magnitude = Decimal(10) ** target.adjusted()
    return next(magnitude * n for n in (1, 2, 5, 10) if magnitude * n >= target)


def options(answer, *, allow_negative=False, minimum_step=0, accepted=()):
    answer = str(answer)
    if not NUMBER.fullmatch(answer):
        raise ValueError('Expected a numeric answer')
    percentage = answer.endswith('%')
    value = Decimal(answer.rstrip('%').strip())
    if percentage and not 0 <= value <= 100:
        raise ValueError('Percentage outside 0-100')
    step = max(spacing(value, percentage), Decimal(str(minimum_step)))
    lower = Decimal(0) if percentage or (value >= 0 and not allow_negative) else None
    forbidden = {Decimal(str(v).rstrip('%').strip()) for v in accepted if NUMBER.fullmatch(str(v))}
    forbidden.discard(value)

    def valid(candidate):
        return (lower is None or candidate >= lower) and (not percentage or candidate <= 100) and candidate not in forbidden

    rng = secrets.SystemRandom()
    windows = [[value + step * offset for offset in range(-position, 4-position)] for position in range(4)]
    windows = [window for window in windows if all(valid(candidate) for candidate in window)]
    if windows:
        values = rng.choice(windows)
    else:
        candidates = [value + step * offset for offset in range(-20, 21) if offset and valid(value + step * offset)]
        if len(candidates) < 3:
            raise ValueError('Insufficient well-separated numeric alternatives')
        values = [value, *rng.sample(candidates, 3)]
    rng.shuffle(values)
    decimals = max(0, -value.as_tuple().exponent, -step.normalize().as_tuple().exponent)
    suffix = (' %' if ' ' in answer else '%') if percentage else ''
    choices = [{'id': str(i), 'text': answer if candidate == value else f'{candidate:.{decimals}f}{suffix}'}
               for i, candidate in enumerate(values)]
    return choices, str(values.index(value))


def refresh(question):
    """Adapt released numeric choices only before freezing a new run; never alter releases."""
    result = deepcopy(question)
    if len(result['options']) != 4:
        return result
    answer = next(option['text'] for option in result['options'] if option['id'] == result['correct'])
    if not NUMBER.fullmatch(answer):
        return result
    result['options'], result['correct'] = options(answer, allow_negative='difference' in result['text'].lower())
    result['numeric_choice_policy'] = POLICY_VERSION
    return result
