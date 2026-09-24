import unittest
from html.parser import HTMLParser

from fastapi.testclient import TestClient
from trivia_app.main import app


class HeaderParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_header = False
        self.controls = []
        self.brand_images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'header' and attrs.get('class') == 'points-header':
            self.in_header = True
        if self.in_header and tag in ('a', 'button', 'nav', 'form'):
            self.controls.append((tag, attrs.get('id') or attrs.get('href')))
        if self.in_header and tag == 'img' and '/brand/' in attrs.get('src', ''):
            self.brand_images.append(attrs)

    def handle_endtag(self, tag):
        if tag == 'header':
            self.in_header = False


class PublicShellTests(unittest.TestCase):
    def test_ads_are_scoped_to_game_and_leaderboard(self):
        client = TestClient(app)
        for path in ('/penalties', '/leaderboard'):
            page = client.get(path).text
            self.assertIn('data-ad-slot="sidebar-left"', page)
            self.assertIn('data-ad-slot="sidebar-right"', page)
        self.assertIn('data-ad-slot="gameplay-bottom"', client.get('/penalties').text)
        for path in ('/', '/how-to-play', '/account', '/history', '/u/example'):
            self.assertNotIn('data-ad-slot=', client.get(path).text)

    def test_results_share_has_a_visible_label(self):
        response = TestClient(app).get('/penalties')
        self.assertEqual(response.status_code, 200)
        self.assertIn('aria-label="Share with friends"', response.text)
        self.assertIn('<span>Share with friends</span>', response.text)

    def test_public_header_only_has_menu_and_brand(self):
        client = TestClient(app)
        for path in ('/', '/penalties', '/leaderboard', '/history', '/account'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                parser = HeaderParser()
                parser.feed(response.text)
                self.assertEqual(parser.controls, [('button', 'menu-open'), ('a', '/')])
                self.assertEqual(len(parser.brand_images), 3)
                self.assertTrue(all(image['src'] == '/trivia-assets/brand/logo-transparent.png?v=1'
                                    and image['alt'] == '' for image in parser.brand_images))
                self.assertIn('aria-label="ON THE DOT. home"', response.text)
                self.assertNotIn('id="profile-open"', response.text)
                self.assertNotIn('id="profile-drawer"', response.text)
                self.assertIn('aria-label="Game menu"', response.text)
                for destination in ('penalties', 'leaderboard', 'history', 'account'):
                    self.assertIn(f'href="/{destination}"', response.text)
