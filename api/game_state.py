"""Track mutable game progress without copying immutable question snapshots."""
from copy import deepcopy


class QuestionWindow:
    """Read-only prefix of a frozen deck, retaining its real exhaustion limit.

    Daily commands need past answers, the current question and one lookahead.
    Missing lookahead fails loudly instead of inventing pool exhaustion. This
    object is never serialized: persistence keeps the full database snapshot.
    """
    def __init__(self, prefix, size):
        if not 0 <= len(prefix) <= size:
            raise ValueError('Invalid question window')
        self.prefix=prefix
        self.size=size

    def __len__(self):
        return self.size

    def __getitem__(self, index):
        if not isinstance(index,int):
            raise TypeError('Question windows support indexed access only')
        if index<0:index+=self.size
        if not 0<=index<self.size:raise IndexError(index)
        if index>=len(self.prefix):raise RuntimeError('Question was not loaded in this window')
        return self.prefix[index]


def progress(state):
    return {key: value for key, value in state.items() if key != 'deck'}


def checkpoint(state):
    # Engines may append questions, never edit existing snapshots. PostgreSQL
    # guards independently enforce that contract when a transition is saved.
    return deepcopy(progress(state)), len(state['deck'])
