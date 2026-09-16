from django.contrib import admin

from .models import AccountGroup, ChartOfAccount, Party


@admin.register(AccountGroup)
class AccountGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent']


@admin.register(ChartOfAccount)
class ChartOfAccountAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'account_type', 'group', 'is_active']
    list_filter = ['account_type']
    search_fields = ['code', 'name']


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ['name', 'party_type', 'credit_limit', 'is_active']
    list_filter = ['party_type']
    search_fields = ['name']
