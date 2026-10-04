from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse

from .models import Category, Product


def robots_txt(request):
    if not settings.SEO_INDEXING_ENABLED:
        return HttpResponse(
            "User-agent: *\nDisallow: /\n",
            content_type="text/plain; charset=utf-8",
        )

    content = (
        "User-agent: *\n"
        "Disallow: /admin/\n"
        "Disallow: /cart/\n"
        "Disallow: /checkout/\n"
        "Disallow: /login/\n"
        "Disallow: /logout/\n"
        "Disallow: /profile/\n"
        f"Sitemap: {settings.SITE_URL}/sitemap.xml\n"
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def sitemap_xml(request):
    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
    urlset = Element("urlset", xmlns=namespace)
    public_paths = []
    if settings.SEO_INDEXING_ENABLED:
        public_paths.append(reverse("sklepzdoniczkami:home"))
        public_paths.extend(
            reverse("sklepzdoniczkami:category", kwargs={"slug": slug})
            for slug in Category.objects.filter(products__is_active=True)
            .values_list("slug", flat=True)
            .distinct()
        )
        public_paths.extend(
            reverse("sklepzdoniczkami:product", kwargs={"slug": slug})
            for slug in Product.objects.filter(is_active=True).values_list("slug", flat=True)
        )

    for path in public_paths:
        url = SubElement(urlset, f"{{{namespace}}}url")
        SubElement(url, f"{{{namespace}}}loc").text = f"{settings.SITE_URL}{path}"

    return HttpResponse(
        tostring(urlset, encoding="utf-8", xml_declaration=True),
        content_type="application/xml; charset=utf-8",
    )
