from django.contrib.auth import views as auth_views
from django.urls import path

from .views import (
    add_to_cart,
    cart_view,
    checkout_success,
    checkout_view,
    login_view,
    payment_cancel,
    payment_success,
    ProductDetailView,
    ProductListView,
    profile_view,
    register_view,
    remove_from_cart,
    stripe_checkout,
    stripe_webhook,
)

app_name = "sklepzdoniczkami"

urlpatterns = [
    path("", ProductListView.as_view(), name="home"),
    path("products/", ProductListView.as_view(), name="products"),
    path("category/<slug:slug>/", ProductListView.as_view(), name="category"),
    path("product/<slug:slug>/", ProductDetailView.as_view(), name="product"),
    path("cart/", cart_view, name="cart"),
    path("cart/add/<int:product_id>/", add_to_cart, name="add_to_cart"),
    path("cart/remove/<int:product_id>/", remove_from_cart, name="remove_from_cart"),
    path("checkout/", checkout_view, name="checkout"),
    path("checkout/stripe/<str:order_token>/", stripe_checkout, name="stripe_checkout"),
    path("checkout/success/<str:order_token>/", checkout_success, name="checkout_success"),
    path("payment/success/<str:order_token>/", payment_success, name="payment_success"),
    path("payment/cancel/<str:order_token>/", payment_cancel, name="payment_cancel"),
    path("stripe/webhook/", stripe_webhook, name="stripe_webhook"),
    path("login/", login_view, name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="sklepzdoniczkami:home"), name="logout"),
    path("register/", register_view, name="register"),
    path("profile/", profile_view, name="profile"),
]
