from rest_framework import serializers

from .models import (
    SafetyStockLevel, StockAdjustment, StockLedgerEntry, StockLevel,
    StockTransfer, StockTransferLine, Warehouse,
)


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            'id', 'name', 'code', 'location', 'is_head_office',
            'requires_po_approval', 'is_active', 'created_at',
        ]


class StockLevelSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source='sku.code', read_only=True)
    sku_name = serializers.CharField(source='sku.name', read_only=True)
    brand_name = serializers.CharField(source='sku.brand.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = StockLevel
        fields = [
            'id', 'warehouse', 'warehouse_name', 'sku', 'sku_code', 'sku_name',
            'brand_name', 'quantity', 'updated_at',
        ]


class StockLedgerEntrySerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source='sku.code', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = StockLedgerEntry
        fields = [
            'id', 'warehouse', 'warehouse_name', 'sku', 'sku_code', 'entry_type',
            'quantity_change', 'reference', 'notes', 'created_by', 'created_by_name',
            'created_at',
        ]
        read_only_fields = ['created_by']


class StockTransferLineSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source='sku.code', read_only=True)

    class Meta:
        model = StockTransferLine
        fields = ['id', 'sku', 'sku_code', 'quantity']


class StockTransferSerializer(serializers.ModelSerializer):
    lines = StockTransferLineSerializer(many=True)
    from_warehouse_name = serializers.CharField(source='from_warehouse.name', read_only=True)
    to_warehouse_name = serializers.CharField(source='to_warehouse.name', read_only=True)

    class Meta:
        model = StockTransfer
        fields = [
            'id', 'transfer_number', 'from_warehouse', 'from_warehouse_name',
            'to_warehouse', 'to_warehouse_name', 'status', 'dispatched_at',
            'received_at', 'created_by', 'created_at', 'lines',
        ]
        read_only_fields = ['status', 'dispatched_at', 'received_at', 'created_by']

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        transfer = StockTransfer.objects.create(**validated_data)
        for line in lines_data:
            StockTransferLine.objects.create(transfer=transfer, **line)
        return transfer


class SafetyStockLevelSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source='sku.code', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    current_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)
    is_below_minimum = serializers.BooleanField(read_only=True)

    class Meta:
        model = SafetyStockLevel
        fields = [
            'id', 'warehouse', 'warehouse_name', 'sku', 'sku_code',
            'minimum_quantity', 'current_quantity', 'is_below_minimum',
        ]


class StockAdjustmentSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source='sku.code', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = StockAdjustment
        fields = [
            'id', 'warehouse', 'warehouse_name', 'sku', 'sku_code', 'reason',
            'quantity', 'is_increase', 'ptc_claim_reference', 'notes',
            'created_by', 'created_at',
        ]
        read_only_fields = ['created_by']
