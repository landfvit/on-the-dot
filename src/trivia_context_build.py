"""Freeze existing kit and weather sources without changing football snapshots."""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from psycopg.types.json import Jsonb
from api.database import get_connection
from kits.catalog import CACHE, SNAPSHOT, source_image
from kits.colours import METHOD, dominant_colour, colour_description
from kits.renderer import compose_layers
from kits import source_signature
from kits.commons import session
import requests


def bounded_download(url):
    response=session.get(url,timeout=30)
    response.raise_for_status()
    return response


def serial(value):
    if isinstance(value,datetime): return value.astimezone(timezone.utc).isoformat()
    if isinstance(value,date): return value.isoformat()
    raise TypeError(type(value).__name__)


def kit_records(fetch_seasons=(),colour_version='v1'):
    catalogue=json.loads(SNAPSHOT.read_text())
    result={}
    downloads_paused=False
    for season,teams in sorted(catalogue['seasons'].items()):
        for team_id,team in sorted(teams.items()):
            for kit in team['kits']:
                key=f"{season}:{team_id}:{kit['type']}"
                record={'season':int(season),'team_id':int(team_id),'kit_type':kit['type'],
                    'source_url':team['source_url'],'retrieved_at':catalogue['retrieved_at'],
                    'source_signature':source_signature(kit),'method':'shirt-torso-colours-'+colour_version,
                    'status':'missing_pixels','colour':None,'palette':[]}
                bodies=[l for l in kit['layers'] if l['left']==31 and l['top']==0 and l['width']==38 and l['height']==59]
                if len(bodies)==1:
                    body=bodies[0];url=body['image_url']
                    path=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.png')
                    if not path.exists() and int(season) in fetch_seasons and not downloads_paused:
                        try:
                            path=source_image(url,request=bounded_download)
                            print(f'Cached shirt body: {key}',flush=True)
                        except requests.RequestException as error:
                            downloads_paused=True
                            print(f'Downloads paused: {error}. Remaining kits use cached pixels only.',flush=True)
                    if path.exists():
                        image=compose_layers([{**body,'left':0,'top':0}],[path],38,59)
                        record.update(dominant_colour(image) if colour_version=='v1' else colour_description(image,colour_version))
                        record['body_source_url']=body['source_url']
                        record['pixel_sha256']=hashlib.sha256(image.tobytes()).hexdigest()
                        stem=record['pixel_sha256']
                        output=ROOT/'web/static/trivia-kits'/f'{stem}.png'
                        output.parent.mkdir(parents=True,exist_ok=True)
                        if not output.exists(): image.save(output)
                        record['image_url']=f'/assets/trivia-kits/{stem}.png'
                result[key]=record
    return result


def build(fetch_seasons=(),colour_version='v1'):
    kits=kit_records(fetch_seasons,colour_version)
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        data=conn.execute('SELECT dataset_id FROM trivia_datasets WHERE sealed_at IS NOT NULL ORDER BY created_at DESC LIMIT 1').fetchone()
        if not data: raise ValueError('Build and seal a football snapshot first')
        weather=conn.execute('''SELECT w.*,f.season FROM trivia_match_team_facts f
            JOIN fixtures live ON live.fixture_id=f.fixture_id AND live.match_date=f.match_date
                AND live.home_team_id=f.team_id AND live.away_team_id=f.opponent_id
            JOIN fixture_weather w ON w.fixture_id=f.fixture_id AND w.kickoff_at=f.match_date AND w.venue_id=live.venue_id
            WHERE f.dataset_id=%s AND f.is_home AND f.status='FT' ORDER BY f.fixture_id''',(data['dataset_id'],)).fetchall()
        payload=json.loads(json.dumps({'kits':kits,'weather':{str(w['fixture_id']):w for w in weather}},default=serial))
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        previous=conn.execute('SELECT context_id,summary FROM trivia_context_snapshots WHERE dataset_id=%s AND source_hash=%s',
            (data['dataset_id'],digest)).fetchone()
        if previous: return previous
        summary={'kit_records':len(kits),'kit_statuses':dict(Counter(k['status'] for k in kits.values())),
            'kit_seasons':sorted({k['season'] for k in kits.values()}),
            'weather_records':len(weather),'weather_seasons':dict(Counter(str(w['season']) for w in weather))}
        context_id=uuid4()
        conn.execute('INSERT INTO trivia_context_snapshots(context_id,dataset_id,source_hash,method,summary,payload) VALUES (%s,%s,%s,%s,%s,%s)',
            (context_id,data['dataset_id'],digest,'context-v1',Jsonb(summary),Jsonb(payload)))
    return {'context_id':context_id,'summary':summary}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-kit-seasons',nargs='+',type=int,default=[],help='Explicitly download missing Commons body patterns for these seasons only')
    parser.add_argument('--colour-version',choices=['v1','v2','v3'],default='v1')
    args=parser.parse_args()
    print(json.dumps(build(args.fetch_kit_seasons,args.colour_version),default=str,indent=2))
