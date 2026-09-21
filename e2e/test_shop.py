import re

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect

from shop.models import Category, Order, Product


@pytest.fixture
def product(db):
    category = Category.objects.create(name="Rosliny", slug="rosliny")
    product = Product.objects.create(
        category=category,
        name="Monstera testowa",
        slug="monstera-testowa",
        description="Produkt utworzony na potrzeby testu E2E.",
        price="49.99",
        stock=5,
        is_active=True,
    )
    Product.objects.create(
        category=category,
        name="Fikus testowy",
        slug="fikus-testowy",
        description="Produkt spoza wyszukiwania w teście E2E.",
        price="39.99",
        stock=5,
        is_active=True,
    )
    return product


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_guest_can_add_product_to_cart(live_server, page: Page, product):
    page.goto(live_server.url + reverse("shop:home"))

    expect(page.get_by_role("heading", name="Wszystkie produkty")).to_be_visible()
    expect(page.get_by_text(product.name)).to_be_visible()
    expect(page.get_by_text("Fikus testowy")).to_be_visible()

    page.get_by_placeholder("Szukaj produktu...").fill("Monstera")
    page.get_by_placeholder("Szukaj produktu...").press("Enter")
    expect(page.get_by_text(product.name)).to_be_visible()
    expect(page.get_by_text("Fikus testowy")).not_to_be_visible()

    product_card = page.locator("article.product-card").filter(has_text=product.name)
    product_card.get_by_role("button", name="Dodaj do koszyka").click()

    page.get_by_role("link", name=re.compile(r"Koszyk")).click()
    product_row = page.locator("tbody tr").filter(has_text=product.name)
    expect(product_row).to_be_visible()
    expect(product_row.locator("td").nth(1)).to_have_text("1")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_guest_can_submit_transfer_order(live_server, page: Page, product):
    page.goto(live_server.url + reverse("shop:home"))
    product_card = page.locator("article.product-card").filter(has_text=product.name)
    product_card.get_by_role("button", name="Dodaj do koszyka").click()
    page.get_by_role("link", name=re.compile(r"Koszyk")).click()
    page.get_by_role("link", name="Przejdź do zamówienia").click()

    page.locator('input[name="first_name"]').fill("Anna")
    page.locator('input[name="last_name"]').fill("Kowalska")
    page.locator('input[name="email"]').fill("anna-e2e@example.com")
    page.locator('input[name="phone"]').fill("123456789")
    page.locator('input[name="address"]').fill("ul. Testowa 1")
    page.locator('input[name="city"]').fill("Warszawa")
    page.locator('input[name="postal_code"]').fill("00-001")
    page.locator('select[name="shipping_method"]').select_option("courier")
    page.locator('select[name="payment_method"]').select_option("transfer")
    page.get_by_role("button", name="Złóż zamówienie").click()

    expect(page.get_by_role("heading", name="Potwierdzenie zamówienia")).to_be_visible()
    expect(page.get_by_text("Zamówienie nr")).to_be_visible()
    expect(page.get_by_text("Metoda płatności: Przelew bankowy")).to_be_visible()
    order = Order.objects.get(email="anna-e2e@example.com")
    assert order.payment_method == "transfer"
