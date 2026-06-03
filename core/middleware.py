from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class CanonicalHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            getattr(settings, 'CANONICAL_HOST_REDIRECT', False)
            and request.method in {'GET', 'HEAD'}
            and not settings.DEBUG
        ):
            canonical_site = getattr(settings, 'SITE_URL', 'https://anupambearings.com').rstrip('/')
            current_site = f'{request.scheme}://{request.get_host().rstrip("/")}'
            if current_site != canonical_site:
                return HttpResponsePermanentRedirect(f'{canonical_site}{request.get_full_path()}')
        return self.get_response(request)
