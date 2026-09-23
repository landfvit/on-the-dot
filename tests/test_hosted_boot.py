"""Public pages must boot without optional local import/training dependencies."""
from pathlib import Path
import subprocess
import sys
import unittest


class HostedBootTests(unittest.TestCase):
    def test_public_pages_without_local_only_dependencies(self):
        script = '''
import importlib.abc
import sys

class NoLocalPackages(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'PIL', 'mwparserfromhell', 'mlx', 'mlx_lm'}:
            raise ImportError('Local-only dependency requested')
sys.meta_path.insert(0, NoLocalPackages())

from fastapi.testclient import TestClient
from trivia_app.main import app
client = TestClient(app)
for path in ['/', '/penalties', '/account', '/leaderboard', '/trivia-assets/solo.js']:
    assert client.get(path).status_code == 200, path
'''
        result = subprocess.run([sys.executable, '-c', script],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
