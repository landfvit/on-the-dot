"""Record the portable copy's initial hashes; exclude credentials and runtimes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.venv', '.venv-llm', '__pycache__', '.DS_Store', '.env',
        'COPY_MANIFEST.json', '.pytest_cache'}


def records():
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if SKIP.intersection(relative.parts) or path.suffix in {'.log', '.pyc', '.lock'}:
            continue
        if not path.is_file():
            continue
        with path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        yield relative.as_posix(), {'bytes': path.stat().st_size, 'sha256': digest}


if __name__ == '__main__':
    output = ROOT / 'COPY_MANIFEST.json'
    if output.exists():
        raise SystemExit('Initial manifest already exists; keep it as the merge baseline.')
    files = dict(records())
    output.write_text(json.dumps({'format': 1, 'copied_on': '2026-09-22', 'files': files}, indent=2) + '\n')
    print(f'Recorded {len(files)} files; {sum(v["bytes"] for v in files.values())} bytes.')
