"""EncryptedCharField — Aadhaar / PAN at rest (REQUIREMENTS §24: "treat as sensitive").

Values are stored as `enc1:<Fernet token>`. Reading tolerates plain text (rows
written before this field existed), so no data has to be rewritten to deploy it;
a value is encrypted the next time its row is saved, or all at once with
`manage.py encrypt_360_sensitive_fields`. The key comes from
`settings.FIELD_ENCRYPTION_KEY` (see settings.py).
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

PREFIX = 'enc1:'


def _fernet():
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', '') or ''
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(('anupam360-fields:' + settings.SECRET_KEY).encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    if not value or value.startswith(PREFIX):
        return value
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not value or not value.startswith(PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        # Wrong key: never show ciphertext as if it were the value, and never crash a page.
        return ''


class EncryptedCharField(models.CharField):
    description = 'CharField encrypted at rest'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 255)            # ciphertext is longer than the plain value
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        return decrypt(value) if isinstance(value, str) else value

    def to_python(self, value):
        return decrypt(value) if isinstance(value, str) else value

    def value_to_string(self, obj):
        # Serialisation (backups, dumpdata) must not leak the plain value.
        return encrypt(self.value_from_object(obj) or '')

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt(value) if isinstance(value, str) else value
