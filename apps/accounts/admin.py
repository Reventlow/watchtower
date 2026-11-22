"""User admin: Django's, plus who has signed in with Microsoft yet."""

from allauth.socialaccount.models import SocialAccount
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import Exists, OuterRef
from django.utils.html import format_html

from .backends import is_break_glass

User = get_user_model()


class SSOLinkedFilter(admin.SimpleListFilter):
    """Filter users by whether they have signed in with Microsoft yet."""

    title = "Microsoft sign-in"
    parameter_name = "sso"

    def lookups(self, request, model_admin):
        return [("yes", "Linked"), ("no", "Not linked")]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(sso_linked=True)
        if self.value() == "no":
            return queryset.filter(sso_linked=False)
        return queryset


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Before switching SSO_ONLY on, every active user except the
    break-glass accounts should show "Linked": they have signed in with
    Microsoft once, so their account is tied to its Entra object id. A user
    is linked on that first sign-in by e-mail address, so set the address
    (their work address) here first."""

    list_display = (*DjangoUserAdmin.list_display, "sso_badge", "last_login")
    list_filter = (*DjangoUserAdmin.list_filter, SSOLinkedFilter)

    def get_queryset(self, request):
        linked = SocialAccount.objects.filter(user=OuterRef("pk"), provider="microsoft")
        return super().get_queryset(request).annotate(sso_linked=Exists(linked))

    @admin.display(description="SSO", ordering="sso_linked")
    def sso_badge(self, obj):
        if is_break_glass(obj):
            return format_html('<span title="{}">{}</span>', "May sign in with a password", "Break-glass")
        return "✓ Linked" if obj.sso_linked else "—"
