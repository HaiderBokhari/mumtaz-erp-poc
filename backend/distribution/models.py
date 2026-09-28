from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from accounting.models import ChartOfAccount, JournalEntry, Party
from warehouses.models import StockLedgerEntry


class Shop(models.Model):
    """Shop/retailer/wholesaler lifecycle management (requirement doc, Distribution #2)."""

    STATUS_ACTIVE = 'ACTIVE'
    STATUS_CLOSED = 'CLOSED'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_CLOSED, 'Closed'),
    ]

    name = models.CharField(max_length=150)
    channel = models.ForeignKey('catalog.Channel', on_delete=models.PROTECT, related_name='shops')
    address = models.CharField(max_length=255, blank=True)
    locality = models.CharField(max_length=100, blank=True)
    contact_name = models.CharField(max_length=100, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    credit_limit = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text='Questionnaire #9: mostly zero for retailers; set for wholesalers and for Eid/motorway exceptions.',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    closed_on = models.DateField(null=True, blank=True)
    party = models.OneToOneField(
        'accounting.Party', null=True, blank=True, on_delete=models.SET_NULL, related_name='shop',
        help_text='Accounting party this shop posts its receivable ledger against (Accounts #5).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_or_create_party(self):
        """Lazily create/link the accounting Party this shop's ledger entries post against."""
        if self.party_id:
            return self.party
        party_type = Party.WHOLESALER if self.channel.channel_type in ('WS', 'VWS', 'MANDI') else Party.RETAILER
        party = Party.objects.create(
            name=self.name, party_type=party_type,
            contact_phone=self.contact_phone, address=self.address, credit_limit=self.credit_limit,
        )
        self.party = party
        self.save(update_fields=['party'])
        return party

    @property
    def outstanding_balance(self):
        """
        Real party-ledger balance once posted (Accounts #5). Falls back to
        the old invoiced-minus-received estimate for a shop that hasn't
        posted anything yet (e.g. freshly created, no party linked).
        """
        if self.party_id:
            return self.party.balance
        invoiced = self.sales_orders.filter(status=SalesOrder.STATUS_CONFIRMED).aggregate(
            total=models.Sum(models.F('lines__quantity') * models.F('lines__unit_price'))
        )['total'] or Decimal('0')
        received = self.payment_receipts.aggregate(total=models.Sum('amount'))['total'] or Decimal('0')
        return invoiced - received


class SalesOrder(models.Model):
    """
    Sales order (requirement doc, Distribution #3): items sold, quantity,
    DR id/name, timestamp, channel, retailer details, PTC reference number.
    """

    STATUS_DRAFT = 'DRAFT'
    STATUS_CONFIRMED = 'CONFIRMED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_CONFIRMED, 'Confirmed (stock dispatched)'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    SOURCE_MANUAL = 'MANUAL'
    SOURCE_BIZOM_UPLOAD = 'BIZOM_UPLOAD'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Entered manually'),
        (SOURCE_BIZOM_UPLOAD, 'Uploaded from PTC / BIZOM sales file'),
    ]

    so_number = models.CharField(max_length=30, unique=True)
    ptc_reference_number = models.CharField(max_length=50, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, related_name='sales_orders')
    channel = models.ForeignKey('catalog.Channel', on_delete=models.PROTECT, related_name='sales_orders')
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='sales_orders')
    dr = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='sales_orders',
        help_text='The Distribution Representative who made the sale.',
    )
    order_date = models.DateField(default=timezone.localdate)
    timestamp = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return self.so_number

    @property
    def total_value(self):
        return sum((line.quantity * line.unit_price for line in self.lines.all()), Decimal('0'))

    @transaction.atomic
    def confirm(self, user=None):
        """Dispatch stock out of the source warehouse for every line, and post the accounting entry."""
        if self.status != self.STATUS_DRAFT:
            raise ValueError('Only a draft sales order can be confirmed.')
        revenue_total = Decimal('0')
        cost_total = Decimal('0')
        for line in self.lines.select_related('sku'):
            StockLedgerEntry.objects.create(
                warehouse=self.warehouse, sku=line.sku,
                entry_type=StockLedgerEntry.SALE_OUT,
                quantity_change=-line.quantity,
                reference=self.so_number, created_by=user,
            )
            revenue_total += line.quantity * line.unit_price
            cost_total += line.quantity * line.sku.current_cost_price
        self.status = self.STATUS_CONFIRMED
        self.save(update_fields=['status'])

        if revenue_total > 0:
            party = self.shop.get_or_create_party()
            lines = [
                {'account': ChartOfAccount.ACCOUNTS_RECEIVABLE, 'debit': revenue_total, 'party': party},
                {'account': ChartOfAccount.SALES_REVENUE, 'credit': revenue_total},
            ]
            if cost_total > 0:
                lines += [
                    {'account': ChartOfAccount.COST_OF_GOODS_SOLD, 'debit': cost_total},
                    {'account': ChartOfAccount.INVENTORY, 'credit': cost_total},
                ]
            JournalEntry.create_posted(
                source=JournalEntry.SOURCE_SALE, lines=lines, date=self.order_date,
                narration=f'Sale to {self.shop.name}', reference=self.so_number, created_by=user,
            )


class SalesOrderLine(models.Model):
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='lines')
    sku = models.ForeignKey('catalog.SKU', on_delete=models.PROTECT, related_name='sales_order_lines')
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f'{self.sales_order.so_number}: {self.sku} x {self.quantity}'

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class SalesReturn(models.Model):
    """Add, change, view, delete a sales return (requirement doc, Distribution #5)."""

    sales_order = models.ForeignKey(
        SalesOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name='returns'
    )
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, related_name='sales_returns')
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='sales_returns')
    sku = models.ForeignKey('catalog.SKU', on_delete=models.PROTECT, related_name='sales_returns')
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ledger_entry = models.OneToOneField(
        StockLedgerEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name='sales_return'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Return: {self.sku} x {self.quantity} from {self.shop}'

    def _resolve_unit_price(self):
        """Best-effort sale price for reversing revenue: the original SO line, else the current channel price, else cost."""
        if self.sales_order:
            line = self.sales_order.lines.filter(sku=self.sku).first()
            if line:
                return line.unit_price
        from catalog.models import ChannelPrice

        price = ChannelPrice.current_price(self.shop.channel_id, self.sku_id)
        return price if price is not None else self.sku.current_cost_price

    @transaction.atomic
    def apply(self, user=None):
        entry = StockLedgerEntry.objects.create(
            warehouse=self.warehouse, sku=self.sku,
            entry_type=StockLedgerEntry.SALE_RETURN_IN,
            quantity_change=self.quantity,
            reference=self.sales_order.so_number if self.sales_order else '',
            created_by=user,
        )
        self.ledger_entry = entry
        self.created_by = user
        self.save(update_fields=['ledger_entry', 'created_by'])

        unit_price = self._resolve_unit_price()
        revenue_reversal = self.quantity * unit_price
        cost_reversal = self.quantity * self.sku.current_cost_price
        if revenue_reversal > 0:
            party = self.shop.get_or_create_party()
            lines = [
                {'account': ChartOfAccount.SALES_REVENUE, 'debit': revenue_reversal},
                {'account': ChartOfAccount.ACCOUNTS_RECEIVABLE, 'credit': revenue_reversal, 'party': party},
            ]
            if cost_reversal > 0:
                lines += [
                    {'account': ChartOfAccount.INVENTORY, 'debit': cost_reversal},
                    {'account': ChartOfAccount.COST_OF_GOODS_SOLD, 'credit': cost_reversal},
                ]
            JournalEntry.create_posted(
                source=JournalEntry.SOURCE_SALE_RETURN, lines=lines,
                narration=f'Sale return from {self.shop.name}',
                reference=self.sales_order.so_number if self.sales_order else '', created_by=user,
            )


class PaymentReceipt(models.Model):
    """
    Payment receipts / collections (requirement doc, Distribution #6).
    Methods reflect questionnaire answer #22 ("Cash, Bank transfer, Bank
    onlines") plus post-dated cheques received from wholesalers (#8).
    """

    METHOD_CASH = 'CASH'
    METHOD_BANK_TRANSFER = 'BANK_TRANSFER'
    METHOD_BANK_ONLINE = 'BANK_ONLINE'
    METHOD_CHEQUE = 'CHEQUE'
    METHOD_CHOICES = [
        (METHOD_CASH, 'Cash'),
        (METHOD_BANK_TRANSFER, 'Bank transfer'),
        (METHOD_BANK_ONLINE, 'Bank online'),
        (METHOD_CHEQUE, 'Cheque (possibly post-dated)'),
    ]

    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, related_name='payment_receipts')
    sales_order = models.ForeignKey(
        SalesOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name='payment_receipts'
    )
    ptc_reference_number = models.CharField(max_length=50, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=METHOD_CASH)
    cheque_number = models.CharField(max_length=50, blank=True)
    cheque_date = models.DateField(null=True, blank=True, help_text='For post-dated cheques.')
    received_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        return f'{self.shop}: {self.amount} ({self.get_method_display()})'

    @transaction.atomic
    def post_to_ledger(self, user=None):
        """Dr Cash/Bank, Cr the shop's receivable (requirement doc, Accounts #3: embedded, not a manual voucher)."""
        cash_or_bank_code = ChartOfAccount.BANK if self.method in (self.METHOD_BANK_TRANSFER, self.METHOD_BANK_ONLINE) else ChartOfAccount.CASH
        party = self.shop.get_or_create_party()
        JournalEntry.create_posted(
            source=JournalEntry.SOURCE_PAYMENT_RECEIPT,
            lines=[
                {'account': cash_or_bank_code, 'debit': self.amount},
                {'account': ChartOfAccount.ACCOUNTS_RECEIVABLE, 'credit': self.amount, 'party': party},
            ],
            date=self.received_at.date() if hasattr(self.received_at, 'date') else self.received_at,
            narration=f'Collection from {self.shop.name}',
            reference=self.ptc_reference_number, created_by=user,
        )


class SalesTarget(models.Model):
    """
    Monthly, DR-wise and channel-wise volume targets (requirement doc,
    "How PTC Distributor Works": Primaries/Secondaries targets by channel;
    questionnaire #24: "Sales target and Target achievement DR wise is
    mandatory"). Volume is tracked in M's (1 M = 1000 sticks), same unit
    PTC itself uses.
    """

    dr = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sales_targets')
    channel = models.ForeignKey('catalog.Channel', on_delete=models.CASCADE, related_name='sales_targets')
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    target_volume_m = models.DecimalField(max_digits=12, decimal_places=3, help_text="Target volume in M's (1,000 sticks).")

    class Meta:
        unique_together = ['dr', 'channel', 'year', 'month']
        ordering = ['-year', '-month']

    def __str__(self):
        return f'{self.dr} / {self.channel} {self.month}-{self.year}: {self.target_volume_m}M'
