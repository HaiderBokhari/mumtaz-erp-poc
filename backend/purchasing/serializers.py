from rest_framework import serializers

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseReturn


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source='sku.code', read_only=True)
    sku_name = serializers.CharField(source='sku.name', read_only=True)
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = [
            'id', 'sku', 'sku_code', 'sku_name', 'quantity', 'unit_cost',
            'batch_number', 'expiry_date', 'line_total',
        ]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    total_value = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'ptc_reference_number', 'warehouse', 'warehouse_name',
            'supplier', 'supplier_name', 'status', 'order_date', 'notes',
            'created_by', 'approved_by', 'approved_at', 'received_at',
            'total_value', 'created_at', 'updated_at', 'lines',
        ]
        read_only_fields = ['status', 'created_by', 'approved_by', 'approved_at', 'received_at']
        extra_kwargs = {
            # Mumtaz & Co has one real supplier (PTC); the view defaults this
            # to the PTC Party if the caller doesn't pass one, so the create
            # form doesn't need a supplier picker.
            'supplier': {'required': False},
            # The view auto-generates a PO-YYYY-NNNNN number when omitted.
            'po_number': {'required': False},
        }

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        po = PurchaseOrder.objects.create(**validated_data)
        for line in lines_data:
            PurchaseOrderLine.objects.create(purchase_order=po, **line)
        return po

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for line in lines_data:
                PurchaseOrderLine.objects.create(purchase_order=instance, **line)
        return instance


class PurchaseReturnSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source='sku.code', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = PurchaseReturn
        fields = [
            'id', 'return_number', 'purchase_order', 'warehouse', 'warehouse_name',
            'sku', 'sku_code', 'quantity', 'reason', 'ptc_claim_reference',
            'status', 'created_by', 'created_at',
        ]
        read_only_fields = ['status', 'created_by']
