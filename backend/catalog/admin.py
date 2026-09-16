from django.contrib import admin

from .models import Brand, Channel, ChannelPrice, CostPriceHistory, SKU


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'status']
    search_fields = ['name', 'code']
    list_filter = ['status']


class CostPriceHistoryInline(admin.TabularInline):
    model = CostPriceHistory
    extra = 0
    readonly_fields = ['effective_from']


@admin.register(SKU)
class SKUAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'brand', 'pack_size', 'sticks_per_pack', 'current_cost_price', 'status']
    list_filter = ['brand', 'status']
    search_fields = ['code', 'name', 'barcode']
    autocomplete_fields = ['brand']
    inlines = [CostPriceHistoryInline]


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ['name', 'channel_type', 'filer_status', 'status', 'opened_on']
    list_filter = ['channel_type', 'filer_status', 'status']
    search_fields = ['name']


@admin.register(ChannelPrice)
class ChannelPriceAdmin(admin.ModelAdmin):
    list_display = ['sku', 'channel', 'price', 'effective_from']
    list_filter = ['channel']
    autocomplete_fields = ['sku', 'channel']
