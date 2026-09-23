"""Audit every Commons PL gallery, retaining missing clubs and missing sets."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit,unquote,quote,parse_qs

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import requests
from kits.catalog import CACHE,source_image
from kits.commons import session,COMMONS_API
from kits.renderer import compose_layers
from kits.colours import COLOURS,colour_family,colour_description
from src.profile_enrichment_import import KitParser

RESEARCH=ROOT/'data/kits/research'
REPORTS=ROOT/'reports/kits'


def save_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)


def fetch(params):
    response=session.get(COMMONS_API,params={'format':'json',**params},timeout=30)
    response.raise_for_status()
    data=response.json()
    if 'error' in data: raise ValueError(str(data['error']))
    return data


def inventory(refresh=False):
    path=RESEARCH/'inventory.json'
    if path.exists() and not refresh:return json.loads(path.read_text())
    result=[];continuation={}
    while True:
        data=fetch({'action':'query','list':'categorymembers','cmtitle':'Category:Premier League kits','cmlimit':100,**continuation})
        result.extend(data['query']['categorymembers'])
        continuation=data.get('continue')
        if not continuation:break
        time.sleep(2)
    result={'retrieved_at':datetime.now(timezone.utc).isoformat(),'source_url':'https://commons.wikimedia.org/wiki/Category:Premier_League_kits','pages':result}
    save_json(path,result);return result


def collect_pages(index,offline=False,fallback_pages=()):
    pages=[];errors=[];paused=offline
    fallback={p['season']:p for p in fallback_pages}
    for item in index['pages']:
        if not re.fullmatch(r'\d{4}\u2013\d{2,4} Premier League kits',item['title']):continue
        year=int(item['title'][:4]);path=RESEARCH/'pages'/f'{year}.json'
        if path.exists(): pages.append(json.loads(path.read_text()));continue
        if year in fallback:pages.append(fallback[year]);continue
        if paused:
            errors.append({'season':year,'reason':'requests_paused'});continue
        try:
            time.sleep(10)
            data=fetch({'action':'parse','pageid':item['pageid'],'prop':'text|sections|revid'})['parse']
            data['season']=year;data['retrieved_at']=datetime.now(timezone.utc).isoformat()
            save_json(path,data);pages.append(data)
            print(f'Gallery {year}: {len(data["sections"])} sections',flush=True)
        except (requests.RequestException,ValueError) as error:
            paused=True;errors.append({'season':year,'reason':str(error)})
            print(f'Gallery requests paused: {error}',flush=True)
    return pages,errors


def local_pages():
    from api.database import fetch_all
    names={str(r['team_id']):r['team_name'] for r in fetch_all('SELECT team_id,team_name FROM teams')}
    catalogue=json.loads((ROOT/'data/enrichment/team_kits.json').read_text())
    result=[]
    for season,teams in catalogue['seasons'].items():
        sources={t['source_url'] for t in teams.values()}
        if len(sources)!=1:raise ValueError('Local season has mixed source revisions')
        revision=int(parse_qs(urlsplit(next(iter(sources))).query)['oldid'][0])
        result.append({'season':int(season),'revid':revision,'retrieved_at':catalogue['retrieved_at'],
            'local_teams':[(names[ident],team['kits']) for ident,team in teams.items()]})
    return result


class GalleryParser(KitParser):
    def handle_endtag(self,tag):
        if tag=='td' and self.kit is not None and self.club.strip().lower() in ('home','away','third'):
            name=self.kit['label'].strip()
            if name and self.kit['layers']:
                self.kit['type']=self.club.strip().lower()
                self.teams[name].append(self.kit)
            self.kit=None
        super().handle_endtag(tag)


def parse_page(page):
    if 'local_teams' in page:return page['local_teams']
    parser=GalleryParser();parser.feed(page['text']['*'])
    # Club sections are H3, unlike the season H2 and related-links footer.
    names=[s['line'] for s in page['sections'] if s['level']=='3']
    if not names and any(s['line'].lower()=='home' for s in page['sections']):
        names=list(parser.teams)
    if not names:
        raise ValueError(f'No club sections in gallery {page["season"]}')
    corrections=json.loads((RESEARCH/'roster_corrections.json').read_text())
    aliases=corrections['spelling'].get(str(page['season']),{})
    clubs={}
    for name in names:
        clubs.setdefault(aliases.get(name,name),[]).extend(parser.teams.get(name,[]))
    missing=corrections['missing_clubs'].get(str(page['season']))
    if missing:clubs.setdefault(missing['team'],[])
    return sorted(clubs.items())


def measure(kit,download=False):
    bodies=[l for l in kit['layers'] if l['left']==31 and l['top']==0 and l['width']==38 and l['height']==59]
    distinct={json.dumps(b,sort_keys=True):b for b in bodies}
    if len(distinct)!=1:return {'status':'ambiguous_source_layout','colours':[],'label':None}
    body=next(iter(distinct.values()));url=body['image_url']
    path=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.png')
    if download and not path.exists():
        def one_request(url):
            response=session.get(url,timeout=30);response.raise_for_status();return response
        path=source_image(url,request=one_request)
    record={'body_source_url':'https://commons.wikimedia.org/wiki/File:'+quote(unquote(urlsplit(url).path.rsplit('/',1)[-1])),
        'image_url':url,'base_hex':body['color'],
        'status':'missing_pixels','colours':[],'label':None}
    if body['color']!='transparent':
        from PIL import ImageColor
        key=colour_family(ImageColor.getrgb(body['color']))
        record['declared_base_hint']=COLOURS[key][0]
    if path.exists():
        image=compose_layers([{**body,'left':0,'top':0}],[path],38,59)
        record.update(colour_description(image,'v3'))
        record['pixel_sha256']=hashlib.sha256(image.tobytes()).hexdigest()
    return record


def create_records(pages,download_limit=0,download_delay=10,download_errors=None):
    if download_limit<0 or download_delay<5:
        raise ValueError('Use a nonnegative download limit and at least five seconds between requests')
    if download_errors is None:download_errors=[]
    rows=[];downloads=0;paused=False
    for page in sorted(pages,key=lambda p:p['season'],reverse=True):
        for name,kits in parse_page(page):
            row={'season':page['season'],'team':name,'source_url':f'https://commons.wikimedia.org/w/index.php?oldid={page["revid"]}',
                'retrieved_at':page['retrieved_at'],'kits':{}}
            for kind in ('home','away','third'):
                candidates=[k for k in kits if k['type']==kind]
                if not candidates:
                    result={'status':'not_listed','label':None,'colours':[]}
                elif len(candidates)!=1:
                    result={'status':'multiple_source_variants','label':None,'colours':[]}
                else:
                    result=measure(candidates[0])
                    if result['status']=='missing_pixels' and downloads<download_limit and not paused:
                        try:
                            time.sleep(download_delay)
                            result=measure(candidates[0],download=True);downloads+=1
                            print(f'Pixels {downloads}: {page["season"]} {name} {kind}',flush=True)
                        except requests.RequestException as error:
                            paused=True
                            response=error.response
                            download_errors.append({'season':page['season'],'team':name,'kit_type':kind,
                                'status_code':response.status_code if response is not None else None,
                                'retry_after':response.headers.get('Retry-After') if response is not None else None,
                                'reason':str(error)})
                            print(f'Pixel requests paused: {error}. Cached data retained; no further requests.',flush=True)
                row['kits'][kind]=result
            rows.append(row)
    return rows


def cell(record):
    if record['status']=='available':return record['label']
    if record['status']=='not_listed':return 'Not listed'
    if record['status']=='missing_pixels':
        hint=record.get('declared_base_hint')
        return f'Unverified (base: {hint})' if hint else 'Image not analysed'
    return 'Needs review'


def export(index,pages,rows,errors,download_errors=()):
    REPORTS.mkdir(parents=True,exist_ok=True)
    counts=Counter(k['status'] for row in rows for k in row['kits'].values())
    summary={'created_at':datetime.now(timezone.utc).isoformat(),'method':'shirt-torso-colours-v3',
        'season_pages':len(pages),'team_seasons':len(rows),'kit_statuses':dict(counts),'fetch_errors':errors,
        'missing_galleries':[e['season'] for e in errors], 'pixel_download_errors':list(download_errors)}
    save_json(REPORTS/'pl_kit_colours.json',{'summary':summary,'inventory':index,'rows':rows})
    with (REPORTS/'pl_kit_colours.csv').open('w',newline='',encoding='utf-8-sig') as output:
        writer=csv.writer(output);writer.writerow(['season','team','home','away','third','home_status','away_status','third_status','source_url'])
        for row in rows:
            writer.writerow([f'{row["season"]}/{str(row["season"]+1)[-2:]}',row['team'],
                *[cell(row['kits'][k]) for k in ('home','away','third')],
                *[row['kits'][k]['status'] for k in ('home','away','third')],row['source_url']])
    lines=['# Premier League: Shirt Colours by Season','',
        f'Generated: {summary["created_at"]}', '',
        '[Gallery inventory](https://commons.wikimedia.org/wiki/Category:Premier_League_kits)', '',
        f'{len(pages)} season galleries; {len(rows)} team-season rows; {counts["available"]} classified sets.', '',
        'Scope: broad colours in the interior shirt body, not shorts, socks or sleeve-only colours. '
        'Two/three substantial colours are combined. Results are algorithmic descriptions of the artwork, not human-verified product records.', '',
        'Not listed = this gallery does not list that set; it does NOT prove the club had no third kit. '
        'Unverified (base: ...) = a declared background hint only, not a confirmed dominant colour. '
        'Image not analysed = source artwork exists but pixels are not cached. Needs review = ambiguous layout or palette.', '',
        'Gallery presence does not establish complete coverage. The 1992/93-1998/99 seasons are not in this category; '
        'this does not rule out club-specific images elsewhere on Commons. 2026/27 is an ongoing season.', '',
        'Roster corrections: [Sunderland 2000/01](https://en.wikipedia.org/wiki/2000%E2%80%9301_FA_Premier_League#League_table), '
        '[Charlton 2002/03](https://en.wikipedia.org/wiki/2002%E2%80%9303_FA_Premier_League#League_table), '
        '[Bolton 2003/04](https://en.wikipedia.org/wiki/2003%E2%80%9304_FA_Premier_League#League_table) '
        'are included even though their club headings are absent from the kit galleries. Aston Vila/Villa is merged in 2007/08; Tottenham Hotpsur/Hotspur is corrected in 2008/09 and 2011/12. No kit colours are inferred by these corrections.', '',
        '## Coverage','', '| Season | Teams | Listed sets | Classified | Not listed | Needs pixels / review |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    seasons=sorted({r['season'] for r in rows},reverse=True)
    for year in seasons:
        group=[r for r in rows if r['season']==year];c=Counter(k['status'] for r in group for k in r['kits'].values())
        lines.append(f'| {year}/{str(year+1)[-2:]} | {len(group)} | {3*len(group)-c["not_listed"]} | {c["available"]} | {c["not_listed"]} | {3*len(group)-c["available"]-c["not_listed"]} |')
    if errors:
        lines.extend(['','Unfetched galleries: '+', '.join(f'{e["season"]}/{str(e["season"]+1)[-2:]}' for e in errors)+'. They are present in the Commons inventory but are not represented as complete data below.'])
    for year in seasons:
        group=[r for r in rows if r['season']==year]
        lines.extend(['',f'## {year}/{str(year+1)[-2:]}','',f'[Commons source revision]({group[0]["source_url"]})','',
            '| Team | Home | Away | Third |','| --- | --- | --- | --- |'])
        for row in group:
            lines.append('| '+' | '.join([row['team'],*[cell(row['kits'][k]) for k in ('home','away','third')]])+' |')
    if errors:lines.extend(['','## Fetch Errors','',*['- '+json.dumps(e) for e in errors]])
    if download_errors:lines.extend(['','## Pixel Download Errors','',*['- '+json.dumps(e) for e in download_errors]])
    (REPORTS/'pl_kit_colours.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download-limit',type=int,default=0)
    parser.add_argument('--download-delay',type=float,default=10,help='Seconds between pixel requests (minimum five)')
    parser.add_argument('--offline',action='store_true',help='Use downloaded pages and existing season snapshots only')
    args=parser.parse_args()
    index=inventory();pages,errors=collect_pages(index,args.offline,local_pages())
    download_errors=[]
    rows=create_records(pages,0 if args.offline or errors else args.download_limit,args.download_delay,download_errors)
    export(index,pages,rows,errors,download_errors)
