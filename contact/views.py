"""
contact/views.py — validated contact form with rate limiting
"""
import json, logging, resend
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.conf import settings

from .models import ContactMessage
from core.validators import validate_contact

logger = logging.getLogger(__name__)


def _rate_limited(request, limit=5, window=300):
    """Max 5 contact form submissions per IP per 5 minutes."""
    ip  = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
           or request.META.get('REMOTE_ADDR', 'unknown'))
    key = f'contact_rl:{ip}'
    count = cache.get(key, 0)
    if count >= limit:
        return True
    cache.set(key, count + 1, timeout=window)
    return False


def contact(request):
    return render(request, 'contact/contact.html')


@require_POST
def send_message(request):
    """
    POST /contact/send/
    Rate-limited, validated contact form submission.
    """
    if _rate_limited(request):
        return JsonResponse(
            {'success': False, 'message': 'Too many submissions. Please try again later.'},
            status=429,
        )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid request format.'}, status=400)

    cleaned, errors = validate_contact(data)
    if errors:
        return JsonResponse(
            {'success': False, 'message': next(iter(errors.values())), 'errors': errors},
            status=400,
        )

    msg = ContactMessage.objects.create(
        name=cleaned['name'],
        email=cleaned['email'],
        phone=cleaned['phone'],
        subject=cleaned['subject'],
        message=cleaned['message'],
    )

    if getattr(settings, 'RESEND_API_KEY', ''):
        try:
            resend.api_key = settings.RESEND_API_KEY
            resend.Emails.send({
                'from':    settings.DEFAULT_FROM_EMAIL,
                'to':      [settings.COMPANY_EMAIL],
                'subject': f'[Anupam Bearings] Contact Form: {msg.subject}',
                'html': (
                    f'<h2>New Contact Form Message</h2>'
                    f'<p><b>Name:</b> {msg.name}</p>'
                    f'<p><b>Email:</b> {msg.email}</p>'
                    f'<p><b>Phone:</b> {msg.phone or "—"}</p>'
                    f'<p><b>Subject:</b> {msg.subject}</p>'
                    f'<p><b>Message:</b><br>{msg.message}</p>'
                ),
            })
        except Exception as e:
            logger.warning(f'Resend failed: {e}')

    return JsonResponse({'success': True, 'message': 'Message sent! We\'ll respond within 24 hours.'})
