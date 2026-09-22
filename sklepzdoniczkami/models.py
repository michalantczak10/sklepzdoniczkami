from django.conf import settings
from django.db import models
from django.urls import reverse


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        db_table = "sklepzdoniczkami_category"
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("sklepzdoniczkami:category", kwargs={"slug": self.slug})


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "sklepzdoniczkami_product"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("sklepzdoniczkami:product", kwargs={"slug": self.slug})


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Oczekujące"),
        ("paid", "Opłacone"),
        ("processing", "W realizacji"),
        ("shipped", "Wysłane"),
        ("cancelled", "Anulowane"),
    ]
    PAYMENT_CHOICES = [
        ("transfer", "Przelew bankowy"),
        ("card", "Karta płatnicza"),
        ("cash_on_delivery", "Pobranie"),
    ]
    SHIPPING_CHOICES = [
        ("pickup", "Odbiór osobisty"),
        ("courier", "Kurier"),
        ("parcel", "Paczkomat"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    comments = models.TextField(blank=True)
    payment_method = models.CharField(max_length=30, choices=PAYMENT_CHOICES, default="transfer")
    shipping_method = models.CharField(max_length=30, choices=SHIPPING_CHOICES, default="courier")
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, default="")
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "sklepzdoniczkami_order"

    def __str__(self):
        return f"Zamówienie #{self.pk}"

    @property
    def total(self):
        return sum(item.total for item in self.items.all()) + self.shipping_cost


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "sklepzdoniczkami_orderitem"

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    @property
    def total(self):
        return self.unit_price * self.quantity