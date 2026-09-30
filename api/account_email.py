"""Optional HTTPS email delivery. Never derive password-reset links from Host."""
import os
from urllib.parse import urlsplit

import requests


def reset_origin():
    origin=os.getenv('PUBLIC_SITE_URL','').strip().rstrip('/')
    try:
        parsed=urlsplit(origin)
        parsed.port
    except ValueError:
        return None
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        return None
    return origin


def reset_enabled():
    return bool(reset_origin() and os.getenv('RESEND_API_KEY','').strip() and os.getenv('ACCOUNT_EMAIL_FROM','').strip())


def send_reset(email,token):
    if not reset_enabled():raise RuntimeError('Account email is not configured')
    # URL fragments stay out of HTTP access logs and Referer headers. The
    # account UI clears the fragment immediately and submits the token via POST.
    link=f'{reset_origin()}/account#reset={token}'
    try:
        response=requests.post('https://api.resend.com/emails',timeout=(5,10),allow_redirects=False,
            headers={'Authorization':'Bearer '+os.environ['RESEND_API_KEY'].strip()},
            json={'from':os.environ['ACCOUNT_EMAIL_FROM'].strip(),'to':[email],'subject':'Reset your ON THE DOT. password',
                  'text':f'Choose a new password using the link below.\n\n{link}\n\nThis link works once and expires in 30 minutes. If you did not request a reset, ignore this email. Your password will stay the same.'})
    except requests.RequestException:
        raise RuntimeError('Account email delivery failed') from None
    # Do not include the provider response, recipient or token in exceptions.
    if not 200<=response.status_code<300:raise RuntimeError('Account email delivery failed')
