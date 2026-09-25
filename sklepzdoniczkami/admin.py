from datetime import timedelta

import stripe
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from .models import Category, Order, OrderItem, Product
from .services import release_order_inventory, reserve_order_inventory


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status", self.instance.status)
        is_paid = cleaned_data.get("is_paid", self.instance.is_paid)
        payment_method = cleaned_data.get(
            "payment_method",
            self.instance.payment_method,
        )

        if self.instance.pk and self.instance.is_paid and not is_paid:
            self.add_error("is_paid", "Nie można cofnąć potwierdzonej płatności.")
        if payment_method == "card" and is_paid and not self.instance.is_paid:
            self.add_error(
                "is_paid",
                "Płatność kartą potwierdza wyłącznie Stripe.",
            )
        if status == "paid" and not is_paid:
            self.add_error("status", "Status „opłacone” wymaga potwierdzonej płatności.")
        if (
            self.instance.pk
            and self.instance.status == "cancelled"
            and status != "cancelled"
        ):
            self.add_error("status", "Anulowanego zamówienia nie można ponownie otworzyć.")
        if self.instance.is_paid and status == "pending":
            self.add_error(
                "status",
                "Opłaconego zamówienia nie można cofnąć do statusu oczekującego.",
            )
        if status in {"processing", "shipped"} and not is_paid:
            self.add_error(
                "status",
                "Nie można realizować ani wysłać nieopłaconego zamówienia.",
            )
        if status == "cancelled" and self.instance.is_paid:
            self.add_error(
                "status",
                "Anulowanie opłaconego zamówienia wymaga osobnej obsługi zwrotu.",
            )
        if (
            status == "cancelled"
            and self.instance.inventory_deducted
            and self.instance.payment_method == "card"
            and not self.instance.stripe_checkout_session_id
            and timezone.now() < self.instance.created_at + timedelta(hours=25)
        ):
            self.add_error(
                "status",
                "Nie można anulować zamówienia, gdy trwa tworzenie sesji Stripe.",
            )

        return cleaned_data


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "quantity", "unit_price")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = ("id", "first_name", "last_name", "status", "payment_method", "shipping_method", "total", "created_at")
    list_filter = ("status", "payment_method", "shipping_method", "is_paid")
    search_fields = ("first_name", "last_name", "email", "address")
    inlines = [OrderItemInline]
    readonly_fields = (
        "created_at",
        "updated_at",
        "paid_at",
        "stripe_checkout_session_id",
        "stripe_payment_intent_id",
        "inventory_deducted",
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is None or obj.is_paid or obj.payment_method == "card":
            fields.append("is_paid")
        if obj and (
            obj.stripe_checkout_session_id
            or obj.inventory_deducted
            or obj.is_paid
        ):
            fields.extend(("payment_method", "shipping_method", "shipping_cost"))
        return tuple(fields)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            previous = (
                Order.objects.select_for_update().filter(pk=obj.pk).first()
                if change
                else None
            )
            was_cancelled = previous is not None and previous.status == "cancelled"
            state_changed = previous is not None and (
                form.initial.get("status", previous.status) != previous.status
                or form.initial.get("is_paid", previous.is_paid) != previous.is_paid
                or form.initial.get("payment_method", previous.payment_method)
                != previous.payment_method
                or obj.stripe_checkout_session_id
                != previous.stripe_checkout_session_id
                or obj.stripe_payment_intent_id
                != previous.stripe_payment_intent_id
                or obj.paid_at != previous.paid_at
                or obj.inventory_deducted != previous.inventory_deducted
            )
            if state_changed:
                messages.warning(
                    request,
                    "Stan płatności lub zamówienia zmienił się w trakcie edycji. "
                    "Zachowano aktualny stan; odśwież stronę przed kolejną zmianą.",
                )
                obj.status = previous.status
                obj.is_paid = previous.is_paid
                obj.payment_method = previous.payment_method
                obj.stripe_checkout_session_id = previous.stripe_checkout_session_id
                obj.stripe_payment_intent_id = previous.stripe_payment_intent_id
                obj.paid_at = previous.paid_at
                obj.inventory_deducted = previous.inventory_deducted

            if (
                not state_changed
                and obj.status == "cancelled"
                and previous is not None
                and previous.status == "pending"
                and not previous.is_paid
                and previous.stripe_checkout_session_id
            ):
                if not settings.STRIPE_SECRET_KEY:
                    messages.error(
                        request,
                        "Nie można anulować zamówienia: brak konfiguracji Stripe. "
                        "Sesja i rezerwacja pozostają aktywne.",
                    )
                    obj.status = previous.status
                    super().save_model(request, obj, form, change)
                    return
                try:
                    stripe.checkout.Session.expire(
                        previous.stripe_checkout_session_id
                    )
                except stripe.error.StripeError:
                    try:
                        session = stripe.checkout.Session.retrieve(
                            previous.stripe_checkout_session_id
                        )
                    except stripe.error.StripeError:
                        messages.error(
                            request,
                            "Nie udało się potwierdzić wygaśnięcia sesji Stripe. "
                            "Zapas pozostaje zarezerwowany.",
                        )
                        obj.status = previous.status
                        super().save_model(request, obj, form, change)
                        return
                    if session.status != "expired":
                        messages.error(
                            request,
                            "Sesja Stripe nadal nie wygasła. "
                            "Zapas pozostaje zarezerwowany.",
                        )
                        obj.status = previous.status
                        super().save_model(request, obj, form, change)
                        return
            if (
                obj.is_paid
                and previous is not None
                and not previous.is_paid
                and not previous.inventory_deducted
                and not reserve_order_inventory(previous)
            ):
                messages.error(
                    request,
                    "Nie można potwierdzić płatności: brak dostępnego zapasu "
                    "dla pozycji zamówienia.",
                )
                obj.is_paid = False
                obj.status = previous.status
                obj.inventory_deducted = previous.inventory_deducted
                super().save_model(request, obj, form, change)
                return
            if obj.is_paid and previous is not None and not previous.is_paid:
                obj.inventory_deducted = True
            if obj.is_paid and (previous is None or not previous.is_paid):
                obj.status = "paid"
                obj.paid_at = timezone.now()
            super().save_model(request, obj, form, change)
            if obj.status == "cancelled" and not was_cancelled:
                release_order_inventory(obj)
