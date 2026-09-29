import os
import unittest
from unittest.mock import patch

from api.database import get_connection
from api import database
from psycopg.rows import dict_row


class DatabaseConfigTests(unittest.TestCase):
    def test_web_pool_is_bounded_and_direct_connections_resume_after_shutdown(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://database.invalid/game'}, clear=True), \
                patch('api.database.ConnectionPool') as factory, patch('api.database.psycopg.connect') as connect:
            database.start_pool()
            try:
                self.assertIs(get_connection(), factory.return_value.connection.return_value)
                connect.assert_not_called()
                kwargs=factory.call_args.kwargs
                self.assertEqual((kwargs['min_size'],kwargs['max_size']),(2,10))
                self.assertEqual(kwargs['timeout'],5)
                self.assertIsNone(kwargs['kwargs']['prepare_threshold'])
            finally:database.close_pool()
            factory.return_value.close.assert_called_once()
            get_connection()
            connect.assert_called_once()

    def test_pool_rejects_unbounded_or_inverted_limits(self):
        for minimum,maximum in [('2','1'),('0','0'),('2','100'),('-1','10')]:
            with self.subTest(minimum=minimum,maximum=maximum), \
                    patch.dict(os.environ, {'DB_POOL_MIN':minimum,'DB_POOL_MAX':maximum}):
                with self.assertRaises(ValueError):database.start_pool()
                self.assertIsNone(database._pool)

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
