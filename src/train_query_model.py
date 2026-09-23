"""Train a local CPU metric classifier from latest human-verified annotations."""
import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from psycopg.types.json import Jsonb
from api.database import get_connection
from src.query_model import train


def run_training(output):
    with get_connection() as conn:
        rows = conn.execute('''SELECT e.query_text,a.annotation_id,a.example_id,a.revision,a.phrase,a.label,
            a.family_key,f.split,a.reviewed_by,a.reviewed_at FROM trivia_query_examples e
            JOIN LATERAL (SELECT * FROM trivia_query_annotations WHERE example_id=e.example_id ORDER BY revision DESC LIMIT 1) a ON TRUE
            JOIN trivia_query_families f USING(family_key) WHERE a.reviewed_at IS NOT NULL ORDER BY a.annotation_id LIMIT 10001''').fetchall()
    result = train(rows)
    model_id = uuid4()
    with get_connection() as conn:
        conn.execute('''INSERT INTO trivia_query_model_runs(model_id,dataset_hash,corpus,manifest,report,artifact)
            VALUES (%s,%s,%s,%s,%s,%s)''',(model_id,result['dataset_hash'],*[Jsonb(result[k]) for k in ('corpus','manifest','report','artifact')]))
    directory = output/model_id.hex
    directory.mkdir(parents=True,mode=0o700)
    for name in ('manifest','report','artifact'):
        target = directory/(name+'.json')
        target.write_text(json.dumps(result[name],indent=2,sort_keys=True)+'\n')
        target.chmod(0o600)
    return {'model_id':str(model_id),'output':str(directory),
        'validation_accuracy':result['report']['validation']['accuracy'],
        'test_accuracy':result['report']['test']['accuracy'],'deployed':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'data'/'private'/'query-models')
    args = parser.parse_args()
    try:
        print(json.dumps(run_training(args.output),indent=2))
    except ValueError as error:
        parser.exit(2,str(error)+'\n')


if __name__=='__main__':
    main()
