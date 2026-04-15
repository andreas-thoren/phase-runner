"""Django admin registrations for all workout and periodization models."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm

from .models import User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = CustomUserCreationForm
    add_fieldsets = (
        (
            None,
            {
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
    )
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Upload Tracking", {"fields": ("weekly_upload_count", "weekly_upload_reset")}),
    )
