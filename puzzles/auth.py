from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.shortcuts import render

from .models import AuthorizedEmail


def google_configured():
    app = settings.SOCIALACCOUNT_PROVIDERS["google"]["APPS"][0]
    return bool(app.get("client_id") and app.get("secret"))


def allowed(email):
    normalized = email.strip().lower() if email else ""
    return bool(
        normalized
        and (
            normalized == settings.OWNER_EMAIL
            or AuthorizedEmail.objects.filter(email=normalized).exists()
        )
    )


def make_configured_owner_staff(user):
    if user.email and user.email.strip().lower() == settings.OWNER_EMAIL:
        user.is_staff = True
        user.is_superuser = True
        if getattr(user, "pk", None):
            user.save(update_fields=["is_staff", "is_superuser"])
    return user


def invited(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and allowed(user.email)
        and SocialAccount.objects.filter(user=user, provider="google").exists()  # ty: ignore[missing-attribute]  # Django adds the manager at runtime.
        and EmailAddress.objects.filter(user=user, email__iexact=user.email, verified=True).exists()
    )


def owner(user):
    return (
        invited(user) and bool(settings.OWNER_EMAIL) and user.email.lower() == settings.OWNER_EMAIL
    )


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False


class GoogleAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        verified = {e.email.lower() for e in sociallogin.email_addresses if e.verified}
        email = (sociallogin.user.email or "").lower()
        if sociallogin.account.provider != "google" or email not in verified or not allowed(email):
            raise ImmediateHttpResponse(
                render(
                    request,
                    "message.html",
                    {"message": "הכניסה מותרת רק לכתובת Google מאומתת ברשימת המוזמנים."},
                    status=403,
                )
            )
        make_configured_owner_staff(sociallogin.user)

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        return make_configured_owner_staff(user)

    def is_open_for_signup(self, request, sociallogin):
        return True
