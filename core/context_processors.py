from .seo import build_seo_context


def seo(request):
    return build_seo_context(request)
