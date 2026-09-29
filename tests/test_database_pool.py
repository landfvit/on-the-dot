"""Real pool reuse and transaction isolation, without touching player tables."""
from concurrent.futures import ThreadPoolExecutor
import os
import unittest
from unittest.mock import patch

from psycopg_pool import PoolTimeout
from api import database


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Local PostgreSQL integration tests')
class DatabasePoolTests(unittest.TestCase):
    def setUp(self):
        with database.get_connection() as conn:
            self.assertIn(conn.info.host,('localhost','127.0.0.1','::1',''),'Local database only')
            self.dsn=conn.info.dsn
        p=patch.dict(os.environ,{'DATABASE_URL':self.dsn,'DB_POOL_MIN':'1','DB_POOL_MAX':'1'})
        p.start();self.addCleanup(p.stop)
        database.start_pool();self.addCleanup(database.close_pool)

    def test_reuses_session_and_rolls_back_before_next_borrower(self):
        with database.get_connection() as conn:
            pid=conn.info.backend_pid
            conn.execute('CREATE TEMP TABLE otd_pool_probe(value integer)')
            conn.execute('INSERT INTO otd_pool_probe VALUES(1)')
        with self.assertRaises(ValueError):
            with database.get_connection() as conn:
                self.assertEqual(conn.info.backend_pid,pid)
                conn.execute('INSERT INTO otd_pool_probe VALUES(2)')
                conn.execute("SET LOCAL statement_timeout='1s'")
                raise ValueError('Simulated failed request')
        with database.get_connection() as conn:
            self.assertEqual(conn.info.backend_pid,pid)
            self.assertEqual(conn.execute('SELECT sum(value) n FROM otd_pool_probe').fetchone()['n'],1)
            self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()['statement_timeout'],'0')

    def test_pool_does_not_open_extra_connections_when_exhausted(self):
        def extra_borrower():
            with database._pool.connection(timeout=.05):
                self.fail('The only connection should still be held')
        with ThreadPoolExecutor(max_workers=1) as workers:
            with database.get_connection() as conn:
                pid=conn.info.backend_pid
                with self.assertRaises(PoolTimeout):workers.submit(extra_borrower).result(timeout=2)
        with database.get_connection() as conn:self.assertEqual(conn.info.backend_pid,pid)
        self.assertEqual(database._pool.get_stats()['pool_size'],1)

    def test_stale_connection_is_replaced_before_request(self):
        with database.get_connection() as conn:pid=conn.info.backend_pid
        # Simulate the hosting provider closing an idle session. Only this
        # test pool's session is terminated, never another application's PID.
        import psycopg
        with psycopg.connect(self.dsn) as admin:admin.execute('SELECT pg_terminate_backend(%s)',(pid,))
        with database.get_connection() as conn:
            self.assertNotEqual(conn.info.backend_pid,pid)
            self.assertEqual(conn.execute('SELECT 1 n').fetchone()['n'],1)
