import os
import json
import time
import secrets
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv('QB_CLIENT_ID')
CLIENT_SECRET = os.getenv('QB_CLIENT_SECRET')
REDIRECT_URI = os.getenv('QB_REDIRECT_URI', 'http://localhost:5000/callback')
ENVIRONMENT = os.getenv('QB_ENVIRONMENT', 'production')

AUTH_URL = 'https://appcenter.intuit.com/connect/oauth2'
TOKEN_URL = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'
SCOPES = 'com.intuit.quickbooks.accounting'
TOKENS_FILE = os.path.join(os.path.dirname(__file__), 'tokens.json')

if ENVIRONMENT == 'sandbox':
    BASE_URL = 'https://sandbox-quickbooks.api.intuit.com/v3/company'
else:
    BASE_URL = 'https://quickbooks.api.intuit.com/v3/company'


def get_auth_url():
    state = secrets.token_urlsafe(16)
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'scope': SCOPES,
        'redirect_uri': REDIRECT_URI,
        'state': state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code):
    resp = requests.post(
        TOKEN_URL,
        auth=(CLIENT_ID, CLIENT_SECRET),
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token):
    resp = requests.post(
        TOKEN_URL,
        auth=(CLIENT_ID, CLIENT_SECRET),
        data={
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def save_tokens(tokens, realm_id):
    data = {
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'realm_id': realm_id,
        'expires_at': time.time() + tokens.get('expires_in', 3600),
    }
    with open(TOKENS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def load_tokens():
    if not os.path.exists(TOKENS_FILE):
        return None
    with open(TOKENS_FILE) as f:
        return json.load(f)


def get_valid_token():
    tokens = load_tokens()
    if not tokens:
        return None, None

    if time.time() > tokens['expires_at'] - 60:
        try:
            new_tokens = refresh_access_token(tokens['refresh_token'])
            save_tokens(new_tokens, tokens['realm_id'])
            tokens['access_token'] = new_tokens['access_token']
        except Exception:
            return None, None

    return tokens['access_token'], tokens['realm_id']


def is_connected():
    token, realm = get_valid_token()
    return token is not None
