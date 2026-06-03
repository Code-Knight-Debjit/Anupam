import json
from urllib.parse import urlsplit

from django.conf import settings

SITE_NAME = 'Anupam Bearings'
SITE_DESCRIPTION = (
    'Industrial bearings, bearing housings, linear motion products, power transmission products, '
    'Timken products, and engineering solutions for B2B buyers across India.'
)
SITE_LOGO_PATH = '/static/images/onlylogo.png'
SOCIAL_PROFILES = [
    'https://www.linkedin.com/company/anupam-bearings',
    'https://twitter.com/anupambearings',
]
PRIMARY_LOCATIONS = [
    {
        'name': 'Bengaluru',
        'telephone': '+91-98844-00741',
        'address': 'No. 128, Jigani Link Road, Bommasandra Industrial Area, Bengaluru, Karnataka 560099, India',
    },
    {
        'name': 'Chennai',
        'telephone': '044-4691-2265',
        'address': 'No. 3 (Old No. 2) Katchaleeswarar Pagoda Lane, Parrys, Chennai, Tamil Nadu 600001, India',
    },
]


def site_url() -> str:
    return getattr(settings, 'SITE_URL', 'https://anupambearings.com').rstrip('/')


def absolute_url(path: str) -> str:
    if not path:
        return site_url()
    parsed = urlsplit(path)
    if parsed.scheme:
        return path
    if path.startswith('/'):
        return f'{site_url()}{path}'
    return f"{site_url()}/{path.lstrip('/')}"


def build_canonical_url(request, *, path: str | None = None) -> str:
    canonical_path = path if path is not None else request.path
    return absolute_url(canonical_path)


def _serialize_schema(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, separators=(',', ':'))


def organization_schema() -> dict:
    return {
        '@context': 'https://schema.org',
        '@type': 'Organization',
        '@id': f'{site_url()}#organization',
        'name': SITE_NAME,
        'alternateName': 'Anupam Bearings India',
        'url': site_url(),
        'logo': absolute_url(SITE_LOGO_PATH),
        'description': SITE_DESCRIPTION,
        'sameAs': SOCIAL_PROFILES,
        'contactPoint': [
            {
                '@type': 'ContactPoint',
                'telephone': '+91-98844-00741',
                'contactType': 'sales',
                'areaServed': 'IN',
                'availableLanguage': ['en', 'hi'],
            },
            {
                '@type': 'ContactPoint',
                'telephone': '044-4691-2265',
                'contactType': 'sales',
                'areaServed': 'IN',
                'availableLanguage': ['en', 'ta'],
            },
        ],
    }


def website_schema() -> dict:
    return {
        '@context': 'https://schema.org',
        '@type': 'WebSite',
        '@id': f'{site_url()}#website',
        'url': site_url(),
        'name': SITE_NAME,
        'alternateName': 'Anupam Bearings India',
        'publisher': {'@id': f'{site_url()}#organization'},
        'potentialAction': {
            '@type': 'SearchAction',
            'target': f'{site_url()}/products/?q={{search_term_string}}',
            'query-input': 'required name=search_term_string',
        },
    }


def local_business_schema(location: dict) -> dict:
    return {
        '@context': 'https://schema.org',
        '@type': 'LocalBusiness',
        '@id': f"{site_url()}#{location['name'].lower()}-location",
        'name': f"{SITE_NAME} {location['name']}",
        'url': site_url(),
        'telephone': location['telephone'],
        'address': {
            '@type': 'PostalAddress',
            'streetAddress': location['address'],
            'addressCountry': 'IN',
        },
        'parentOrganization': {'@id': f'{site_url()}#organization'},
        'areaServed': ['Bengaluru', 'Chennai', 'Karnataka', 'Tamil Nadu', 'India'],
        'sameAs': SOCIAL_PROFILES,
    }


def breadcrumb_schema(items: list[dict]) -> dict:
    return {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {
                '@type': 'ListItem',
                'position': index + 1,
                'name': item['name'],
                'item': absolute_url(item['item']),
            }
            for index, item in enumerate(items)
        ],
    }


def faq_schema(items: list[dict]) -> dict:
    return {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        'mainEntity': [
            {
                '@type': 'Question',
                'name': item['question'],
                'acceptedAnswer': {
                    '@type': 'Answer',
                    'text': item['answer'],
                },
            }
            for item in items
        ],
    }


def product_schema(product, image_urls: list[str], canonical_url: str) -> dict:
    schema = {
        '@context': 'https://schema.org',
        '@type': 'Product',
        '@id': f'{canonical_url}#product',
        'name': product.name,
        'description': (product.description or '')[:300],
        'sku': product.slug,
        'url': canonical_url,
        'brand': {
            '@type': 'Brand',
            'name': SITE_NAME,
        },
        'manufacturer': {
            '@type': 'Organization',
            'name': SITE_NAME,
            'url': site_url(),
        },
        'category': product.category.name if getattr(product, 'category', None) else 'Industrial Bearing',
    }
    if image_urls:
        schema['image'] = image_urls
    return schema


def build_seo_context(
    request,
    *,
    title: str | None = None,
    description: str | None = None,
    canonical_url: str | None = None,
    robots: str | None = None,
    og_type: str = 'website',
    og_image: str | None = None,
    twitter_image: str | None = None,
    json_ld: list[dict] | None = None,
) -> dict:
    schemas = [website_schema(), organization_schema()]
    if json_ld:
        schemas.extend([schema for schema in json_ld if schema])

    resolved_canonical = canonical_url or build_canonical_url(request)
    resolved_description = description or SITE_DESCRIPTION
    resolved_title = title or SITE_NAME
    resolved_og_image = absolute_url(og_image or SITE_LOGO_PATH)
    resolved_twitter_image = absolute_url(twitter_image or SITE_LOGO_PATH)

    return {
        'seo_site_name': SITE_NAME,
        'seo_site_url': site_url(),
        'seo_title': resolved_title,
        'seo_meta_description': resolved_description,
        'seo_canonical_url': resolved_canonical,
        'seo_meta_robots': robots or 'index,follow,max-snippet:-1,max-image-preview:large,max-video-preview:-1',
        'seo_og_type': og_type,
        'seo_og_site_name': SITE_NAME,
        'seo_og_title': title or SITE_NAME,
        'seo_og_description': description or SITE_DESCRIPTION,
        'seo_og_image': resolved_og_image,
        'seo_twitter_title': title or SITE_NAME,
        'seo_twitter_description': description or SITE_DESCRIPTION,
        'seo_twitter_image': resolved_twitter_image,
        'seo_json_ld': [_serialize_schema(schema) for schema in schemas],
    }
