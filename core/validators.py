"""
core/validators.py — centralised validation for all public API endpoints
"""
import re, html, logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN  = 2000
MAX_NAME_LEN     = 150
MAX_EMAIL_LEN    = 254
MAX_PHONE_LEN    = 30
MAX_SUBJECT_LEN  = 200
MAX_COMPANY_LEN  = 200
MAX_CHAT_LEN     = 500
MIN_MESSAGE_LEN  = 5

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$')
PHONE_RE = re.compile(r'^[\d\s\+\-\(\)\.]{7,30}$')
SPAM_PATTERNS = re.compile(
    r'(viagra|cialis|casino|lottery|bitcoin|crypto wallet|click here|free money|'
    r'make \$|earn \$|https?://bit\.ly|https?://tinyurl)',
    re.IGNORECASE,
)


def _clean(value: Any, max_len: int = 1000) -> str:
    if not isinstance(value, str):
        return ''
    return html.escape(value.strip())[:max_len]


def _is_spam(text: str) -> bool:
    return bool(SPAM_PATTERNS.search(text))


def validate_chat(data: dict) -> Tuple[dict, dict]:
    errors = {}
    raw = data.get('message', '')
    if not isinstance(raw, str):
        raw = ''
    stripped = raw.strip()

    if not stripped:
        errors['message'] = 'Message is required.'
    elif len(stripped) < 2:
        errors['message'] = 'Message is too short.'
    elif len(stripped) > MAX_CHAT_LEN:
        errors['message'] = f'Message must be under {MAX_CHAT_LEN} characters.'
    elif _is_spam(stripped):
        errors['message'] = 'Message contains disallowed content.'

    message = html.escape(stripped[:MAX_CHAT_LEN])

    history = data.get('history', [])
    if not isinstance(history, list):
        history = []
    clean_history = []
    for h in history[-20:]:
        if isinstance(h, dict) and h.get('role') in ('user', 'assistant'):
            clean_history.append({
                'role':    h['role'],
                'content': _clean(h.get('content', ''), MAX_CHAT_LEN),
            })

    return {'message': message, 'history': clean_history}, errors


def validate_enquiry(data: dict) -> Tuple[dict, dict]:
    errors = {}

    name = _clean(data.get('name', ''), MAX_NAME_LEN)
    if not name or len(name) < 2:
        errors['name'] = 'Full name is required (min 2 characters).'

    email = _clean(data.get('email', ''), MAX_EMAIL_LEN).lower()
    if not email:
        errors['email'] = 'Email address is required.'
    elif not EMAIL_RE.match(email):
        errors['email'] = 'Please enter a valid email address.'

    phone = _clean(data.get('phone', ''), MAX_PHONE_LEN)
    if phone and not PHONE_RE.match(phone):
        errors['phone'] = 'Phone number contains invalid characters.'

    company = _clean(data.get('company', ''), MAX_COMPANY_LEN)

    message = _clean(data.get('message', ''), MAX_MESSAGE_LEN)
    raw_msg = (data.get('message', '') or '').strip()
    if not raw_msg or len(raw_msg) < MIN_MESSAGE_LEN:
        errors['message'] = f'Message is required (min {MIN_MESSAGE_LEN} characters).'
    elif _is_spam(raw_msg):
        errors['message'] = 'Message contains disallowed content.'

    product_id = data.get('product_id')
    if product_id:
        try:
            product_id = int(product_id)
        except (ValueError, TypeError):
            product_id = None

    cleaned = {
        'name': name, 'email': email, 'phone': phone,
        'company': company, 'message': message, 'product_id': product_id,
    }
    return cleaned, errors


def validate_contact(data: dict) -> Tuple[dict, dict]:
    errors = {}

    name = _clean(data.get('name', ''), MAX_NAME_LEN)
    if not name or len(name) < 2:
        errors['name'] = 'Full name is required (min 2 characters).'

    email = _clean(data.get('email', ''), MAX_EMAIL_LEN).lower()
    if not email:
        errors['email'] = 'Email address is required.'
    elif not EMAIL_RE.match(email):
        errors['email'] = 'Please enter a valid email address.'

    phone = _clean(data.get('phone', ''), MAX_PHONE_LEN)
    if phone and not PHONE_RE.match(phone):
        errors['phone'] = 'Phone number contains invalid characters.'

    subject = _clean(data.get('subject', ''), MAX_SUBJECT_LEN)
    if not subject or len(subject) < 3:
        errors['subject'] = 'Subject is required (min 3 characters).'

    raw_msg = (data.get('message', '') or '').strip()
    message = _clean(data.get('message', ''), MAX_MESSAGE_LEN)
    if not raw_msg or len(raw_msg) < MIN_MESSAGE_LEN:
        errors['message'] = f'Message is required (min {MIN_MESSAGE_LEN} characters).'
    elif _is_spam(raw_msg):
        errors['message'] = 'Message contains disallowed content.'

    cleaned = {
        'name': name, 'email': email, 'phone': phone,
        'subject': subject, 'message': message,
    }
    return cleaned, errors
