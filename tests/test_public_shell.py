import unittest
from html.parser import HTMLParser

from fastapi.testclient import TestClient
from trivia_app.main import app


class HeaderParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_header = False
        self.controls = []
        self.toggles = []
        self.brand_images = []
        self.brand_letters = []
        self.brand_dots = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'header' and 'points-header' in attrs.get('class', '').split():
            self.in_header = True
        if self.in_header and tag in ('a', 'button', 'nav', 'form'):
            self.controls.append((tag, attrs.get('id') or attrs.get('href')))
        if self.in_header and tag == 'img' and '/brand/' in attrs.get('src', ''):
            self.brand_images.append(attrs)
        if self.in_header and tag == 'button':
            self.toggles.extend(key for key in ('data-theme-toggle','data-sound-toggle') if key in attrs)
        if self.in_header and tag == 'svg' and attrs.get('class') == 'brand-letter':
            self.brand_letters.append(attrs['data-letter'])
        if self.in_header and tag == 'svg' and attrs.get('class') == 'brand-dot':
            self.brand_dots += 1

    def handle_endtag(self, tag):
        if tag == 'header':
            self.in_header = False


class PageActionsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.containers = []
        self.controls = []
        self.container_tag = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if 'page-return' in classes or 'solo-heading' in classes:
            self.containers.append(tag)
            self.container_tag = tag
        if self.container_tag and tag in ('a', 'button'):
            self.controls.append(attrs)

    def handle_endtag(self, tag):
        if tag == self.container_tag:
            self.container_tag = None


class PublicShellTests(unittest.TestCase):
    def test_ads_are_scoped_to_game_and_leaderboard(self):
        client = TestClient(app)
        for path in ('/penalties', '/leaderboard'):
            page = client.get(path).text
            self.assertIn('data-ad-slot="sidebar-left"', page)
            self.assertIn('data-ad-slot="sidebar-right"', page)
        self.assertIn('data-ad-slot="gameplay-bottom"', client.get('/penalties').text)
        for path in ('/account', '/history', '/u/example'):
            self.assertNotIn('data-ad-slot=', client.get(path).text)

    def test_results_share_has_a_visible_label(self):
        response = TestClient(app).get('/penalties')
        self.assertEqual(response.status_code, 200)
        self.assertIn('aria-label="Share with friends"', response.text)
        self.assertIn('<span>Share with friends</span>', response.text)

    def test_public_header_has_brand_navigation_and_one_of_each_preference(self):
        client = TestClient(app)
        for path in ('/', '/penalties', '/leaderboard', '/history', '/account'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                parser = HeaderParser()
                parser.feed(response.text)
                self.assertEqual(parser.toggles, ['data-theme-toggle', 'data-sound-toggle'])
                self.assertEqual(len(parser.brand_images), 1)
                self.assertIn('/brand/favicon.svg', parser.brand_images[0]['src'])
                self.assertIn('aria-label="ON THE DOT. home"', response.text)
                self.assertNotIn('id="profile-open"', response.text)
                self.assertNotIn('id="profile-drawer"', response.text)
                self.assertNotIn('id="menu-open"', response.text)
                self.assertIn('aria-label="Main navigation"', response.text)

    def test_footer_and_page_actions_do_not_repeat_navigation(self):
        client=TestClient(app)
        for path in ('/','/penalties','/daily','/friends','/how-to-play','/leaderboard','/history','/account','/u/example'):
            with self.subTest(path=path):
                html=client.get(path).text
                footer=html.split('<footer class="site-footer">',1)[1].split('</footer>',1)[0]
                self.assertNotIn('<a ',footer)
                self.assertNotIn('<button',footer)
                self.assertIn('PL Seasons',footer)
                actions=PageActionsParser()
                actions.feed(html)
                self.assertEqual(len(actions.containers),1)
                self.assertFalse(any('data-theme-toggle' in control for control in actions.controls))
                self.assertFalse(any('data-sound-toggle' in control for control in actions.controls))
                self.assertEqual(any('data-share-game' in control for control in actions.controls),path=='/')
                self.assertEqual(sum('data-back' in control for control in actions.controls),int(path!='/'))
                self.assertLessEqual(html.count('href="/how-to-play"'),1)
        self.assertEqual(client.get('/account').text.count('data-sound-toggle'),1)
        self.assertIn('href="/history">Match history',client.get('/account').text)
        for path in ('/','/how-to-play','/account'):
            self.assertEqual(client.get(path).text.count('href="/penalties"'),1)
