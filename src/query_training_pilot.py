"""Insert a small unreviewed pilot. No generated label is marked human-verified."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from api.database import get_connection
from api.query_training import Annotation,save_annotation
from api.sports_query import normalize

PILOT = {
    'win_rate': ['win rate','percentage of victories','how often did they win','proportion of games won'],
    'total_goals': ['goals scored','scoring total','number of goals','goals for'],
    'unsupported': ['weather forecast','shirt colour','stadium parking fees','ticket availability'],
}


def seed():
    count=0
    with get_connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(84424325)')
        for label,phrases in PILOT.items():
            for index,phrase in enumerate(phrases):
                text=f'Manchester United {phrase} last 5 seasons'
                if conn.execute('SELECT 1 FROM trivia_query_examples WHERE normalized_text=%s',(normalize(text),)).fetchone():
                    continue
                save_annotation(conn,Annotation(query_text=text,phrase=phrase,label=label,
                    family_key=f'pilot-{label}-{index+1}',split=['train','train','validation','test'][index],
                    note='Synthetic pilot draft. Review the metric phrase, label and paraphrase family before confirming.'),
                    'pilot-generator')
                count+=1
    print(f'Created {count} unreviewed pilot drafts; no training or verification performed.')


if __name__=='__main__':
    seed()
