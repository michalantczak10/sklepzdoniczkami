from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError


class StorefrontPasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        matching_email_users = list(super().get_users(email))
        if matching_email_users:
            yield from matching_email_users
            return

        user_model = get_user_model()
        if user_model._default_manager.filter(email__iexact=email).exists():
            return

        for user in user_model._default_manager.filter(
            username__iexact=email,
            email="",
            is_active=True,
        ):
            if user.has_usable_password():
                user.email = email
                yield user


class StorefrontPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        email_field = user.get_email_field_name()
        user_email = getattr(user, email_field)
        if not user_email:
            setattr(user, email_field, user.get_username())
        try:
            return super()._make_hash_value(user, timestamp)
        finally:
            setattr(user, email_field, user_email)


class StorefrontSetPasswordForm(SetPasswordForm):
    def save(self, commit=True):
        if not self.user.email:
            self.user.email = self.user.get_username()
        return super().save(commit=commit)


class CustomerCreationForm(UserCreationForm):
    email = forms.EmailField(label="Adres e-mail")

    class Meta(UserCreationForm.Meta):
        fields = ("username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        user_model = self._meta.model
        if user_model.objects.filter(email__iexact=email).exists():
            raise ValidationError("Konto z tym adresem e-mail już istnieje.")
        return email
