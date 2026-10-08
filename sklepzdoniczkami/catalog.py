from django.db.models import Count, Q

from .models import Category, Product


POT_CATEGORY_SLUGS = ("doniczki", "betonowe", "drewniane", "plastikowe")
POT_CATEGORY_IMAGES = {
    "doniczki": "sklepzdoniczkami/img/categories/doniczki.svg",
    "betonowe": "sklepzdoniczkami/img/categories/betonowe.svg",
    "drewniane": "sklepzdoniczkami/img/categories/drewniane.svg",
    "plastikowe": "sklepzdoniczkami/img/categories/plastikowe.svg",
}
RETIRED_CATEGORY_SLUGS = ("rosliny-zielone", "preprod-rosliny-zielone")
RETIRED_PRODUCT_SLUGS = (
    "monstera-deliciosa",
    "preprod-monstera-deliciosa",
    "epipremnum-zlociste",
    "preprod-epipremnum-aureum",
)


def public_products():
    return Product.objects.filter(
        is_active=True,
        category__slug__in=POT_CATEGORY_SLUGS,
    )


def public_categories():
    return (
        Category.objects.filter(
            slug__in=POT_CATEGORY_SLUGS,
            products__is_active=True,
        )
        .annotate(product_count=Count("products", filter=Q(products__is_active=True)))
        .distinct()
        .order_by("name")
    )
