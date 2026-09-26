from django.db import migrations


def create_sample_products(apps, schema_editor):
    Category = apps.get_model('sklepzdoniczkami', 'Category')
    Product = apps.get_model('sklepzdoniczkami', 'Product')

    cat, _ = Category.objects.get_or_create(name='Doniczki', slug='doniczki')

    sample = [
        {
            'name': 'Doniczka Ceramiczna Płytka',
            'slug': 'doniczka-ceramiczna-plytka',
            'description': 'Klasyczna ceramiczna doniczka, idealna do małych roślin i ziół.',
            'price': '29.90',
            'stock': 12,
            'image': '/media/products/plant-1.svg',
        },
        {
            'name': 'Doniczka Betonowa Mini',
            'slug': 'doniczka-betonowa-mini',
            'description': 'Nowoczesna mini doniczka z betonu, surowy i minimalistyczny wygląd.',
            'price': '39.90',
            'stock': 8,
            'image': '/media/products/plant-2.svg',
        },
        {
            'name': 'Doniczka Zewnętrzna Duża',
            'slug': 'doniczka-zewnetrzna-duza',
            'description': 'Duża, mrozoodporna doniczka na taras lub do ogrodu.',
            'price': '89.00',
            'stock': 5,
            'image': '/media/products/plant-3.svg',
        },
    ]

    for p in sample:
        Product.objects.update_or_create(
            slug=p['slug'],
            defaults={
                'category': cat,
                'name': p['name'],
                'description': p['description'],
                'price': p['price'],
                'stock': p['stock'],
                'image': p['image'],
                'is_active': True,
            }
        )


def reverse_func(apps, schema_editor):
    Product = apps.get_model('sklepzdoniczkami', 'Product')
    Product.objects.filter(slug__in=['doniczka-ceramiczna-plytka','doniczka-betonowa-mini','doniczka-zewnetrzna-duza']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('sklepzdoniczkami', '0008_alter_product_image'),
    ]

    operations = [
        migrations.RunPython(create_sample_products, reverse_func),
    ]
