from rest_framework import serializers

from .models import PaymentReceipt, SalesOrder, SalesOrderLine, SalesReturn, SalesTarget, Shop


class ShopSerializer(serializers.ModelSerializer):
    channel_name = serializers.CharField(source='channel.name', read_only=True)
    outstanding_balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'channel', 'channel_name', 'address', 'locality',
            'contact_name', 'contact_phone', 'credit_limit', 'status',
            'closed_on', 'outstanding_balance', 'created_at', 'updated_at',
        ]


class SalesOrderLineSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source='sku.code', read_only=True)
    sku_name = serializers.CharField(source='sku.name', read_only=True)
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = SalesOrderLine
        fields = ['id', 'sku', 'sku_code', 'sku_name', 'quantity', 'unit_price', 'line_total']


class SalesOrderSerializer(serializers.ModelSerializer):
    lines = SalesOrderLineSerializer(many=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    channel_name = serializers.CharField(source='channel.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    dr_name = serializers.CharField(source='dr.get_full_name', read_only=True)
    total_value = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = SalesOrder
        fields = [
            'id', 'so_number', 'ptc_reference_number', 'shop', 'shop_name',
            'channel', 'channel_name', 'warehouse', 'warehouse_name', 'dr', 'dr_name',
            'order_date', 'timestamp', 'status', 'source', 'total_value',
            'created_by', 'created_at', 'lines',
        ]
        read_only_fields = ['status', 'source', 'created_by']
        extra_kwargs = {
            # The view auto-generates SO-YYYY-NNNNN when omitted, and defaults
            # `dr` to the logged-in user (most sales orders are entered by the
            # DR themselves, or by staff on a DR's behalf via the `dr` field).
            'so_number': {'required': False},
            'dr': {'required': False},
        }

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        so = SalesOrder.objects.create(**validated_data)
        for line in lines_data:
            SalesOrderLine.objects.create(sales_order=so, **line)
        return so

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for line in lines_data:
                SalesOrderLine.objects.create(sales_order=instance, **line)
        return instance


class SalesReturnSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source='sku.code', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)

    class Meta:
        model = SalesReturn
        fields = [
            'id', 'sales_order', 'shop', 'shop_name', 'warehouse', 'sku', 'sku_code',
            'quantity', 'reason', 'created_by', 'created_at',
        ]
        read_only_fields = ['created_by']


class PaymentReceiptSerializer(serializers.ModelSerializer):
    shop_name = serializers.CharField(source='shop.name', read_only=True)

    class Meta:
        model = PaymentReceipt
        fields = [
            'id', 'shop', 'shop_name', 'sales_order', 'ptc_reference_number',
            'amount', 'method', 'cheque_number', 'cheque_date', 'received_at', 'created_by',
        ]
        read_only_fields = ['created_by']


class SalesTargetSerializer(serializers.ModelSerializer):
    dr_name = serializers.CharField(source='dr.get_full_name', read_only=True)
    channel_name = serializers.CharField(source='channel.name', read_only=True)

    class Meta:
        model = SalesTarget
        fields = ['id', 'dr', 'dr_name', 'channel', 'channel_name', 'year', 'month', 'target_volume_m']


class SalesUploadResultSerializer(serializers.Serializer):
    orders_created = serializers.IntegerField()
    rows_processed = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.CharField())
