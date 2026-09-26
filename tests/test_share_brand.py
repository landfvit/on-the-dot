"""Minimal brand and result previews, with matching light/dark score layouts."""
from html.parser import HTMLParser
from io import BytesIO
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image, ImageChops, ImageDraw

from api.result_shares import card_image
from trivia_app.main import app


class PreviewMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and (attrs.get('property') == 'og:image' or attrs.get('name') == 'twitter:image'):
            self.urls.append(attrs['content'])
        if tag == 'img' and attrs.get('class') == 'game-share-preview':
            self.urls.append(attrs['src'])


class ShareBrandTests(unittest.TestCase):
    def setUp(self):
        card_image.cache_clear()
        self.addCleanup(card_image.cache_clear)

    def result(self, **overrides):
        return dict(dict(label='Solo penalties', status='Won', player='Player',
            opponent='Opponent', score=[4, 2], attempts=[[True]*4, [True, False, True, False]],
            correct=6, total=8, mode='solo', xp=120, guest=False), **overrides)

    def render(self, data=None, theme='light'):
        labels = []
        original = ImageDraw.ImageDraw.text

        def record(draw, xy, value, *args, **kwargs):
            labels.append(str(value))
            return original(draw, xy, value, *args, **kwargs)

        with patch.object(ImageDraw.ImageDraw, 'text', record):
            raw = card_image(json.dumps(data) if data else '', theme)
        return Image.open(BytesIO(raw)), labels

    def test_brand_has_only_centered_symbol_without_text(self):
        image, labels = self.render()
        self.assertEqual(image.size, (1200, 630))
        self.assertEqual(labels, [])
        background = Image.new('RGB', image.size, '#f6f3eb')
        difference = ImageChops.difference(image, background)
        for box in [(0, 0, 1200, 105), (0, 105, 390, 525),
                    (810, 105, 1200, 525), (0, 525, 1200, 630)]:
            self.assertIsNone(difference.crop(box).getbbox())
        symbol = difference.getbbox()
        self.assertIsNotNone(symbol)
        self.assertAlmostEqual((symbol[0] + symbol[2]) / 2, 600, delta=2)
        self.assertAlmostEqual((symbol[1] + symbol[3]) / 2, 315, delta=2)
        self.assertEqual(image.getpixel((452, 190)), (136, 176, 75))

    def test_result_only_has_outcome_score_logo_and_kicks_in_both_themes(self):
        for theme, background in [('light', '#f6f3eb'), ('dark', '#191c1a')]:
            with self.subTest(theme=theme):
                image, labels = self.render(self.result(), theme)
                self.assertEqual(image.size, (1200, 630))
                self.assertEqual(labels, ['WON', '4', ':', '2'])
                difference = ImageChops.difference(image, Image.new('RGB', image.size, background))
                for box in [(0, 0, 1200, 80), (0, 510, 1200, 630),
                            (0, 80, 280, 510), (920, 80, 1200, 510)]:
                    self.assertIsNone(difference.crop(box).getbbox())
                logo = difference.crop((0, 80, 1200, 200)).getbbox()
                self.assertAlmostEqual((logo[0] + logo[2]) / 2, 600, delta=1)
                for x in [364, 408, 452, 496, 704, 748, 792, 836]:
                    self.assertIsNotNone(difference.crop((x-18, 472, x+18, 508)).getbbox())
                self.assertIn((255, 255, 255), image.crop((346, 472, 382, 508)).getdata())
                self.assertIn((255, 111, 97), image.crop((730, 472, 766, 508)).getdata())

    def test_lost_daily_and_long_results_remain_truthful(self):
        _, labels = self.render(self.result(status='Lost', reason='Forfeit'))
        self.assertEqual(labels[0], 'LOST')
        _, labels = self.render(self.result(format='daily_survival', status='Daily score',
            correct=24, attempts=[[], []]))
        self.assertEqual(labels, ['DAILY SCORE', '24 GOALS'])
        short, _ = self.render(self.result(attempts=[[True]*7, [False]*7]))
        long, _ = self.render(self.result(attempts=[[True]*30, [False]*30]))
        self.assertEqual(short.tobytes(), long.tobytes())

    def test_result_endpoint_supports_separate_cached_themes_and_validates_them(self):
        client = TestClient(app)
        with patch('api.result_shares.shared_result', return_value=self.result()) as read:
            light = client.get('/s/'+'a'*32+'/image.png?v=2')
            dark = client.get('/s/'+'a'*32+'/image.png?v=2&theme=dark')
            self.assertEqual(read.call_count, 2)
            self.assertEqual(light.status_code, 200)
            self.assertEqual(dark.status_code, 200)
            self.assertNotEqual(light.content, dark.content)
            self.assertEqual(Image.open(BytesIO(dark.content)).getpixel((0, 0)), (25, 28, 26))
            self.assertEqual(client.get('/s/'+'a'*32+'/image.png?theme=other').status_code, 422)
            self.assertEqual(read.call_count, 2)

    def test_preview_endpoint_and_all_brand_references_use_new_version(self):
        client = TestClient(app)
        response = client.get('/share/brand.png?v=4')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'image/png')
        self.assertEqual(response.content, card_image())
        for path in ['/', '/account', '/how-to-play', '/penalties']:
            markup = PreviewMarkup()
            markup.feed(client.get(path).text)
            self.assertEqual(len(markup.urls), 3)
            self.assertTrue(all(url.endswith('/share/brand.png?v=4') for url in markup.urls))
