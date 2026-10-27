"""Response hardening for everything under /360/ (the HTML shell and the JSON
API): keep the internal tool out of search indexes and out of shared/browser
caches, since responses are per-user and contain customer data."""


class ThreeSixtyResponseHeadersMiddleware:
    PREFIX = '/360/'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(self.PREFIX):
            response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
            response['Cache-Control'] = 'no-store, private'
            response['Referrer-Policy'] = 'same-origin'
        return response
