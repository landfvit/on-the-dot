import tempfile
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageColor

from api.profile_enrichment import get_team_kits
from kits import source_signature
from kits.renderer import compose_layers, normalize_color, recolor_svg, render_pixel_kit
from kits.vectorizer import image_to_svg_geometry
from src.current_squads_import import validate_current_season


class PixelKitTests(unittest.TestCase):
    def test_rectangle_merging_preserves_every_rgba_pixel(self):
        image = Image.new('RGBA', (5, 5))
        image.paste((255, 0, 0, 255), (0, 0, 3, 3))
        image.paste((0, 0, 255, 128), (3, 1, 5, 4))
        data = image_to_svg_geometry(image)
        rectangles = ET.fromstring('<svg>' + data['geometry'] + '</svg>')
        self.assertEqual(len(rectangles), 2)
        rebuilt = Image.new('RGBA', image.size)
        for rect in rectangles:
            attrs = rect.attrib
            x, y, w, h = [int(attrs[key]) for key in ('x', 'y', 'width', 'height')]
            rgb = ImageColor.getrgb(attrs['fill'])
            alpha = round(float(attrs.get('fill-opacity', 1)) * 255)
            rebuilt.paste((*rgb, alpha), (x, y, x+w, y+h))
        self.assertEqual(image.tobytes(), rebuilt.tobytes())

    def test_base_mask_is_not_recolored(self):
        source = '<svg xmlns="http://www.w3.org/2000/svg" width="38" height="59"><path fill="#FFF" stroke="#000" d="M0 0"/></svg>'
        root = ET.fromstring(recolor_svg(source, 'f00'))
        self.assertEqual(root[0].attrib['fill'], '#ff0000')
        self.assertEqual(root[1].attrib['fill'], '#FFF')
        self.assertEqual(root[1].attrib['stroke'], '#000')

    def test_unknown_color_does_not_silently_become_white(self):
        for color in (None, 'oops', 'ff00000'):
            with self.assertRaises(ValueError):
                normalize_color(color)

    def test_source_pixels_and_colors_survive_composition_and_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pattern.png'
            pattern = Image.new('RGBA', (2, 2))
            pattern.putpixel((1, 1), (255, 255, 255, 255))
            pattern.save(path)
            layer = {'left': 0, 'top': 0, 'width': 2, 'height': 2, 'color': '#123456'}
            image = compose_layers([layer], [path])
            self.assertEqual(image.getpixel((0, 0)), (18, 52, 86, 255))
            self.assertEqual(image.getpixel((1, 1)), (255, 255, 255, 255))
            output = Path(directory) / 'home'
            render_pixel_kit([layer], [path], output, 'Team & Home', ['https://example.com/source'])
            root = ET.parse(output.with_suffix('.svg')).getroot()
            self.assertEqual(root.attrib['shape-rendering'], 'crispEdges')
            with Image.open(output.with_suffix('.png')) as result:
                self.assertEqual(result.size, (400, 540))
                self.assertEqual(result.getpixel((1, 1)), (18, 52, 86, 255))
            with self.assertRaises(ValueError):
                compose_layers([{**layer, 'width': 3}], [path])

    def test_current_roster_cannot_be_imported_into_historical_season(self):
        payload = {'response': [{'league': {'id': 39}, 'seasons': [{'year': 2026, 'current': True}]}]}
        self.assertTrue(validate_current_season(payload, 39, 2026))
        self.assertFalse(validate_current_season(payload, 39, 2025))
        self.assertFalse(validate_current_season(payload, 140, 2026))

    def test_api_rejects_render_after_source_colors_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enrichment = root / 'data/enrichment'
            enrichment.mkdir(parents=True)
            catalog = root / 'data/kits/catalog.json'
            catalog.parent.mkdir()
            image = root / 'web/static/kits/2026/33/home.svg'
            image.parent.mkdir(parents=True)
            image.write_text('<svg/>')
            kit = {'type': 'home', 'label': 'Home', 'layers': [{'color': '#ff0000'}]}
            catalog.write_text(json.dumps({'seasons': {'2026': {'33': {'home': {
                'image_url': '/assets/kits/2026/33/home.svg', 'source_signature': source_signature(kit)
            }}}}}))
            data = {'seasons': {'2026': {'33': {'kits': [kit]}}}}
            with patch('api.profile_enrichment.DATA_DIR', enrichment), patch('api.profile_enrichment.snapshot', return_value=data), patch('api.profile_enrichment.fetch_one', return_value={'team_id': 33}):
                self.assertEqual(get_team_kits(33, 2026)['kits'][0]['render_style'], 'pixel')
                kit['layers'][0]['color'] = '#0000ff'
                self.assertNotIn('image_url', get_team_kits(33, 2026)['kits'][0])
                self.assertNotIn('image_url', get_team_kits(33, 2025)['kits'][0])
