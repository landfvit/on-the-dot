"""Fail-closed access to the private question workspace."""
import os
import secrets
import hashlib
import hmac
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

basic = HTTPBasic(auto_error=False)


def credential_tag(request):
    value = os.getenv('TRIVIA_EDITOR_USERNAME', '') + ':' + os.getenv('TRIVIA_EDITOR_PASSWORD', '')
    return hmac.new(request.app.state.session_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def require_editor(request: Request, credentials: HTTPBasicCredentials | None = Depends(basic)):
    username = os.getenv('TRIVIA_EDITOR_USERNAME', '')
    password = os.getenv('TRIVIA_EDITOR_PASSWORD', '')
    if not username or len(password) < 16:
        raise HTTPException(404, 'Not found')
    valid_user = secrets.compare_digest((credentials.username if credentials else '').encode(), username.encode())
    valid_password = secrets.compare_digest((credentials.password if credentials else '').encode(), password.encode())
    session = request.scope.get('session', {})
    session_valid = bool(session.get('editor')) and hasattr(request.app.state, 'session_secret') and secrets.compare_digest(
        str(session.get('credential_tag', '')), credential_tag(request))
    if not (valid_user and valid_password) and not session_valid:
        raise HTTPException(401, 'Editor authentication required', headers={'WWW-Authenticate': 'Basic realm="Trivia editor"'})
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and (
            urlsplit(origin).netloc != request.url.netloc or urlsplit(origin).scheme != request.url.scheme
        )):
            raise HTTPException(403, 'Cross-origin editor requests are not allowed')
