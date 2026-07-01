from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Preferenze viaggio', {
            'fields': ('phone_number', 'default_budget', 'preferred_activities'),
        }),
    )
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff']
