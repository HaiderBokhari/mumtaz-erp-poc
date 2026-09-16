from django.contrib import admin

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseReturn


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['po_number', 'ptc_reference_number', 'warehouse', 'supplier', 'status', 'order_date']
    list_filter = ['status', 'warehouse']
    search_fields = ['po_number', 'ptc_reference_number']
    inlines = [PurchaseOrderLineInline]


@admin.register(PurchaseReturn)
class PurchaseReturnAdmin(admin.ModelAdmin):
    list_display = ['return_number', 'warehouse', 'sku', 'quantity', 'status', 'created_at']
    list_filter = ['status', 'warehouse']
