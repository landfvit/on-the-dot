"""Offline pixel-for-pixel verification of published season kit assets."""
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET

from PIL import Image, ImageColor

from . import source_signature
from .catalog import CACHE, MANIFEST, OUTPUT, SNAPSHOT
from .renderer import compose_layers


def audit_season(season):
    teams = json.loads(SNAPSHOT.read_text())['seasons'][str(season)]
    catalog = json.loads(MANIFEST.read_text())['seasons'].get(str(season), {})
    errors = []
    checked = 0
    for ident, team in teams.items():
        for kit in team['kits']:
            kind = kit['type']
            try:
                entry = catalog[ident][kind]
                if entry['source_signature'] != source_signature(kit):
                    raise ValueError('Source signature mismatch')
                paths = [CACHE / (hashlib.sha256(layer['image_url'].encode()).hexdigest() + '.png')
                         for layer in kit['layers']]
                expected = compose_layers(kit['layers'], paths)
                stem = OUTPUT / str(season) / ident / kind
                root = ET.parse(stem.with_suffix('.svg')).getroot()
                if root.attrib.get('viewBox') != '0 0 100 135' or root.attrib.get('shape-rendering') != 'crispEdges':
                    raise ValueError('Unexpected SVG canvas or rendering mode')
                rebuilt = Image.new('RGBA', expected.size)
                for rect in root.findall('{http://www.w3.org/2000/svg}rect'):
                    attrs = rect.attrib
                    x, y, w, h = [int(attrs[key]) for key in ('x', 'y', 'width', 'height')]
                    color = ImageColor.getrgb(attrs['fill'])
                    alpha = round(float(attrs.get('fill-opacity', 1)) * 255)
                    rebuilt.paste((*color, alpha), (x, y, x+w, y+h))
                if rebuilt.tobytes() != expected.tobytes():
                    raise ValueError('SVG pixels differ from source composition')
                with Image.open(stem.with_suffix('.png')) as png:
                    enlarged = expected.resize((400, 540), Image.Resampling.NEAREST)
                    if png.size != enlarged.size or png.convert('RGBA').tobytes() != enlarged.tobytes():
                        raise ValueError('PNG pixels differ from nearest-neighbor export')
                checked += 1
            except (KeyError, OSError, ValueError, ET.ParseError) as error:
                errors.append(f'{ident}/{kind}: {error}')
    return {'season': season, 'teams': len(teams), 'verified_kits': checked,
            'passed': not errors, 'errors': errors}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', type=int, required=True)
    result = audit_season(parser.parse_args().season)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
