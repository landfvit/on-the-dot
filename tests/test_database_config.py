import os
import unittest
from unittest.mock import patch

from api.database import get_connection
from psycopg.rows import dict_row


class DatabaseConfigTests(unittest.TestCase):
    def test_hosted_url_takes_precedence_over_local_configuration(self):
        url = 'postgresql://example:dummy@database.invalid/game?sslmode=require'
        with patch.dict(os.environ, {'DATABASE_URL': ' ' + url + ' ',
                                    'DB_HOST': 'localhost', 'DB_PASSWORD': 'local'}, clear=True), \
                patch('api.database.psycopg.connect') as connect:
            self.assertIs(get_connection(), connect.return_value)
            connect.assert_called_once_with(url, row_factory=dict_row)

    def test_blank_or_missing_url_preserves_local_configuration(self):
        for url in (None, '', '  '):
            with self.subTest(url=url):
                env = {'DB_HOST': 'localhost', 'DB_PORT': '5432', 'DB_NAME': 'local',
                       'DB_USER': 'example', 'DB_PASSWORD': 'dummy'}
                if url is not None:
                    env['DATABASE_URL'] = url
                with patch.dict(os.environ, env, clear=True), patch('api.database.psycopg.connect') as connect:
                    get_connection()
                    connect.assert_called_once_with(host='localhost', port='5432', dbname='local',
                                                    user='example', password='dummy', row_factory=dict_row)

    def test_url_failure_does_not_fall_back_to_a_different_database(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://database.invalid/game'}, clear=True), \
                patch('api.database.psycopg.connect', side_effect=RuntimeError('unavailable')) as connect:
            with self.assertRaises(RuntimeError):
                get_connection()
            self.assertEqual(connect.call_count, 1)
