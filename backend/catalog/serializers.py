from rest_framework import serializers

from .models import Brand, Channel, ChannelPrice, CostPriceHistory, SKU


class BrandSerializer(serializers.ModelSerializer):
    sku_count = serializers.IntegerField(source='skus.count', read_only=True)

    class Meta:
        model = Brand
        fields = ['id', 'name', 'code', 'status', 'sku_count', 'created_at', 'updated_at']


class CostPriceHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source='changed_by.username', read_only=True)

    class Meta:
        model = CostPriceHistory
        fields = ['id', 'sku', 'cost_price', 'changed_by', 'changed_by_name', 'note', 'effective_from']
        read_only_fields = ['changed_by']


class SKUSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source='brand.name', read_only=True)

    class Meta:
        model = SKU
        fields = [
            'id', 'code', 'name', 'brand', 'brand_name', 'variant', 'pack_size',
            'sticks_per_pack', 'barcode', 'current_cost_price', 'status',
            'created_at', 'updated_at',
        ]


class SKUDetailSerializer(SKUSerializer):
    cost_history = CostPriceHistorySerializer(many=True, read_only=True)

    class Meta(SKUSerializer.Meta):
        fields = SKUSerializer.Meta.fields + ['cost_history']


class ChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Channel
        fields = [
            'id', 'name', 'channel_type', 'filer_status', 'status',
            'opened_on', 'closed_on', 'created_at', 'updated_at',
        ]


class ChannelPriceSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source='sku.code', read_only=True)
    channel_name = serializers.CharField(source='channel.name', read_only=True)

    class Meta:
        model = ChannelPrice
        fields = [
            'id', 'channel', 'channel_name', 'sku', 'sku_code', 'price',
            'effective_from', 'changed_by', 'created_at',
        ]
        read_only_fields = ['changed_by']


class SKUPriceMatrixSerializer(serializers.Serializer):
    """One row per SKU with its current price on every active channel — powers the
    'View SKUs master with Channel Wise pricing' screen (requirement doc, Inventory #11)."""

    sku_id = serializers.IntegerField()
    sku_code = serializers.CharField()
    sku_name = serializers.CharField()
    brand_name = serializers.CharField()
    prices = serializers.DictField(child=serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True))
