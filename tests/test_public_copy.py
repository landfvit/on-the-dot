"""Public copy stays brief without changing server-owned timers or eligibility."""
import unittest
from html.parser import HTMLParser

from fastapi.testclient import TestClient

from trivia_app.main import app


class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paragraphs = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == 'p':
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == 'p' and self.current is not None:
            self.paragraphs.append(''.join(self.current).strip())
            self.current = None


class PublicCopyTests(unittest.TestCase):
    def test_public_pages_and_dynamic_copy_have_no_clock_times_or_slogans(self):
        client = TestClient(app)
        paths = ['/', '/how-to-play', '/penalties', '/daily', '/friends',
                 '/account', '/leaderboard', '/history', '/my-questions']
        paths += ['/trivia-assets/' + name + '.js'
                  for name in ('home', 'mode_intro', 'solo', 'community', 'friends')]
        for path in paths:
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotRegex(response.text, r'UTC|00:00|midnight')
                self.assertNotRegex(response.text.lower(),
                                    r'unlock daily|make it count|set your record|go head.to.head|play fair')

    def test_explanatory_paragraphs_stay_short(self):
        client = TestClient(app)
        for path in ('/', '/how-to-play', '/account', '/penalties', '/daily', '/friends'):
            with self.subTest(path=path):
                copy = Paragraphs()
                copy.feed(client.get(path).text)
                self.assertTrue(copy.paragraphs)
                for paragraph in copy.paragraphs:
                    self.assertLessEqual(len(paragraph.split()), 26, paragraph)

    def test_short_copy_keeps_guest_and_account_deletion_consequences(self):
        client = TestClient(app)
        self.assertIn('Guest progress is not transferred.', client.get('/penalties').text)
        account = client.get('/account').text
        for text in ('permanently deletes your account and progress',
                     'Anonymous game records remain', 'This cannot be undone',
                     'Your username cannot be changed'):
            self.assertIn(text, account)

    def test_shared_public_script_uses_the_same_new_cache_version(self):
        client = TestClient(app)
        for path in ('/account', '/penalties', '/daily'):
            self.assertIn('/trivia-assets/solo.js?v=34', client.get(path).text)
