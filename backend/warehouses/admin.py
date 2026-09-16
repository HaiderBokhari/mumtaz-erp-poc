from django.contrib import admin

from .models import (
    SafetyStockLevel, StockAdjustment, StockLedgerEntry, StockLevel,
    StockTransfer, StockTransferLine, Warehouse,
)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_head_office', 'requires_po_approval', 'is_active']
    search_fields = ['name', 'code']


@admin.register(StockLevel)
class StockLevelAdmin(admin.ModelAdmin):
    list_display = ['warehouse', 'sku', 'quantity', 'updated_at']
    list_filter = ['warehouse']
    search_fields = ['sku__code', 'sku__name']


@admin.register(StockLedgerEntry)
class StockLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'warehouse', 'sku', 'entry_type', 'quantity_change', 'reference']
    list_filter = ['entry_type', 'warehouse']
    search_fields = ['sku__code', 'reference']
    date_hierarchy = 'created_at'


class StockTransferLineInline(admin.TabularInline):
    model = StockTransferLine
    extra = 1


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ['transfer_number', 'from_warehouse', 'to_warehouse', 'status', 'created_at']
    list_filter = ['status']
    inlines = [StockTransferLineInline]


@admin.register(SafetyStockLevel)
class SafetyStockLevelAdmin(admin.ModelAdmin):
    list_display = ['warehouse', 'sku', 'minimum_quantity']
    list_filter = ['warehouse']


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ['warehouse', 'sku', 'reason', 'quantity', 'is_increase', 'created_at']
    list_filter = ['reason', 'warehouse']
