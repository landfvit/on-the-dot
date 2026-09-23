"""Build public-only club badges and season metadata from the local game bank."""
import json
from pathlib import Path
import re

import requests

from api.database import get_connection
from api.solo_routes import active_releases

ROOT=Path(__file__).resolve().parents[1]/'trivia_app'/'static'


def main():
    with get_connection() as conn:
        clubs=conn.execute('SELECT c.team_id,c.name,t.logo_url FROM game_clubs c JOIN teams t USING(team_id) ORDER BY c.name').fetchall()
        questions=conn.execute('SELECT question FROM penalty_bank_questions WHERE release_id=ANY(%s)',(active_releases(conn),)).fetchall()
    (ROOT/'clubs').mkdir(exist_ok=True)
    for club in clubs:
        url=club['logo_url']
        if url!=f'https://media.api-sports.io/football/teams/{club["team_id"]}.png':raise ValueError('Unexpected logo origin')
        response=requests.get(url,timeout=20);response.raise_for_status()
        if not response.content.startswith(b'\x89PNG\r\n\x1a\n') or len(response.content)>1000000:raise ValueError('Unexpected badge content')
        (ROOT/'clubs'/f'{club["team_id"]}.png').write_bytes(response.content)
    seasons=sorted({int(a) for r in questions for a,b in re.findall(r'((?:19|20)\d{2})[/\u2013-](\d{2})(?!\d)',r['question']['text']) if int(b)==(int(a)+1)%100})
    # Keep gaps visible instead of claiming every year between min and max.
    groups=[]
    for season in seasons:
        if groups and groups[-1][-1]+1==season:groups[-1].append(season)
        else:groups.append([season])
    label=lambda n:f'{n%100:02d}/{(n+1)%100:02d}'
    ranges=', '.join(label(g[0]) if len(g)==1 else label(g[0])+' - '+label(g[-1]) for g in groups)
    metadata={'season_label':'PL Seasons '+ranges,'seasons':seasons,'clubs':clubs}
    (ROOT/'public_metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=True)+'\n')
    print(f'Exported {len(clubs)} badges; {metadata["season_label"]}')


if __name__=='__main__':main()
