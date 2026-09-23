"""Build local pixel SVGs from the existing season-specific Commons snapshots."""
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from . import source_signature
from .commons import request_with_retry
from .renderer import render_pixel_kit

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'data/enrichment/team_kits.json'
CACHE = ROOT / 'data/kits/source_cache'
OUTPUT = ROOT / 'web/static/kits'
MANIFEST = ROOT / 'data/kits/catalog.json'


def source_image(url, request=request_with_retry):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != 'upload.wikimedia.org':
        raise ValueError('Kit assets must come from Wikimedia Commons')
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.png')
    if not path.exists():
        time.sleep(1.1)
        response = request(url)
        CACHE.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(response.content)
        with Image.open(temporary) as image:
            if image.format != 'PNG':
                raise ValueError('Expected a PNG kit pattern')
            image.verify()
        temporary.replace(path)
    return path


def build_season(season, team_id=None):
    source = json.loads(SNAPSHOT.read_text())['seasons'].get(str(season), {})
    if not source:
        raise ValueError(f'No sourced kits for season {season}')
    if team_id is not None and str(team_id) not in source:
        raise ValueError(f'No sourced kits for team {team_id}')
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {'seasons': {}}
    season_output = manifest['seasons'].setdefault(str(season), {})
    errors = []
    rendered = 0
    for ident, team in source.items():
        if team_id is not None and str(team_id) != ident:
            continue
        kits = {}
        for kit in team['kits']:
            kind = kit['type']
            if kind not in ('home', 'away', 'third'):
                continue
            try:
                paths = [source_image(layer['image_url']) for layer in kit['layers']]
                stem = OUTPUT / str(season) / str(int(ident)) / kind
                render_pixel_kit(kit['layers'], paths, stem, f'{ident} {season}/{str(season+1)[-2:]} {kind}',
                                 [layer['source_url'] for layer in kit['layers']])
                kits[kind] = {'image_url': f'/assets/kits/{season}/{ident}/{kind}.svg',
                              'png_url': f'/assets/kits/{season}/{ident}/{kind}.png',
                              'source_signature': source_signature(kit)}
                rendered += 1
            except (ValueError, OSError, RuntimeError) as error:
                errors.append(f'{ident}/{kind}: {error}')
        season_output[ident] = kits
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        temporary = MANIFEST.with_suffix('.tmp')
        temporary.write_text(json.dumps(manifest, indent=2) + '\n')
        temporary.replace(MANIFEST)
        print(f'{season} team {ident}: {len(kits)} local pixel kits', flush=True)
    if errors:
        raise RuntimeError('\n'.join(errors))
    print(f'Finished: {rendered} verified pixel kits', flush=True)
