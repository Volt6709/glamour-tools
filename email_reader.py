import imaplib
import email as email_lib
import os
from email.header import decode_header
from email.utils import parseaddr
from dotenv import load_dotenv

load_dotenv()

IMAP_HOST = 'imap.gmail.com'
IMAP_PORT = 993
EMAIL_ADDR = os.getenv('SMTP_EMAIL', '')
PASSWORD = os.getenv('SMTP_PASSWORD', '')

JOB_KEYWORDS = [
    'quote', 'estimate', 'upholstery', 'recover', 'reupholster',
    'repair', 'sofa', 'couch', 'chair', 'cushion', 'fabric',
    'headboard', 'ottoman', 'bench', 'booth', 'seat'
]


def _decode_str(s):
    if not s:
        return ''
    parts = decode_header(s)
    result = ''
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or 'utf-8', errors='replace')
        else:
            result += str(part)
    return result.strip()


def _get_body(msg):
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain' and 'attachment' not in str(part.get('Content-Disposition', '')):
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode('utf-8', errors='replace')
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode('utf-8', errors='replace')
    return body[:3000]


def _connect():
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(EMAIL_ADDR, PASSWORD)
    return mail


def _parse_message(eid, raw):
    msg = email_lib.message_from_bytes(raw)
    sender_raw = msg.get('From', '')
    name, addr = parseaddr(sender_raw)
    name = _decode_str(name) or addr.split('@')[0]
    subject = _decode_str(msg.get('Subject', '(no subject)'))
    date = msg.get('Date', '')
    body = _get_body(msg)
    message_id = msg.get('Message-ID', f'local-{eid}')
    is_job = any(kw in (subject + ' ' + body).lower() for kw in JOB_KEYWORDS)

    return {
        'imap_id': eid.decode() if isinstance(eid, bytes) else str(eid),
        'message_id': message_id,
        'sender_name': name,
        'sender_email': addr,
        'subject': subject,
        'date': date,
        'body': body,
        'is_job': is_job,
    }


def is_configured():
    return bool(EMAIL_ADDR and PASSWORD)


def fetch_recent(limit=30):
    if not is_configured():
        return []
    try:
        mail = _connect()
        mail.select('INBOX')
        _, data = mail.search(None, 'ALL')
        ids = data[0].split()
        recent = list(reversed(ids[-limit:])) if ids else []

        results = []
        for eid in recent:
            _, msg_data = mail.fetch(eid, '(RFC822)')
            raw = msg_data[0][1]
            results.append(_parse_message(eid, raw))

        mail.logout()
        return results
    except Exception as e:
        return [{'error': str(e)}]


def fetch_one(imap_id):
    if not is_configured():
        return None
    try:
        mail = _connect()
        mail.select('INBOX')
        _, msg_data = mail.fetch(imap_id.encode(), '(RFC822)')
        raw = msg_data[0][1]
        result = _parse_message(imap_id.encode(), raw)
        mail.logout()
        return result
    except Exception:
        return None
