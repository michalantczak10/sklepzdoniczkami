from django.db import migrations


POT_CATEGORY_SLUGS = ("doniczki", "ceramiczne", "plastikowe", "cementowe")


def hide_non_pot_products(apps, schema_editor):
    Product = apps.get_model("sklepzdoniczkami", "Product")
    Product.objects.filter(is_active=True).exclude(
        category__slug__in=POT_CATEGORY_SLUGS
    ).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("sklepzdoniczkami", "0010_deactivate_migration_sample_products"),
    ]

    operations = [
        migrations.RunPython(hide_non_pot_products, migrations.RunPython.noop),
    ]
