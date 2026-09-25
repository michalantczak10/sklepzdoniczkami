from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import connection
from django.core import signing
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .admin import OrderAdmin, OrderItemInline
from .models import Category, Order, OrderItem, Product
from .services import release_order_inventory
from .views import (
    ORDER_ACCESS_SALT,
    ORDER_ACCESS_TOKEN_MAX_AGE,
    make_order_access_token,
    stripe_checkout,
)

inventory_migration = import_module(
    "sklepzdoniczkami.migrations.0006_order_inventory_deducted"
)


class ProductCatalogTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Elektronika", slug="elektronika")
        self.product = Product.objects.create(
            category=self.category,
            name="Laptop Pro",
            slug="laptop-pro",
            description="Nowoczesny laptop do pracy i nauki.",
            price=3499.99,
            stock=10,
            is_active=True,
        )

    def test_product_list_page_renders(self):
        response = self.client.get(reverse("sklepzdoniczkami:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laptop Pro")

    def test_product_search_filters_results(self):
        response = self.client.get(reverse("sklepzdoniczkami:products"), {"q": "laptop"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laptop Pro")

    def test_product_detail_page_renders(self):
        response = self.client.get(reverse("sklepzdoniczkami:product", kwargs={"slug": self.product.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laptop Pro")
        self.assertContains(response, "Nowoczesny laptop do pracy i nauki.")

    def test_add_to_cart_and_checkout(self):
        add_response = self.client.post(
            reverse("sklepzdoniczkami:add_to_cart", kwargs={"product_id": self.product.pk})
        )
        self.assertEqual(add_response.status_code, 302)
        self.assertEqual(self.client.session["cart"][str(self.product.pk)], 1)

        checkout_response = self.client.post(
            reverse("sklepzdoniczkami:checkout"),
            {
                "first_name": "Anna",
                "last_name": "Kowalska",
                "email": "anna@example.com",
                "phone": "123456789",
                "address": "ul. Testowa 1",
                "city": "Warszawa",
                "postal_code": "00-001",
                "comments": "Dzień dobry",
            },
        )
        self.assertEqual(checkout_response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        order = Order.objects.get()
        self.assertEqual(self.product.stock, 9)
        self.assertTrue(order.inventory_deducted)
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_checkout_rejects_quantity_above_current_stock(self):
        self.client.post(
            reverse("sklepzdoniczkami:add_to_cart", kwargs={"product_id": self.product.pk})
        )
        self.product.stock = 0
        self.product.save(update_fields=["stock"])

        response = self.client.post(
            reverse("sklepzdoniczkami:checkout"),
            {
                "first_name": "Anna",
                "last_name": "Kowalska",
                "email": "anna@example.com",
                "address": "ul. Testowa 1",
                "city": "Warszawa",
                "postal_code": "00-001",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.client.session["cart"][str(self.product.pk)], 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    def test_inventory_migration_reserves_existing_pending_orders(self):
        self.product.stock = 5
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            status="pending",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=self.product.price,
        )

        inventory_migration.reserve_existing_pending_orders(
            apps,
            SimpleNamespace(connection=connection),
        )

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertTrue(order.inventory_deducted)
        self.assertEqual(self.product.stock, 3)

    def test_inventory_migration_leaves_unreservable_order_unreserved(self):
        self.product.stock = 1
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            status="pending",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=self.product.price,
        )

        inventory_migration.reserve_existing_pending_orders(
            apps,
            SimpleNamespace(connection=connection),
        )

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertFalse(order.inventory_deducted)
        self.assertEqual(self.product.stock, 1)

    def test_add_to_cart_rejects_out_of_stock_product(self):
        self.product.stock = 0
        self.product.save(update_fields=["stock"])

        response = self.client.post(
            reverse("sklepzdoniczkami:add_to_cart", kwargs={"product_id": self.product.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_checkout_rejects_invalid_payment_and_shipping_methods(self):
        self.client.post(
            reverse("sklepzdoniczkami:add_to_cart", kwargs={"product_id": self.product.pk})
        )
        checkout_url = reverse("sklepzdoniczkami:checkout")
        form_data = {
            "first_name": "Anna",
            "last_name": "Kowalska",
            "email": "anna@example.com",
            "address": "ul. Testowa 1",
            "city": "Warszawa",
            "postal_code": "00-001",
        }

        for invalid_field, invalid_value in (
            ("payment_method", "invalid"),
            ("shipping_method", "invalid"),
        ):
            with self.subTest(field=invalid_field):
                response = self.client.post(
                    checkout_url,
                    {**form_data, invalid_field: invalid_value},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(Order.objects.count(), 0)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    @patch("sklepzdoniczkami.views.stripe.checkout.Session.expire")
    def test_cancelled_card_order_releases_inventory_once(self, mock_expire):
        self.product.stock = 9
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            stripe_checkout_session_id="cs_test_cancel",
            inventory_deducted=True,
        )
        mock_expire.return_value = SimpleNamespace(status="expired")
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )
        token = make_order_access_token(order)
        cancel_url = reverse(
            "sklepzdoniczkami:payment_cancel",
            kwargs={"order_token": token},
        )

        self.client.get(cancel_url)
        self.client.get(cancel_url)

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        self.assertFalse(order.inventory_deducted)
        self.assertEqual(self.product.stock, 10)
        mock_expire.assert_called_once_with("cs_test_cancel")

    def test_payment_cancel_does_not_release_non_card_order_inventory(self):
        self.product.stock = 9
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="transfer",
            inventory_deducted=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )
        token = make_order_access_token(order)

        response = self.client.get(
            reverse("sklepzdoniczkami:payment_cancel", kwargs={"order_token": token})
        )

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(order.status, "pending")
        self.assertTrue(order.inventory_deducted)
        self.assertEqual(self.product.stock, 9)

    def test_payment_cancel_keeps_inventory_when_stripe_session_cannot_be_expired(self):
        self.product.stock = 9
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            stripe_checkout_session_id="cs_test_active",
            inventory_deducted=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )
        token = make_order_access_token(order)

        with (
            patch(
                "sklepzdoniczkami.views.stripe.checkout.Session.expire",
                side_effect=stripe.error.InvalidRequestError("still active", "id"),
            ),
            patch(
                "sklepzdoniczkami.views.stripe.checkout.Session.retrieve",
                return_value=SimpleNamespace(status="open", payment_status="unpaid"),
            ),
        ):
            response = self.client.get(
                reverse("sklepzdoniczkami:payment_cancel", kwargs={"order_token": token})
            )

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(order.status, "pending")
        self.assertTrue(order.inventory_deducted)
        self.assertEqual(self.product.stock, 9)

    @patch(
        "sklepzdoniczkami.views.stripe.checkout.Session.create",
        side_effect=stripe.error.InvalidRequestError("invalid checkout", "line_items"),
    )
    def test_rejected_stripe_checkout_cancels_order_and_releases_inventory(self, mock_create):
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            inventory_deducted=True,
        )
        self.product.stock = 9
        self.product.save(update_fields=["stock"])
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )
        token = make_order_access_token(order)

        response = self.client.get(
            reverse("sklepzdoniczkami:stripe_checkout", kwargs={"order_token": token})
        )

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(order.status, "cancelled")
        self.assertFalse(order.inventory_deducted)
        self.assertEqual(self.product.stock, 10)
        mock_create.assert_called_once()

    @patch("sklepzdoniczkami.views.stripe.Webhook.construct_event")
    def test_expired_stripe_session_cancels_order_and_releases_inventory(self, mock_construct_event):
        self.product.stock = 9
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            inventory_deducted=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )
        mock_construct_event.return_value = {
            "type": "checkout.session.expired",
            "data": {
                "object": SimpleNamespace(
                    id="cs_test_expired",
                    metadata=SimpleNamespace(order_id=str(order.pk)),
                )
            },
        }

        response = self.client.post(
            reverse("sklepzdoniczkami:stripe_webhook"),
            data=b"payload",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test-signature",
        )

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, "cancelled")
        self.assertFalse(order.inventory_deducted)
        self.assertEqual(self.product.stock, 10)

    @patch("sklepzdoniczkami.views.stripe.checkout.Session.retrieve")
    def test_cancelled_order_cannot_be_marked_paid_by_success_redirect(self, mock_retrieve):
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            stripe_checkout_session_id="cs_test_cancelled",
            status="cancelled",
        )
        token = make_order_access_token(order)

        response = self.client.get(
            reverse(
                "sklepzdoniczkami:payment_success",
                kwargs={"order_token": token},
            ),
            {"session_id": "cs_test_cancelled"},
        )

        order.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(order.is_paid)
        self.assertEqual(order.status, "cancelled")
        mock_retrieve.assert_not_called()

    def test_transient_stripe_checkout_error_retries_with_same_idempotency_key(self):
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            inventory_deducted=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )
        token = make_order_access_token(order)
        created_session = SimpleNamespace(
            id="cs_test_retry",
            url="https://checkout.stripe.com/retry",
        )

        with patch(
            "sklepzdoniczkami.views.stripe.checkout.Session.create",
            side_effect=[
                stripe.error.APIConnectionError("temporary timeout"),
                created_session,
            ],
        ) as mock_create:
            response = self.client.get(
                reverse(
                    "sklepzdoniczkami:stripe_checkout",
                    kwargs={"order_token": token},
                )
            )

        order.refresh_from_db()
        self.assertRedirects(
            response,
            created_session.url,
            fetch_redirect_response=False,
        )
        self.assertEqual(mock_create.call_count, 2)
        self.assertEqual(
            mock_create.call_args_list[0].kwargs["idempotency_key"],
            mock_create.call_args_list[1].kwargs["idempotency_key"],
        )
        self.assertEqual(order.stripe_checkout_session_id, created_session.id)

    def test_idempotency_conflict_keeps_inventory_reserved(self):
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            inventory_deducted=True,
        )
        self.product.stock = 9
        self.product.save(update_fields=["stock"])
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )
        token = make_order_access_token(order)

        with patch(
            "sklepzdoniczkami.views.stripe.checkout.Session.create",
            side_effect=[
                stripe.error.APIConnectionError("temporary timeout"),
                stripe.error.InvalidRequestError(
                    "request is still processing",
                    "idempotency_key",
                    code="idempotency_key_in_use",
                ),
            ],
        ):
            response = self.client.get(
                reverse(
                    "sklepzdoniczkami:stripe_checkout",
                    kwargs={"order_token": token},
                )
            )

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(order.status, "pending")
        self.assertTrue(order.inventory_deducted)
        self.assertEqual(self.product.stock, 9)

    def test_checkout_session_is_expired_if_order_was_cancelled_during_creation(self):
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            inventory_deducted=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )
        token = make_order_access_token(order)
        created_session = SimpleNamespace(
            id="cs_test_race",
            url="https://checkout.stripe.com/race",
        )

        def create_session(**kwargs):
            Order.objects.filter(pk=order.pk).update(
                status="cancelled",
                inventory_deducted=False,
            )
            return created_session

        with (
            patch(
                "sklepzdoniczkami.views.stripe.checkout.Session.create",
                side_effect=create_session,
            ),
            patch(
                "sklepzdoniczkami.views.stripe.checkout.Session.expire"
            ) as mock_expire,
        ):
            response = self.client.get(
                reverse(
                    "sklepzdoniczkami:stripe_checkout",
                    kwargs={"order_token": token},
                )
            )

        order.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response["Location"], created_session.url)
        self.assertEqual(order.status, "cancelled")
        mock_expire.assert_called_once_with(created_session.id)

    def test_paid_order_inventory_is_not_released(self):
        self.product.stock = 9
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            is_paid=True,
            status="paid",
            inventory_deducted=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )

        release_order_inventory(order)

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertTrue(order.inventory_deducted)
        self.assertEqual(self.product.stock, 9)

    def test_order_admin_protects_paid_flag_and_active_checkout_payment_method(self):
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            stripe_checkout_session_id="cs_test_active",
            inventory_deducted=True,
        )
        request = RequestFactory().get("/admin/")
        request.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="StrongPass123!",
        )
        order_admin = OrderAdmin(Order, admin.site)
        inline_admin = OrderItemInline(Order, admin.site)

        readonly_fields = order_admin.get_readonly_fields(request, order)
        self.assertIn("is_paid", readonly_fields)
        self.assertIn("payment_method", readonly_fields)
        self.assertIn("shipping_method", readonly_fields)
        self.assertIn("shipping_cost", readonly_fields)
        self.assertIn("stripe_checkout_session_id", readonly_fields)
        self.assertIn("inventory_deducted", readonly_fields)
        self.assertFalse(order_admin.has_delete_permission(request, order))
        self.assertFalse(order_admin.has_add_permission(request))
        self.assertEqual(
            inline_admin.get_readonly_fields(request, order),
            ("product", "quantity", "unit_price"),
        )
        self.assertFalse(inline_admin.has_add_permission(request, order))
        self.assertFalse(inline_admin.has_delete_permission(request, order))
        order.inventory_deducted = False
        order.status = "cancelled"
        self.assertFalse(inline_admin.has_add_permission(request, order))
        self.assertFalse(inline_admin.has_delete_permission(request, order))

    def test_admin_stale_edit_preserves_webhook_payment_state(self):
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            stripe_checkout_session_id="cs_test_admin_race",
        )
        stale_order = Order.objects.get(pk=order.pk)
        Order.objects.filter(pk=order.pk).update(
            is_paid=True,
            status="paid",
            stripe_payment_intent_id="pi_test_admin_race",
        )
        request = RequestFactory().post("/admin/")
        request.user = get_user_model().objects.create_superuser(
            username="admin-race",
            email="admin-race@example.com",
            password="StrongPass123!",
        )
        request.session = {}
        request._messages = FallbackStorage(request)
        form = SimpleNamespace(
            initial={
                "status": "pending",
                "is_paid": False,
                "payment_method": "card",
            }
        )

        OrderAdmin(Order, admin.site).save_model(
            request,
            stale_order,
            form,
            change=True,
        )

        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, "paid")
        self.assertEqual(order.stripe_payment_intent_id, "pi_test_admin_race")

    @patch("sklepzdoniczkami.views.stripe.Webhook.construct_event")
    def test_completed_stripe_session_does_not_pay_cancelled_order(self, mock_construct_event):
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            stripe_checkout_session_id="cs_test_cancelled",
            status="cancelled",
        )
        mock_construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": SimpleNamespace(
                    id="cs_test_cancelled",
                    metadata=SimpleNamespace(order_id=str(order.pk)),
                    payment_status="paid",
                    payment_intent="pi_test_123",
                )
            },
        }

        response = self.client.post(
            reverse("sklepzdoniczkami:stripe_webhook"),
            data=b"payload",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test-signature",
        )

        order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(order.is_paid)
        self.assertEqual(order.status, "cancelled")

    @patch("sklepzdoniczkami.views.stripe.Webhook.construct_event")
    def test_completed_legacy_session_reserves_stock_before_marking_paid(
        self,
        mock_construct_event,
    ):
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            stripe_checkout_session_id="cs_test_legacy",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )
        mock_construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": SimpleNamespace(
                    id="cs_test_legacy",
                    metadata=SimpleNamespace(order_id=str(order.pk)),
                    payment_intent="pi_test_legacy",
                    payment_status="paid",
                )
            },
        }

        response = self.client.post(
            reverse("sklepzdoniczkami:stripe_webhook"),
            data=b"payload",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test-signature",
        )

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(order.is_paid)
        self.assertTrue(order.inventory_deducted)
        self.assertEqual(self.product.stock, 9)

    @patch("sklepzdoniczkami.views.stripe.Refund.create")
    @patch("sklepzdoniczkami.views.stripe.Webhook.construct_event")
    def test_completed_unreserved_order_is_refunded_when_stock_is_unavailable(
        self,
        mock_construct_event,
        mock_refund,
    ):
        self.product.stock = 0
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            stripe_checkout_session_id="cs_test_unreserved",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )
        mock_construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": SimpleNamespace(
                    id="cs_test_unreserved",
                    metadata=SimpleNamespace(order_id=str(order.pk)),
                    payment_intent="pi_test_unreserved",
                    payment_status="paid",
                )
            },
        }
        mock_refund.return_value = SimpleNamespace(status="succeeded")

        response = self.client.post(
            reverse("sklepzdoniczkami:stripe_webhook"),
            data=b"payload",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test-signature",
        )

        order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(order.is_paid)
        self.assertEqual(order.status, "cancelled")
        mock_refund.assert_called_once_with(
            payment_intent="pi_test_unreserved",
            idempotency_key=f"unreserved-order-refund-{order.pk}",
        )

    def test_user_registration_and_profile(self):
        response = self.client.post(
            reverse("sklepzdoniczkami:register"),
            {"username": "testuser", "password1": "StrongPass123!", "password2": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(username="testuser").exists())

        response = self.client.get(reverse("sklepzdoniczkami:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "testuser")

    @patch("sklepzdoniczkami.views.stripe.checkout.Session.create")
    def test_stripe_checkout_redirects(self, mock_session_create):
        mock_session_create.return_value = type("Session", (), {"id": "cs_test_123", "url": "https://checkout.stripe.com/test"})()

        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            shipping_method="courier",
            shipping_cost=19.99,
            inventory_deducted=True,
        )
        OrderItem.objects.create(order=order, product=self.product, quantity=1, unit_price=self.product.price)

        token = make_order_access_token(order)
        request = RequestFactory().get(
            reverse(
                "sklepzdoniczkami:stripe_checkout",
                kwargs={"order_token": token},
            )
        )
        request.session = {}
        response = stripe_checkout(request, token)

        self.assertEqual(response.status_code, 302)
        self.assertIn("https://checkout.stripe.com/test", response["Location"])

    def test_order_endpoints_reject_unsigned_order_ids(self):
        endpoint_names = (
            "sklepzdoniczkami:stripe_checkout",
            "sklepzdoniczkami:checkout_success",
            "sklepzdoniczkami:payment_success",
            "sklepzdoniczkami:payment_cancel",
        )

        for endpoint_name in endpoint_names:
            response = self.client.get(
                reverse(endpoint_name, kwargs={"order_token": "1"})
            )
            self.assertEqual(response.status_code, 404)

    def test_signed_token_allows_order_confirmation(self):
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="transfer",
            shipping_method="courier",
            shipping_cost=19.99,
        )
        token = make_order_access_token(order)

        response = self.client.get(
            reverse(
                "sklepzdoniczkami:checkout_success",
                kwargs={"order_token": token},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"#{order.pk}")

    def test_expired_order_token_is_rejected(self):
        with patch("django.core.signing.time.time", return_value=1000):
            token = signing.dumps(1, salt=ORDER_ACCESS_SALT)

        with patch(
            "django.core.signing.time.time",
            return_value=1000 + ORDER_ACCESS_TOKEN_MAX_AGE + 1,
        ):
            response = self.client.get(
                reverse(
                    "sklepzdoniczkami:checkout_success",
                    kwargs={"order_token": token},
                )
            )

        self.assertEqual(response.status_code, 404)

    @patch("sklepzdoniczkami.views.stripe.checkout.Session.create")
    def test_paid_order_cannot_start_another_checkout(self, mock_session_create):
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            shipping_method="courier",
            shipping_cost=19.99,
            is_paid=True,
            status="paid",
        )
        token = make_order_access_token(order)

        response = self.client.get(
            reverse(
                "sklepzdoniczkami:stripe_checkout",
                kwargs={"order_token": token},
            )
        )

        self.assertRedirects(
            response,
            reverse("sklepzdoniczkami:checkout"),
            fetch_redirect_response=False,
        )
        mock_session_create.assert_not_called()

    @patch("sklepzdoniczkami.views.stripe.Webhook.construct_event")
    def test_stripe_webhook_is_idempotent(self, mock_construct_event):
        self.product.stock = 9
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            email="anna@example.com",
            address="ul. Testowa 1",
            city="Warszawa",
            postal_code="00-001",
            payment_method="card",
            shipping_method="courier",
            shipping_cost=19.99,
            inventory_deducted=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
        )
        mock_construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": SimpleNamespace(
                    id="cs_test_123",
                    metadata=SimpleNamespace(order_id=str(order.pk)),
                    payment_intent="pi_test_123",
                    payment_status="paid",
                )
            },
        }
        order.stripe_checkout_session_id = "cs_test_123"
        order.save(update_fields=["stripe_checkout_session_id"])

        webhook_url = reverse("sklepzdoniczkami:stripe_webhook")
        first_response = self.client.post(
            webhook_url,
            data=b"payload",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test-signature",
        )
        order.refresh_from_db()
        first_paid_at = order.paid_at

        second_response = self.client.post(
            webhook_url,
            data=b"payload",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test-signature",
        )
        order.refresh_from_db()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(order.is_paid)
        self.assertEqual(order.paid_at, first_paid_at)

    @patch("sklepzdoniczkami.views.stripe.Webhook.construct_event")
    def test_stripe_webhook_ignores_session_without_order_metadata(self, mock_construct_event):
        mock_construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {"object": SimpleNamespace(metadata=SimpleNamespace())},
        }

        response = self.client.post(
            reverse("sklepzdoniczkami:stripe_webhook"),
            data=b"payload",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test-signature",
        )

        self.assertEqual(response.status_code, 200)
