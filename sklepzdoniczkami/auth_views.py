from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordResetForm
from django.template.response import TemplateResponse

from .catalog import public_categories


class AdminPasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        return (
            user
            for user in super().get_users(email)
            if user.is_superuser
        )


class AdminPasswordResetView(auth_views.PasswordResetView):
    def dispatch(self, request, *args, **kwargs):
        if not settings.ADMIN_PASSWORD_RESET_EMAIL_CONFIGURED:
            return TemplateResponse(
                request,
                "admin/password_reset_unavailable.html",
                status=503,
            )
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["email"].label = "Adres e-mail administratora"
        form.fields["email"].widget.attrs.update(
            {
                "autocomplete": "email",
                "autofocus": True,
                "placeholder": "adres@example.com",
            }
        )
        return form


class StorefrontPasswordResetContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = public_categories()
        return context


class StorefrontPasswordResetView(
    StorefrontPasswordResetContextMixin,
    auth_views.PasswordResetView,
):
    def dispatch(self, request, *args, **kwargs):
        if not settings.PASSWORD_RESET_EMAIL_CONFIGURED:
            return TemplateResponse(
                request,
                "sklepzdoniczkami/password_reset_unavailable.html",
                {"categories": public_categories()},
                status=503,
            )
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["email"].label = "Adres e-mail"
        form.fields["email"].widget.attrs.update(
            {
                "autocomplete": "email",
                "autofocus": True,
                "placeholder": "adres@example.com",
            }
        )
        return form


class StorefrontPasswordResetDoneView(
    StorefrontPasswordResetContextMixin,
    auth_views.PasswordResetDoneView,
):
    pass


class StorefrontPasswordResetConfirmView(
    StorefrontPasswordResetContextMixin,
    auth_views.PasswordResetConfirmView,
):
    pass


class StorefrontPasswordResetCompleteView(
    StorefrontPasswordResetContextMixin,
    auth_views.PasswordResetCompleteView,
):
    pass
