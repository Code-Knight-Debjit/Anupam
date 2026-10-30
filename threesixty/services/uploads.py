"""Validation for user-uploaded branding images (logo, QR, footer, ...).

Checked by *content* (Pillow decodes it), not by file name or the browser's
claimed content type. SVG is deliberately not accepted — it can carry script.
"""
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 2 * 1024 * 1024
ALLOWED_FORMATS = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}


def validate_image_upload(uploaded):
    if uploaded.size > MAX_IMAGE_BYTES:
        raise ValidationError(f'Image is too large (max {MAX_IMAGE_BYTES // (1024 * 1024)} MB).')
    try:
        with Image.open(uploaded) as img:
            fmt = img.format
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError('That file is not a valid image.')
    finally:
        uploaded.seek(0)
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError('Only PNG, JPEG or WebP images are allowed.')
    return ALLOWED_FORMATS[fmt]
