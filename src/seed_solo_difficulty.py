"""Opt-in first editorial sample; other classifications remain unpublished suggestions."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from api.database import get_connection
from api.solo_routes import latest_release

EASY={'ARS-004','CHE-004','EVE-003','MUN-006','TOT-009','WHU-005','IPS-010','SHU-004','LUT-006','MID-008'}
MEDIUM={f'GEN-{n:03}' for n in range(4,14)}
HARD={f'GEN-{n:03}' for n in range(74,84)}


def classify(external_id,topic):
    if external_id in EASY:return 'easy',True,'Initial editorial estimate: recognizable manager or home ground, one fact, four choices. Not empirically calibrated.'
    if external_id in MEDIUM:return 'medium',True,'Initial editorial estimate: season-specific Golden Boot total or shared award, close numerical alternatives. Not empirically calibrated.'
    if external_id in HARD:return 'hard',True,'Initial editorial estimate: season-specific Big Six mini-league leader, combined opponent filter. Not empirically calibrated.'
    difficulty='medium' if topic in {'Stadiums','Managers','Kit manufacturers','Scoring leaders','Golden Boot','Awards','Kits and design'} else 'hard'
    return difficulty,False,'Topic-based suggestion only. Review familiarity, detail, historical context, distractors and ten-second readability before approval.'


def seed(conn):
    conn.execute('SELECT pg_advisory_xact_lock(84424324)')
    release=latest_release(conn)
    if not release:raise ValueError('Publish an audited penalty question release first')
    rows=conn.execute('''SELECT p.question_id,p.question FROM penalty_bank_questions p
        WHERE release_id=%s AND NOT EXISTS(SELECT 1 FROM game_question_difficulty d
        WHERE d.release_id=p.release_id AND d.question_id=p.question_id)''',(release,)).fetchall()
    approved=0
    for row in rows:
        q=row['question'];level,publish,reason=classify(q['source']['external_id'],q['topic'])
        conn.execute('''INSERT INTO game_question_difficulty(release_id,question_id,difficulty,approved,reason,reviewed_by)
            VALUES(%s,%s,%s,%s,%s,'initial-editorial-v1')''',(release,row['question_id'],level,publish,reason))
        approved+=publish
    return {'classified':len(rows),'approved':approved,'pending':len(rows)-approved}


if __name__=='__main__':
    with get_connection() as conn:print(seed(conn))
