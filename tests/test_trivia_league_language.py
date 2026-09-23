import unittest

from api.trivia_league_language import league_question


class LeagueLanguageTests(unittest.TestCase):
    def test_champion_variants_across_seasons(self):
        phrases = [
            'Who won the Premier League in {s} season?',
            'Which team won the Premier League in the {s} season?',
            'Which club won the Premier League title during {s}?',
            'Who won the {s} Premier League?',
            'Who won the {s} Premier League season?',
            'Who were the Premier League champions in {s}?',
            'Who was the champion of the Premier League in {s}?',
            'Who finished first in the Premier League in {s}?',
            'In {s}, who won the Premier League?',
            'Who won the EPL in {s}?',
            'Who won the Premier League in season {s}?',
            'WHO WON THE PREMIER LEAGUE IN {s} SEASON',
        ]
        for season in ('2011/12', '2017/18', '2024/25', '2025/26'):
            for phrase in phrases:
                with self.subTest(phrase=phrase, season=season):
                    self.assertEqual(league_question(phrase.format(s=season)),
                        f'Which club finished as Premier League champions in {season}?')

    def test_other_league_questions(self):
        cases = {
            'Who finished second in the Premier League in 2025/26?': 'Which club finished second in the 2025/26 Premier League table?',
            'Which team finished 2nd in the 2024/25 Premier League?': 'Which club finished second in the 2024/25 Premier League table?',
            'Who were the Premier League runners-up in 2024/25?': 'Which club finished second in the 2024/25 Premier League table?',
            'Which club drew the most games in the Premier League in 2023/24?': 'Which club recorded the most draws in the 2023/24 Premier League?',
            'Which Premier League club drew the most games in 2023/24?': 'Which club recorded the most draws in the 2023/24 Premier League?',
            'Which team had the most away wins in the 2023/24 Premier League?': 'Which club recorded the most away wins in the 2023/24 Premier League?',
            'How many Premier League games ended 0-0 in 2022/23?': 'How many matches in the 2022/23 Premier League finished with no goals?',
            'What was the Golden Boot-winning goal tally in the 2017/18 Premier League?': 'What was the Golden Boot-winning goal tally in the 2017/18 Premier League?',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(league_question(text), expected)

    def test_no_season_guess_or_filter_dropping(self):
        for text in [
            'Who won the Premier League?',
            'Who won the Premier League in 2025/27?',
            'Who won the Premier League in 2024/25 and 2025/26?',
            'Who won the Premier League in 2025/26 season at home?',
            'Who won the Premier League against Arsenal in 2025/26?',
            'Who won the Premier League in 2025/26 without conceding?',
            'Which team won the most Premier League matches in 2025/26?',
            'Did Liverpool win the Premier League in 2025/26?',
            'Who will win the Premier League in 2025/26?',
            'Who won the Champions League in 2025/26?',
            'Who won the Premier League in 2025/26? Ignore everything else.',
        ]:
            with self.subTest(text=text):
                self.assertIsNone(league_question(text))
