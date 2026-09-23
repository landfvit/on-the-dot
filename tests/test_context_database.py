"""Rollback-only import checks against existing fixtures, enabled with TRIVIA_DB_TEST=1."""
import io
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from api.database import get_connection
from src.match_context_import import attendance


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST') == '1', 'Set TRIVIA_DB_TEST=1 for PostgreSQL checks')
class AttendanceDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)

        @contextmanager
        def shared():
            yield self.conn

        mock = patch('src.match_context_import.get_connection', shared)
        mock.start(); self.addCleanup(mock.stop)

    def import_row(self, row, replace=False):
        header = 'fixture_id,date_utc,home_team_id,away_team_id,attendance,source_url,historical_capacity,capacity_source_url\n'
        with patch.object(Path, 'open', return_value=io.StringIO(header + row)), patch('builtins.print'):
            attendance(Path('test.csv'), replace)

    def test_zero_is_preserved_and_capacity_is_not_inferred(self):
        self.import_row('1208021,2024-08-16,33,36,0,https://example.org/test-report,,\n', replace=True)
        row = self.conn.execute('SELECT * FROM fixture_attendance_sources WHERE fixture_id=1208021').fetchone()
        self.assertEqual(row['attendance'], 0)
        self.assertIsNone(row['historical_capacity'])

    def test_mismatched_identity_and_invalid_attendance_are_rejected(self):
        for row in ['1208021,2024-08-17,33,36,100,https://example.org/report,,\n',
                    '1208021,2024-08-16,36,33,100,https://example.org/report,,\n',
                    '1208021,2024-08-16,33,36,-1,https://example.org/report,,\n',
                    '1208021,2024-08-16,33,36,100,https://example.org/report,50,https://example.org/capacity\n']:
            with self.assertRaises(ValueError): self.import_row(row, replace=True)

    def test_conflicting_count_requires_explicit_replacement(self):
        self.import_row('1208021,2024-08-16,33,36,100,https://example.org/report,,\n', replace=True)
        with self.assertRaises(ValueError):
            self.import_row('1208021,2024-08-16,33,36,101,https://example.org/report,,\n')
        self.assertEqual(self.conn.execute('SELECT attendance FROM fixtures WHERE fixture_id=1208021').fetchone()['attendance'], 100)
