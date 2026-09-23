#!/bin/zsh
# Resolve this file's directory so Finder launches use the correct .env and modules.
set -eu
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print 'Python environment missing. See README.md.'
  exit 1
fi
exec .venv/bin/python -m uvicorn trivia_app.main:app --host 127.0.0.1 --port "${PORT:-8004}"
