from django.conf import settings


def seo_globals(request):
    return {
        "site_url": settings.SITE_URL,
        "seo_indexing_enabled": settings.SEO_INDEXING_ENABLED,
    }
