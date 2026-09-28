from rest_framework import serializers

from .models import AccountGroup, ChartOfAccount, JournalEntry, JournalLine, Party, Voucher, VoucherLine


class AccountGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountGroup
        fields = ['id', 'name', 'parent']


class ChartOfAccountSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source='group.name', read_only=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = ChartOfAccount
        fields = ['id', 'code', 'name', 'account_type', 'group', 'group_name', 'is_active', 'balance']


class PartySerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Party
        fields = [
            'id', 'name', 'party_type', 'contact_phone', 'address',
            'credit_limit', 'is_active', 'balance', 'created_at',
        ]


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    party_name = serializers.CharField(source='party.name', read_only=True)

    class Meta:
        model = JournalLine
        fields = ['id', 'account', 'account_code', 'account_name', 'party', 'party_name', 'debit', 'credit']


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)
    total_debit = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_credit = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            'id', 'date', 'narration', 'source', 'reference',
            'created_by', 'created_at', 'lines', 'total_debit', 'total_credit',
        ]


class VoucherLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    party_name = serializers.CharField(source='party.name', read_only=True)

    class Meta:
        model = VoucherLine
        fields = ['id', 'account', 'account_code', 'party', 'party_name', 'debit', 'credit']


class VoucherSerializer(serializers.ModelSerializer):
    lines = VoucherLineSerializer(many=True, required=False)
    party_name = serializers.CharField(source='party.name', read_only=True)
    debit_account_code = serializers.CharField(source='debit_account.code', read_only=True)
    journal_entry_id = serializers.IntegerField(source='journal_entry.id', read_only=True)

    class Meta:
        model = Voucher
        fields = [
            'id', 'voucher_number', 'voucher_type', 'date', 'narration',
            'party', 'party_name', 'payment_mode', 'amount',
            'debit_account', 'debit_account_code', 'status',
            'journal_entry_id', 'created_by', 'created_at', 'lines',
        ]
        read_only_fields = ['status', 'created_by']
        extra_kwargs = {'voucher_number': {'required': False}}

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        voucher = Voucher.objects.create(**validated_data)
        for line in lines_data:
            VoucherLine.objects.create(voucher=voucher, **line)
        return voucher

    def update(self, instance, validated_data):
        if instance.status != Voucher.STATUS_DRAFT:
            raise serializers.ValidationError('A posted voucher cannot be edited.')
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for line in lines_data:
                VoucherLine.objects.create(voucher=instance, **line)
        return instance
