from django.contrib import admin

from .models import PaymentReceipt, SalesOrder, SalesOrderLine, SalesReturn, SalesTarget, Shop


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ['name', 'channel', 'locality', 'credit_limit', 'status']
    list_filter = ['channel', 'status']
    search_fields = ['name', 'locality']


class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 1


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ['so_number', 'ptc_reference_number', 'shop', 'channel', 'dr', 'status', 'order_date']
    list_filter = ['status', 'channel', 'source']
    search_fields = ['so_number', 'ptc_reference_number']
    inlines = [SalesOrderLineInline]


@admin.register(SalesReturn)
class SalesReturnAdmin(admin.ModelAdmin):
    list_display = ['shop', 'sku', 'quantity', 'warehouse', 'created_at']
    list_filter = ['warehouse']


@admin.register(PaymentReceipt)
class PaymentReceiptAdmin(admin.ModelAdmin):
    list_display = ['shop', 'amount', 'method', 'received_at']
    list_filter = ['method']


@admin.register(SalesTarget)
class SalesTargetAdmin(admin.ModelAdmin):
    list_display = ['dr', 'channel', 'year', 'month', 'target_volume_m']
    list_filter = ['channel', 'year', 'month']
