from decimal import Decimal

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, ListView

from .models import Category, Order, OrderItem, Product

stripe.api_key = settings.STRIPE_SECRET_KEY
ORDER_ACCESS_SALT = "sklepzdoniczkami.order-access"
ORDER_ACCESS_TOKEN_MAX_AGE = 30 * 24 * 60 * 60


def make_order_access_token(order):
    return signing.dumps(order.pk, salt=ORDER_ACCESS_SALT)


def get_order_from_access_token(order_token, queryset=None):
    try:
        order_id = signing.loads(
            order_token,
            salt=ORDER_ACCESS_SALT,
            max_age=ORDER_ACCESS_TOKEN_MAX_AGE,
        )
    except signing.BadSignature as exc:
        raise Http404 from exc

    if not isinstance(order_id, int):
        raise Http404
    if queryset is None:
        queryset = Order.objects.all()
    return get_object_or_404(queryset, pk=order_id)


def get_cart(request):
    cart = request.session.get("cart", {})
    return cart


def save_cart(request, cart):
    request.session["cart"] = cart
    request.session.modified = True


def cart_items(request):
    cart = get_cart(request)
    product_ids = list(cart.keys())
    products = Product.objects.filter(id__in=product_ids, is_active=True).select_related("category")
    items = []
    total = Decimal("0")
    for product in products:
        qty = cart.get(str(product.id), 0)
        if qty <= 0:
            continue
        line_total = product.price * qty
        total += line_total
        items.append({
            "product": product,
            "quantity": qty,
            "line_total": line_total,
        })
    return items, total


class ProductListView(ListView):
    model = Product
    template_name = "sklepzdoniczkami/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True).select_related("category")
        query = self.request.GET.get("q")
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(description__icontains=query) | Q(category__name__icontains=query)
            )
        category_slug = self.kwargs.get("slug")
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        return queryset.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_category"] = Category.objects.filter(slug=self.kwargs.get("slug")).first()
        context["categories"] = Category.objects.filter(products__is_active=True).distinct().order_by("name")
        context["search_query"] = self.request.GET.get("q", "")
        return context


class ProductDetailView(DetailView):
    model = Product
    template_name = "sklepzdoniczkami/product_detail.html"
    context_object_name = "product"

    def get_queryset(self):
        return Product.objects.filter(is_active=True).select_related("category")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["related_products"] = (
            Product.objects.filter(category=self.object.category, is_active=True)
            .exclude(pk=self.object.pk)
            .order_by("name")[:4]
        )
        context["categories"] = Category.objects.filter(products__is_active=True).distinct().order_by("name")
        return context


def cart_view(request):
    items, total = cart_items(request)
    context = {
        "items": items,
        "total": total,
        "categories": Category.objects.filter(products__is_active=True).distinct().order_by("name"),
    }
    return render(request, "sklepzdoniczkami/cart.html", context)


def add_to_cart(request, product_id):
    if request.method != "POST":
        return redirect("sklepzdoniczkami:products")

    product = Product.objects.filter(id=product_id, is_active=True).first()
    if not product:
        messages.error(request, "Produkt nie istnieje lub jest niedostępny.")
        return redirect("sklepzdoniczkami:products")

    cart = get_cart(request)
    cart[str(product.id)] = cart.get(str(product.id), 0) + 1
    if cart[str(product.id)] > product.stock:
        cart[str(product.id)] = product.stock
        messages.warning(request, "Maksymalna dostępna ilość produktu została dodana do koszyka.")
    save_cart(request, cart)
    messages.success(request, f"Dodano {product.name} do koszyka.")
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect("sklepzdoniczkami:products")


def remove_from_cart(request, product_id):
    cart = get_cart(request)
    cart.pop(str(product_id), None)
    save_cart(request, cart)
    messages.info(request, "Produkt usunięty z koszyka.")
    return redirect("sklepzdoniczkami:cart")


def checkout_view(request):
    items, total = cart_items(request)
    if not items:
        messages.warning(request, "Koszyk jest pusty.")
        return redirect("sklepzdoniczkami:cart")

    shipping_costs = {
        "pickup": Decimal("0.00"),
        "courier": Decimal("19.99"),
        "parcel": Decimal("14.99"),
    }

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        address = request.POST.get("address", "").strip()
        city = request.POST.get("city", "").strip()
        postal_code = request.POST.get("postal_code", "").strip()
        comments = request.POST.get("comments", "").strip()
        payment_method = request.POST.get("payment_method", "transfer")
        shipping_method = request.POST.get("shipping_method", "courier")
        shipping_cost = shipping_costs.get(shipping_method, Decimal("0.00"))

        if not all([first_name, last_name, email, address, city, postal_code]):
            messages.error(request, "Wypełnij wszystkie wymagane pola.")
        else:
            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                address=address,
                city=city,
                postal_code=postal_code,
                comments=comments,
                payment_method=payment_method,
                shipping_method=shipping_method,
                shipping_cost=shipping_cost,
                is_paid=False,
                status="pending",
            )
            for item in items:
                OrderItem.objects.create(
                    order=order,
                    product=item["product"],
                    quantity=item["quantity"],
                    unit_price=item["product"].price,
                )

            order_token = make_order_access_token(order)
            if payment_method == "card":
                # Stripe session is created after the order exists.
                return redirect(
                    "sklepzdoniczkami:stripe_checkout",
                    order_token=order_token,
                )

            request.session["cart"] = {}
            request.session.modified = True
            return redirect(
                "sklepzdoniczkami:checkout_success",
                order_token=order_token,
            )

    context = {
        "items": items,
        "total": total,
        "shipping_costs": shipping_costs,
        "categories": Category.objects.filter(products__is_active=True).distinct().order_by("name"),
    }
    return render(request, "sklepzdoniczkami/checkout.html", context)


def stripe_checkout(request, order_token):
    order = get_order_from_access_token(order_token)
    if not settings.STRIPE_SECRET_KEY:
        messages.error(request, "Stripe nie jest skonfigurowany. Ustaw STRIPE_SECRET_KEY w środowisku.")
        return redirect("sklepzdoniczkami:checkout")
    if order.payment_method != "card" or order.is_paid or order.status != "pending":
        messages.error(request, "To zamówienie nie może rozpocząć płatności kartą.")
        return redirect("sklepzdoniczkami:checkout")

    line_items = []
    for item in order.items.all():
        line_items.append({
            "price_data": {
                "currency": "pln",
                "product_data": {"name": item.product.name},
                "unit_amount": int(item.unit_price * 100),
            },
            "quantity": item.quantity,
        })
    if order.shipping_cost:
        line_items.append({
            "price_data": {
                "currency": "pln",
                "product_data": {"name": f"Dostawa ({order.get_shipping_method_display()})"},
                "unit_amount": int(order.shipping_cost * 100),
            },
            "quantity": 1,
        })

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=line_items,
        mode="payment",
        success_url=request.build_absolute_uri(
            reverse(
                "sklepzdoniczkami:payment_success",
                kwargs={"order_token": order_token},
            )
        ) + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=request.build_absolute_uri(
            reverse(
                "sklepzdoniczkami:payment_cancel",
                kwargs={"order_token": order_token},
            )
        ),
        customer_email=order.email,
        metadata={"order_id": str(order.id)},
        idempotency_key=f"checkout-order-{order.pk}",
    )
    order.stripe_checkout_session_id = session.id
    order.save(update_fields=["stripe_checkout_session_id"])
    return redirect(session.url, permanent=False)


def payment_success(request, order_token):
    order = get_order_from_access_token(order_token)
    session_id = request.GET.get("session_id")

    # Never trust the redirect alone: verify the checkout session with Stripe
    # before marking the order as paid. The webhook is the source of truth,
    # but this lets us reflect the paid state immediately for the user too.
    if not order.is_paid and session_id and settings.STRIPE_SECRET_KEY:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.error.StripeError:
            session = None

        if (
            session
            and session.id == order.stripe_checkout_session_id
            and getattr(session.metadata, "order_id", None) == str(order.id)
            and session.payment_status == "paid"
        ):
            with transaction.atomic():
                order = get_order_from_access_token(
                    order_token,
                    Order.objects.select_for_update(),
                )
                if not order.is_paid:
                    order.is_paid = True
                    order.status = "paid"
                    order.paid_at = timezone.now()
                    order.stripe_payment_intent_id = (
                        session.payment_intent or order.stripe_payment_intent_id
                    )
                    order.save(
                        update_fields=[
                            "is_paid",
                            "status",
                            "paid_at",
                            "stripe_payment_intent_id",
                        ]
                    )
                    request.session["cart"] = {}
                    request.session.modified = True

    order.refresh_from_db()

    if order.is_paid:
        messages.success(request, "Płatność została przyjęta. Zamówienie jest opłacone.")
    else:
        messages.info(request, "Oczekujemy na potwierdzenie płatności. Sprawdź status zamówienia za chwilę.")
    return redirect(
        "sklepzdoniczkami:checkout_success",
        order_token=order_token,
    )


def payment_cancel(request, order_token):
    with transaction.atomic():
        order = get_order_from_access_token(
            order_token,
            Order.objects.select_for_update(),
        )
        if not order.is_paid and order.status == "pending":
            order.status = "cancelled"
            order.save(update_fields=["status"])
    messages.warning(request, "Płatność została anulowana. Możesz spróbować ponownie.")
    return redirect("sklepzdoniczkami:checkout")


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    if not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = getattr(getattr(session, "metadata", None), "order_id", None)
        if order_id:
            with transaction.atomic():
                order = Order.objects.select_for_update().filter(pk=order_id).first()
                if order and not order.is_paid:
                    order.is_paid = True
                    order.status = "paid"
                    order.paid_at = timezone.now()
                    order.stripe_payment_intent_id = session.payment_intent or ""
                    order.save(
                        update_fields=[
                            "is_paid",
                            "status",
                            "paid_at",
                            "stripe_payment_intent_id",
                        ]
                    )

    return HttpResponse(status=200)


def checkout_success(request, order_token):
    order = get_order_from_access_token(order_token)
    context = {
        "order": order,
        "categories": Category.objects.filter(products__is_active=True).distinct().order_by("name"),
    }
    return render(request, "sklepzdoniczkami/checkout_success.html", context)


def login_view(request):
    if request.user.is_authenticated:
        return redirect("sklepzdoniczkami:profile")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        messages.success(request, "Zalogowano pomyślnie.")
        return redirect("sklepzdoniczkami:profile")

    context = {
        "form": form,
        "categories": Category.objects.filter(products__is_active=True).distinct().order_by("name"),
    }
    return render(request, "sklepzdoniczkami/login.html", context)


def register_view(request):
    if request.user.is_authenticated:
        return redirect("sklepzdoniczkami:profile")

    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Konto zostało utworzone.")
        return redirect("sklepzdoniczkami:profile")

    context = {
        "form": form,
        "categories": Category.objects.filter(products__is_active=True).distinct().order_by("name"),
    }
    return render(request, "sklepzdoniczkami/register.html", context)


@login_required
def profile_view(request):
    orders = request.user.orders.order_by("-created_at")
    context = {
        "orders": orders,
        "categories": Category.objects.filter(products__is_active=True).distinct().order_by("name"),
    }
    return render(request, "sklepzdoniczkami/profile.html", context)


class CategoryListView(ProductListView):
    def get_queryset(self):
        return super().get_queryset()
