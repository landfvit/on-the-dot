"""Safety and reporting checks for the local-only capacity harness."""
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.stress_game import Measurements, local_config, percentile


class StressGameTests(unittest.TestCase):
    def test_remote_or_implicit_database_is_refused(self):
        for host in ('db.render.com', '192.168.1.10', '/tmp', None, 'localhost,db.render.com'):
            with self.subTest(host=host), patch('tools.stress_game.settings', return_value={'host': host}):
                with self.assertRaises(ValueError):
                    local_config(Path('unused'))

    def test_explicit_loopback_database_is_allowed(self):
        for host in ('127.0.0.1', 'localhost', '::1'):
            config = {'host': host, 'dbname': 'source'}
            with self.subTest(host=host), patch('tools.stress_game.settings', return_value=config):
                self.assertEqual(local_config(Path('unused')), config)

    def test_percentile_uses_nearest_rank_and_handles_empty(self):
        self.assertIsNone(percentile([], .95))
        self.assertEqual(percentile(list(range(1, 101)), .95), 95)
        self.assertEqual(percentile([9, 1, 4], .5), 4)
        self.assertEqual(percentile([1.234], .99), 1.23)

    def test_failures_are_in_latency_and_error_denominators(self):
        metrics = Measurements()
        metrics.rows = [('solo:poll', 10, True), ('solo:poll', 10000, False), ('profile', 20, True)]
        metrics.errors['solo:poll:ReadTimeout'] = 1
        metrics.missed_ticks = 9
        result = metrics.summary(10)
        self.assertEqual(result['requests'], 3)
        self.assertEqual(result['rps'], .3)
        self.assertEqual(result['error_rate'], .3333)
        self.assertEqual(result['p95_ms'], 10000)
        self.assertEqual(result['endpoints']['solo:poll']['errors'], 1)
        self.assertEqual(result['missed_one_second_ticks'], 9)

    def test_empty_summary_does_not_imply_measured_latency(self):
        result = Measurements().summary(1)
        self.assertEqual(result['requests'], 0)
        self.assertIsNone(result['p95_ms'])


if __name__ == '__main__':
    unittest.main()
