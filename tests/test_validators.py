"""
tests/test_validators.py
────────────────────────
Tests for core/validators.py — input cleaning, error detection, spam blocking.
Run: pytest tests/test_validators.py -v
"""
import pytest
from core.validators import validate_chat, validate_enquiry, validate_contact


# ─────────────────────────────────────────────
# CHAT VALIDATOR
# ─────────────────────────────────────────────

class TestValidateChat:
    def test_valid_message(self):
        cleaned, errors = validate_chat({'message': 'What bearings do you sell?'})
        assert errors == {}
        assert cleaned['message'] == 'What bearings do you sell?'

    def test_empty_message(self):
        _, errors = validate_chat({'message': ''})
        assert 'message' in errors

    def test_whitespace_only(self):
        _, errors = validate_chat({'message': '   '})
        assert 'message' in errors

    def test_message_too_short(self):
        _, errors = validate_chat({'message': 'a'})
        assert 'message' in errors

    def test_message_too_long(self):
        _, errors = validate_chat({'message': 'x' * 501})
        assert 'message' in errors

    def test_spam_message(self):
        _, errors = validate_chat({'message': 'Buy viagra cheap bitcoin wallet'})
        assert 'message' in errors

    def test_history_cleaned(self):
        history = [
            {'role': 'user',      'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi there'},
            {'role': 'unknown',   'content': 'Bad'},   # should be stripped
        ]
        cleaned, errors = validate_chat({'message': 'Tell me more', 'history': history})
        assert errors == {}
        assert len(cleaned['history']) == 2
        assert all(h['role'] in ('user', 'assistant') for h in cleaned['history'])

    def test_history_not_list_becomes_empty(self):
        cleaned, _ = validate_chat({'message': 'Hi there', 'history': 'invalid'})
        assert cleaned['history'] == []

    def test_html_escaped(self):
        cleaned, _ = validate_chat({'message': '<script>alert(1)</script> bearings?'})
        assert '<script>' not in cleaned['message']

    def test_history_capped_at_20(self):
        history = [{'role': 'user', 'content': f'msg {i}'} for i in range(30)]
        cleaned, _ = validate_chat({'message': 'Latest question', 'history': history})
        assert len(cleaned['history']) <= 20


# ─────────────────────────────────────────────
# ENQUIRY VALIDATOR
# ─────────────────────────────────────────────

class TestValidateEnquiry:
    def _valid(self, **overrides):
        base = {
            'name':       'Rajesh Kumar',
            'email':      'rajesh@example.com',
            'phone':      '+91 98765 43210',
            'company':    'Steelworks Ltd',
            'message':    'I need 100 units of tapered roller bearings urgently.',
            'product_id': 1,
        }
        base.update(overrides)
        return base

    def test_valid_payload(self):
        _, errors = validate_enquiry(self._valid())
        assert errors == {}

    def test_name_required(self):
        _, errors = validate_enquiry(self._valid(name=''))
        assert 'name' in errors

    def test_name_too_short(self):
        _, errors = validate_enquiry(self._valid(name='A'))
        assert 'name' in errors

    def test_email_required(self):
        _, errors = validate_enquiry(self._valid(email=''))
        assert 'email' in errors

    def test_invalid_email(self):
        _, errors = validate_enquiry(self._valid(email='not-an-email'))
        assert 'email' in errors

    def test_email_normalised_lowercase(self):
        cleaned, _ = validate_enquiry(self._valid(email='RAJESH@EXAMPLE.COM'))
        assert cleaned['email'] == 'rajesh@example.com'

    def test_phone_optional(self):
        _, errors = validate_enquiry(self._valid(phone=''))
        assert errors == {}

    def test_invalid_phone_chars(self):
        _, errors = validate_enquiry(self._valid(phone='abc-xyz-invalid'))
        assert 'phone' in errors

    def test_message_required(self):
        _, errors = validate_enquiry(self._valid(message=''))
        assert 'message' in errors

    def test_message_too_short(self):
        _, errors = validate_enquiry(self._valid(message='Hi'))
        assert 'message' in errors

    def test_spam_in_message(self):
        _, errors = validate_enquiry(self._valid(message='Buy bitcoin wallet free money'))
        assert 'message' in errors

    def test_product_id_converted_to_int(self):
        cleaned, _ = validate_enquiry(self._valid(product_id='42'))
        assert cleaned['product_id'] == 42

    def test_invalid_product_id_becomes_none(self):
        cleaned, _ = validate_enquiry(self._valid(product_id='abc'))
        assert cleaned['product_id'] is None

    def test_no_product_id_is_valid(self):
        _, errors = validate_enquiry(self._valid(product_id=None))
        assert errors == {}


# ─────────────────────────────────────────────
# CONTACT VALIDATOR
# ─────────────────────────────────────────────

class TestValidateContact:
    def _valid(self, **overrides):
        base = {
            'name':    'Priya Sharma',
            'email':   'priya@company.com',
            'phone':   '044-4691-2265',
            'subject': 'Enquiry about annual contracts',
            'message': 'We are interested in setting up an annual rate contract for bearings.',
        }
        base.update(overrides)
        return base

    def test_valid_payload(self):
        _, errors = validate_contact(self._valid())
        assert errors == {}

    def test_subject_required(self):
        _, errors = validate_contact(self._valid(subject=''))
        assert 'subject' in errors

    def test_subject_too_short(self):
        _, errors = validate_contact(self._valid(subject='Hi'))
        assert 'subject' in errors

    def test_multiple_errors_returned(self):
        _, errors = validate_contact({'name': '', 'email': 'bad', 'subject': '', 'message': ''})
        assert len(errors) >= 3

    def test_all_fields_html_escaped(self):
        cleaned, _ = validate_contact(self._valid(
            name='<b>Test</b>',
            message='<img src=x onerror=alert(1)> bearings please',
        ))
        assert '<b>' not in cleaned['name']
        assert '<img' not in cleaned['message']
