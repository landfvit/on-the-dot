import unittest
from api.trivia_audit import evidence_hash, season_audits
from api.trivia_models import GradeAnswer
from api.trivia import grade_answer


class CoverageAuditTests(unittest.TestCase):
    def setUp(self):
        self.rules = [{'first_season': 2000, 'last_season': 2030, 'team_count': 4}]
        self.rows = [{'season': 2020, 'team_id': a, 'opponent_id': b, 'result_valid': True,
                      'timeline_valid': True, 'scorers_valid': True, 'status': 'FT'}
                     for a in range(4) for b in range(4) if a != b]

    def audit(self, rows):
        return season_audits(rows, self.rules)[0]

    def test_complete_double_round_robin(self):
        audit = self.audit(self.rows)
        self.assertTrue(audit['catalogue_complete'])
        self.assertEqual(audit['expected_fixtures'], 12)

    def test_missing_match_cannot_hide_behind_valid_results(self):
        audit = self.audit(self.rows[:-1])
        self.assertFalse(audit['catalogue_complete'])
        self.assertIn('incomplete_fixture_catalogue', audit['problems'])

    def test_correct_count_with_duplicate_pair_is_rejected(self):
        audit = self.audit(self.rows[:-1] + [self.rows[0]])
        self.assertEqual(audit['fixtures'], 12)
        self.assertIn('duplicate_or_invalid_pairing', audit['problems'])
        self.assertFalse(audit['catalogue_complete'])

    def test_unknown_competition_format_is_not_guessed(self):
        self.assertIn('unverified_competition_format', season_audits(self.rows, [])[0]['problems'])

    def test_in_progress_season_has_distinct_finished_count(self):
        self.rows[0]['result_valid'] = False; self.rows[0]['status'] = 'NS'
        self.assertEqual(self.audit(self.rows)['finished'], 11)

    def test_bad_result_is_not_mislabeled_as_unplayed(self):
        self.rows[0]['result_valid'] = False
        self.assertEqual(self.audit(self.rows)['finished'], 12)
        self.assertEqual(self.audit(self.rows)['results'], 11)

    def test_missing_away_facts_blocks_complete_home_catalogue(self):
        self.rows[0]['team_facts_valid'] = False
        self.assertIn('inconsistent_team_facts', self.audit(self.rows)['problems'])

    def test_evidence_fingerprint_is_order_independent(self):
        rows = [{'fixture_id': 2, 'goals': 2}, {'fixture_id': 1, 'goals': 1}]
        self.assertEqual(evidence_hash(rows), evidence_hash(rows[::-1]))
        self.assertNotEqual(evidence_hash(rows), evidence_hash([{**rows[0], 'goals': 3}, rows[1]]))

    def test_integer_answer_does_not_accept_rounded_fraction(self):
        self.assertFalse(grade_answer({'kind': 'integer', 'value': 16}, GradeAnswer(value=16.1))['correct'])
        self.assertTrue(grade_answer({'kind': 'integer', 'value': 16}, GradeAnswer(value=16))['correct'])
