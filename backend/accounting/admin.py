from django.contrib import admin

from .models import (
    AccountGroup, ChartOfAccount, JournalEntry, JournalLine, Party,
    PartyBalance, Voucher, VoucherLine,
)


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


@admin.register(PartyBalance)
class PartyBalanceAdmin(admin.ModelAdmin):
    list_display = ['party', 'balance', 'updated_at']


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ['id', 'date', 'source', 'reference', 'narration']
    list_filter = ['source']
    search_fields = ['reference', 'narration']
    inlines = [JournalLineInline]


class VoucherLineInline(admin.TabularInline):
    model = VoucherLine
    extra = 0


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ['voucher_number', 'voucher_type', 'date', 'party', 'amount', 'status']
    list_filter = ['voucher_type', 'status']
    search_fields = ['voucher_number']
    inlines = [VoucherLineInline]
