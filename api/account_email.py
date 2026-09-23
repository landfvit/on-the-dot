"""Optional HTTPS email delivery. Never derive password-reset links from Host."""
import os
from urllib.parse import urlsplit

import requests


def reset_origin():
    origin=os.getenv('PUBLIC_SITE_URL','').rstrip('/')
    parsed=urlsplit(origin)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        return None
    return origin


def reset_enabled():
    return bool(reset_origin() and os.getenv('RESEND_API_KEY') and os.getenv('ACCOUNT_EMAIL_FROM'))


def send_reset(email,token):
    if not reset_enabled():raise RuntimeError('Account email is not configured')
    # URL fragments stay out of HTTP access logs and Referer headers. The
    # account UI clears the fragment immediately and submits the token via POST.
    link=f'{reset_origin()}/account#reset={token}'
    response=requests.post('https://api.resend.com/emails',timeout=(5,10),
        headers={'Authorization':'Bearer '+os.environ['RESEND_API_KEY']},
        json={'from':os.environ['ACCOUNT_EMAIL_FROM'],'to':[email],'subject':'Reset your ON THE DOT. password',
              'text':f'Reset your password:\n{link}\n\nThis link expires in 30 minutes and works once. If you did not request it, ignore this email.'})
    # Do not include the provider response, recipient or token in exceptions.
    if not response.ok:raise RuntimeError('Account email delivery failed')
