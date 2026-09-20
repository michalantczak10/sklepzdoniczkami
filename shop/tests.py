from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .models import Category, Order, OrderItem, Product
from .views import stripe_checkout


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

        request = RequestFactory().get(reverse("shop:stripe_checkout", kwargs={"order_id": order.pk}))
        request.session = {}
        response = stripe_checkout(request, order.pk)

        self.assertEqual(response.status_code, 302)
        self.assertIn("https://checkout.stripe.com/test", response["Location"])
