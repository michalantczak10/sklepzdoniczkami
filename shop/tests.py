from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .models import Category, Order, OrderItem, Product
from .views import (
    ORDER_ACCESS_SALT,
    ORDER_ACCESS_TOKEN_MAX_AGE,
    make_order_access_token,
    stripe_checkout,
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
        response = self.client.get(reverse("shop:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laptop Pro")

    def test_product_search_filters_results(self):
        response = self.client.get(reverse("shop:products"), {"q": "laptop"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laptop Pro")

    def test_product_detail_page_renders(self):
        response = self.client.get(reverse("shop:product", kwargs={"slug": self.product.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laptop Pro")
        self.assertContains(response, "Nowoczesny laptop do pracy i nauki.")

    def test_add_to_cart_and_checkout(self):
        add_response = self.client.post(reverse("shop:add_to_cart", kwargs={"product_id": self.product.pk}))
        self.assertEqual(add_response.status_code, 302)
        self.assertEqual(self.client.session["cart"][str(self.product.pk)], 1)

        checkout_response = self.client.post(
            reverse("shop:checkout"),
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
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_user_registration_and_profile(self):
        response = self.client.post(
            reverse("shop:register"),
            {"username": "testuser", "password1": "StrongPass123!", "password2": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(username="testuser").exists())

        response = self.client.get(reverse("shop:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "testuser")

    @patch("shop.views.stripe.checkout.Session.create")
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
        )
        OrderItem.objects.create(order=order, product=self.product, quantity=1, unit_price=self.product.price)

        token = make_order_access_token(order)
        request = RequestFactory().get(reverse("shop:stripe_checkout", kwargs={"order_token": token}))
        request.session = {}
        response = stripe_checkout(request, token)

        self.assertEqual(response.status_code, 302)
        self.assertIn("https://checkout.stripe.com/test", response["Location"])

    def test_order_endpoints_reject_unsigned_order_ids(self):
        endpoint_names = (
            "shop:stripe_checkout",
            "shop:checkout_success",
            "shop:payment_success",
            "shop:payment_cancel",
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
            reverse("shop:checkout_success", kwargs={"order_token": token})
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
                reverse("shop:checkout_success", kwargs={"order_token": token})
            )

        self.assertEqual(response.status_code, 404)

    @patch("shop.views.stripe.checkout.Session.create")
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
            reverse("shop:stripe_checkout", kwargs={"order_token": token})
        )

        self.assertRedirects(
            response,
            reverse("shop:checkout"),
            fetch_redirect_response=False,
        )
        mock_session_create.assert_not_called()

    @patch("shop.views.stripe.Webhook.construct_event")
    def test_stripe_webhook_is_idempotent(self, mock_construct_event):
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
        )
        mock_construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": SimpleNamespace(
                    metadata=SimpleNamespace(order_id=str(order.pk)),
                    payment_intent="pi_test_123",
                )
            },
        }

        webhook_url = reverse("shop:stripe_webhook")
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

    @patch("shop.views.stripe.Webhook.construct_event")
    def test_stripe_webhook_ignores_session_without_order_metadata(self, mock_construct_event):
        mock_construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {"object": SimpleNamespace(metadata=SimpleNamespace())},
        }

        response = self.client.post(
            reverse("shop:stripe_webhook"),
            data=b"payload",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test-signature",
        )

        self.assertEqual(response.status_code, 200)
