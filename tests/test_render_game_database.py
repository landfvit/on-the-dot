import os
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from tools.render_game_database import DATA_TABLES, assert_empty, pg_environment, render_config, restore_list, load_manifest


class RenderGameDatabaseTests(unittest.TestCase):
    def test_modified_archive_or_manifest_with_accounts_is_refused(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'game.dump').write_bytes(b'fixture archive')
            manifest = {'format': 1, 'sha256': hashlib.sha256(b'fixture archive').hexdigest(),
                        'data_tables': sorted(DATA_TABLES), 'counts': dict.fromkeys(DATA_TABLES, 0)}
            (directory / 'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(load_manifest(directory), manifest)
            (directory / 'game.dump').write_bytes(b'changed archive')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                load_manifest(directory)
            (directory / 'game.dump').write_bytes(b'fixture archive')
            manifest['counts']['game_accounts'] = 1
            (directory / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'non-game'):
                load_manifest(directory)

    def test_existing_public_schema_is_preserved_without_removing_tables(self):
        toc = ('4; 2615 2200 SCHEMA - public pg_database_owner\n'
               '5; 0 0 COMMENT - SCHEMA public pg_database_owner\n'
               '6; 1259 999 TABLE public game_accounts owner\n')
        self.assertEqual(restore_list(toc), '6; 1259 999 TABLE public game_accounts owner\n')

    def test_account_and_model_tables_are_never_exported(self):
        excluded = {'game_accounts', 'game_sessions', 'game_solo_runs', 'game_solo_answers',
                    'game_xp_ledger', 'game_question_history', 'game_daily_activity',
                    'pvp_players', 'trivia_bank_models', 'fixture_player_statistics'}
        self.assertFalse(DATA_TABLES & excluded)

    def test_external_url_requires_tls(self):
        config = render_config('postgresql://test:dummy@dpg-example.frankfurt-postgres.render.com/game?sslmode=disable')
        self.assertEqual(config['sslmode'], 'require')
        self.assertEqual(config['connect_timeout'], '15')

    def test_wrong_host_and_incomplete_urls_are_refused(self):
        for value in ['postgresql://test:dummy@localhost/game',
                      'postgresql://test:dummy@database.render.com.attacker.invalid/game',
                      'postgresql://test@database.render.com/game',
                      'postgresql://test:dummy@database.render.com/game?options=other']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                render_config(value)

    def test_inherited_postgres_targets_cannot_override_destination(self):
        with patch.dict(os.environ, {'PGHOSTADDR': '127.0.0.1', 'PGSERVICE': 'local',
                                    'PGPASSWORD': 'old', 'PGOPTIONS': 'wrong'}, clear=True):
            env = pg_environment({'host': 'database.render.com', 'dbname': 'game', 'password': 'dummy'})
        self.assertNotIn('PGHOSTADDR', env)
        self.assertNotIn('PGSERVICE', env)
        self.assertNotIn('PGOPTIONS', env)
        self.assertEqual(env['PGPASSWORD'], 'dummy')

    def test_existing_schema_is_refused_even_with_zero_rows(self):
        for objects, routines in [(1, 0), (0, 1), (5, 7)]:
            conn = MagicMock()
            conn.execute.return_value.fetchone.side_effect = [(objects,), (routines,)]
            with self.subTest(objects=objects, routines=routines), self.assertRaises(ValueError):
                assert_empty(conn)

    def test_empty_database_is_allowed(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [(0,), (0,)]
        assert_empty(conn)
