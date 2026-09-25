from django.db import transaction
from django.db.models import F

from .models import Order, Product


def reserve_order_inventory(order):
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.inventory_deducted:
            return True

        quantities = {}
        for item in locked_order.items.all().order_by("product_id", "pk"):
            quantities[item.product_id] = (
                quantities.get(item.product_id, 0) + item.quantity
            )
        if not quantities:
            return False

        products = {
            product.pk: product
            for product in Product.objects.select_for_update()
            .filter(pk__in=quantities)
            .order_by("pk")
        }
        if len(products) != len(quantities) or any(
            products[product_id].stock < quantity
            for product_id, quantity in quantities.items()
        ):
            return False

        for product_id, quantity in quantities.items():
            product = products[product_id]
            product.stock -= quantity
            product.save(update_fields=["stock"])

        locked_order.inventory_deducted = True
        locked_order.save(update_fields=["inventory_deducted"])
        return True


def release_order_inventory(order):
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if not locked_order.inventory_deducted or locked_order.is_paid:
            return

        for item in locked_order.items.all().order_by("product_id"):
            Product.objects.filter(pk=item.product_id).update(
                stock=F("stock") + item.quantity
            )

        locked_order.inventory_deducted = False
        locked_order.save(update_fields=["inventory_deducted"])


def cancel_order_and_release_inventory(order):
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.is_paid or locked_order.status != "pending":
            return False

        locked_order.status = "cancelled"
        locked_order.save(update_fields=["status"])
        release_order_inventory(locked_order)
        return True
