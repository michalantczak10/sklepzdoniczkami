from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("sklepzdoniczkami", "0004_order_stripe_checkout_session_id_and_more"),
    ]

    operations = [
        migrations.AlterModelTable(
            name="category",
            table="sklepzdoniczkami_category",
        ),
        migrations.AlterModelTable(
            name="product",
            table="sklepzdoniczkami_product",
        ),
        migrations.AlterModelTable(
            name="order",
            table="sklepzdoniczkami_order",
        ),
        migrations.AlterModelTable(
            name="orderitem",
            table="sklepzdoniczkami_orderitem",
        ),
    ]
