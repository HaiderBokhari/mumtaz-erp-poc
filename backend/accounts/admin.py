from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'dr_code', 'warehouse', 'supervisor', 'is_blocked']
    list_filter = ['warehouse', 'is_blocked']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'dr_code']
    autocomplete_fields = ['user', 'warehouse', 'supervisor']
