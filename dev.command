#!/bin/zsh
# Local editing only. Never use Render's database, URLs or email delivery.
set -eu
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print 'Python environment missing. See README.md.'
  exit 1
fi
PORT="${PORT:-8009}"
if [[ "$PORT" != <-> ]] || (( PORT < 1024 || PORT > 65535 )); then
  print 'PORT must be a number between 1024 and 65535.'
  exit 1
fi
# Credentials still come from the private .env, but the database target is
# explicitly pinned to this Mac's independent On The Dot copy.
export DATABASE_URL='' DB_HOST=127.0.0.1 DB_PORT=5432 DB_NAME=on_the_dot
unset PGSERVICE PGSERVICEFILE PGHOSTADDR
export PUBLIC_SITE_URL="http://127.0.0.1:$PORT" TRIVIA_HTTPS_ONLY=0
export RESEND_API_KEY='' ACCOUNT_EMAIL_FROM=''
print "Local editor: $PUBLIC_SITE_URL/"
print 'Database: local on_the_dot. Email delivery: disabled.'
print 'Save HTML/CSS/JS and refresh the browser. Python changes restart automatically.'
exec .venv/bin/python -m uvicorn trivia_app.main:app --host 127.0.0.1 --port "$PORT" \
  --reload --reload-dir trivia_app --reload-dir api
