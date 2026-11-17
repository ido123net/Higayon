from django.conf import settings
from django.contrib import admin, messages

from .auth import make_configured_owner_staff, owner
from .models import AuthorizedEmail


class OwnerAdminSite(admin.AdminSite):
    site_header = "ניהול היגיון"
    site_title = "ניהול היגיון"
    index_title = "ניהול גישה"

    def has_permission(self, request):
        if owner(request.user):
            make_configured_owner_staff(request.user)
            return request.user.is_active and request.user.is_staff and request.user.is_superuser
        return False


owner_admin_site = OwnerAdminSite(name="admin")


@admin.register(AuthorizedEmail, site=owner_admin_site)
class AuthorizedEmailAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at", "added_by")
    search_fields = ("email",)
    ordering = ("email",)
    fields = ("email",)
    actions = ("remove_selected",)

    @admin.action(description="הסרת המשתמשים שנבחרו")
    def remove_selected(self, request, queryset):
        protected = queryset.filter(email__iexact=settings.OWNER_EMAIL).count()
        removable = queryset.exclude(email__iexact=settings.OWNER_EMAIL)
        count = removable.count()
        removable.delete()
        if count:
            self.message_user(request, f"הוסרו {count} משתמשים מורשים.", messages.SUCCESS)
        if protected:
            self.message_user(request, "לא ניתן להסיר את חשבון הבעלים.", messages.WARNING)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.added_by = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.email.lower() == settings.OWNER_EMAIL:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        queryset.exclude(email__iexact=settings.OWNER_EMAIL).delete()
