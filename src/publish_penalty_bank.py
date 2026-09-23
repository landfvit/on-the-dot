"""Explicitly release an audited, user-approved reference bank to unranked penalties."""
import argparse
from collections import Counter
import json
import os
from uuid import UUID,uuid4

from psycopg.types.json import Jsonb
from api.database import get_connection
from api.penalty_bank import CHOICE_VERSION, answer_pools, eligible, make_options, released_question

RECOGNITION_CHOICE_VERSION='bank-choices-v3'


def publish(conn, run_id, recognition=False):
    from api import bank_choices
    from api.bank_curation import section_code,game_topic
    from api.solo_topics import SOURCE_TOPIC
    version=RECOGNITION_CHOICE_VERSION if recognition else CHOICE_VERSION
    conn.execute('SELECT pg_advisory_xact_lock(84424329)')
    existing=conn.execute('SELECT release_id,question_count FROM penalty_bank_releases WHERE validation_run_id=%s AND choice_version=%s',
        (run_id,version)).fetchone()
    if existing: return {**existing,'reused':True}
    rows=conn.execute('''SELECT q.question_id,q.content,c.result FROM trivia_bank_questions q
        JOIN trivia_bank_checks c USING(question_id) WHERE c.run_id=%s ORDER BY q.external_id''',(run_id,)).fetchall()
    if not rows: raise ValueError('Audit not found or empty')
    accepted=[r for r in rows if eligible(r['result'])]
    if recognition:pools,clubs=bank_choices.pools_for([r['content'] for r in accepted])
    else:pools=answer_pools([r['content'] for r in accepted])
    release_id=uuid4()
    output=[]
    for row in accepted:
        item={**row['content'],'accepted':row['result'].get('accepted',[])}
        question=released_question(item,row['result'],release_id,row['question_id'])
        question['options'],question['correct']=bank_choices.options(item,pools,clubs) if recognition else make_options(item,pools)
        if recognition:
            question['source_topic']=item['topic'];question['topic']=game_topic(item)
            if question['topic'] not in SOURCE_TOPIC:raise ValueError('Unmapped topic: '+question['topic'])
            if item.get('difficulty') not in {'easy','medium','hard'}:raise ValueError('Missing editorial difficulty')
        output.append((release_id,row['question_id'],section_code(item['id']),item['section'],Jsonb(question)))
    conn.execute('INSERT INTO penalty_bank_releases VALUES(%s,%s,%s,%s,TRUE,%s,DEFAULT)',
        (release_id,run_id,version,os.getenv('TRIVIA_EDITOR_USERNAME') or 'local-owner',len(output)))
    with conn.cursor() as cur:
        cur.executemany('INSERT INTO penalty_bank_questions VALUES(%s,%s,%s,%s,%s)',output)
        if recognition:
            cur.executemany('''INSERT INTO game_question_difficulty
                (release_id,question_id,difficulty,approved,reason,reviewed_by) VALUES(%s,%s,%s,TRUE,%s,%s)''',
                [(release_id,r['question_id'],r['content']['difficulty'].lower(),
                  'Owner-approved source difficulty; provisional editorial label, not empirically calibrated.',
                  'owner-authorized:easy-medium-v1') for r in accepted])
    return {'release_id':release_id,'question_count':len(output),'excluded':len(rows)-len(output),
            'sections':dict(Counter(r[3] for r in output)),'reused':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=UUID,required=True)
    parser.add_argument('--recognition',action='store_true',help='Preserve explicit options and approve supplied editorial difficulty')
    parser.add_argument('--confirm-user-attested',action='store_true',required=True,
        help='Owner authorizes reference answers even where database validation is unavailable')
    args=parser.parse_args()
    with get_connection() as conn: result=publish(conn,args.run,args.recognition)
    print(json.dumps(result,default=str,indent=2))
