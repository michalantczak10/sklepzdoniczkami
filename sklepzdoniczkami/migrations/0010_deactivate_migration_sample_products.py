from django.db import migrations


SAMPLE_PRODUCT_SLUGS = (
    "doniczka-ceramiczna-plytka",
    "doniczka-betonowa-mini",
    "doniczka-zewnetrzna-duza",
)


def deactivate_legacy_demo_products(apps, schema_editor):
    Product = apps.get_model("sklepzdoniczkami", "Product")
    Product.objects.filter(slug__in=SAMPLE_PRODUCT_SLUGS).update(
        is_active=False,
        image="",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("sklepzdoniczkami", "0009_create_sample_products"),
    ]

    operations = [
        migrations.RunPython(
            deactivate_legacy_demo_products,
            migrations.RunPython.noop,
        ),
    ]
