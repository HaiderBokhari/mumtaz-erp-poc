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
    # Outlet master fields as they come from BIZOM's Customer List export
    # (questionnaire: BIZOM is the sales data source). Blank for shops
    # entered by hand.
    bizom_outlet_id = models.CharField(max_length=20, blank=True, db_index=True)
    dr = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='outlets', help_text='DR whose beat this outlet is on.',
    )
    beat = models.CharField(max_length=255, blank=True)
    visit_days = models.CharField(max_length=100, blank=True)
    area_type = models.CharField(max_length=10, blank=True, help_text='URBAN / RURAL / MANDI, from BIZOM.')
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
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
        if self.bizom_outlet_id:
            # BIZOM outlets settle with their DR in cash on the day; any credit
            # sits on the DR's settlement (market credit), not on the outlet.
            return Decimal('0')
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
        for line in self.lines.select_related('sku'):
            StockLedgerEntry.objects.create(
                warehouse=self.warehouse, sku=line.sku,
                entry_type=StockLedgerEntry.SALE_OUT,
                quantity_change=-line.quantity,
                reference=self.so_number, created_by=user,
            )
        self.status = self.STATUS_CONFIRMED
        self.save(update_fields=['status'])
        self.post_accounting_entry(user=user)

    def post_accounting_entry(self, user=None):
        """
        Split out from confirm() so a management command can backfill this
        for any SO that was confirmed before the accounting module existed,
        without re-running confirm() (which would re-dispatch stock).
        """
        revenue_total = Decimal('0')
        cost_total = Decimal('0')
        for line in self.lines.select_related('sku'):
            revenue_total += line.quantity * line.unit_price
            cost_total += line.quantity * line.sku.current_cost_price

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


class ActualSale(models.Model):
    """
    The "actual" book: what DRs physically sold, per day, SKU and bucket,
    as kept in Mumtaz & Co's own daily "ACTUAL SALE" sheet. BIZOM sales
    orders (source=BIZOM_UPLOAD) are the *company* book and can differ
    because of adjustments: "Madam Banam" (invoiced in BIZOM, stock stays
    in the godown) and "Madam Wasooli" (sold physically, no BIZOM invoice).
    US-19: the owner wants actual sales, with the company version beside it.

    Physical stock follows this book, so each row is backed by a SALE_OUT
    ledger entry (reference ``ACT-<dr code>-<date>``).
    """

    BUCKET_RETAIL = 'RETAIL'
    BUCKET_SCATTERED = 'SCATTERED'
    BUCKET_CHOICES = [
        (BUCKET_RETAIL, 'Sold in retail'),
        (BUCKET_SCATTERED, 'Sold in scattered wholesale'),
    ]

    SOURCE_SHEET = 'SHEET'
    SOURCE_BIZOM_ASSUMED = 'BIZOM_ASSUMED'
    SOURCE_MANUAL = 'MANUAL'
    SOURCE_CHOICES = [
        (SOURCE_SHEET, "From the distributor's daily actual-sale sheet"),
        (SOURCE_BIZOM_ASSUMED, 'Not on the actual-sale sheet; BIZOM volume assumed actual (e.g. shop sale)'),
        (SOURCE_MANUAL, 'Entered manually'),
    ]

    date = models.DateField(db_index=True)
    dr = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='actual_sales')
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='actual_sales')
    sku = models.ForeignKey('catalog.SKU', on_delete=models.PROTECT, related_name='actual_sales')
    bucket = models.CharField(max_length=10, choices=BUCKET_CHOICES, default=BUCKET_RETAIL)
    quantity_m = models.DecimalField(max_digits=14, decimal_places=3, help_text="Volume in M's (1,000 sticks).")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, help_text='Price per M.')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', 'dr', 'sku']
        unique_together = ['date', 'dr', 'sku', 'bucket']

    def __str__(self):
        return f'{self.date} {self.dr} {self.sku.code} {self.quantity_m}M'

    @property
    def value(self):
        return self.quantity_m * self.unit_price


class DRIssuance(models.Model):
    """
    What the KPO issued to a DR in the morning and what came back in the
    evening, per sheet column, in M's — the distributor's ISSUANCE / RETURN
    rows (team request 23 Nov 2026: "Hamza puts brand-wise issuance and
    return and gets the sales and its amount"). Sale = issued - returned,
    and it is saved into the actual book as that DR's retail sale for the day
    (see distribution.actual_entry.save_issuance).
    """

    date = models.DateField(db_index=True)
    dr = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='issuances')
    column = models.CharField(max_length=10, help_text='Sheet column key, see actual_entry.SHEET_COLUMNS.')
    issued_m = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    returned_m = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['date', 'dr', 'column']
        ordering = ['-date', 'dr', 'column']

    def __str__(self):
        return f'{self.date} {self.dr} {self.column}: {self.issued_m} - {self.returned_m}'

    @property
    def sale_m(self):
        return self.issued_m - self.returned_m


class DRSettlement(models.Model):
    """
    A DR's end-of-day cash settlement, laid out exactly like Mumtaz & Co's
    paper slip: the KPO fills the top (sale, FBR, adjustments), the DR fills
    the bottom (cash by note, bank transfers, expense, market credit), and
    the difference is the DR's short/excess for the day.

    total_sale is the BIZOM (company) value. Banam is the part of it that
    was invoiced but not physically sold; Wasooli is money for stock sold
    without an invoice. So the DR should hand over
    total_sale - banam + wasooli - FBR.
    """

    NOTE_DENOMINATIONS = [5000, 1000, 500, 100, 50, 20, 10]

    date = models.DateField(db_index=True)
    dr = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='settlements')
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='settlements')

    # KPO portion
    total_sale = models.DecimalField(max_digits=14, decimal_places=2)
    fbr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    scattered_wholesale = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    madam_banam_fmc = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    madam_banam_nc = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    madam_wasooli = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # DR portion
    notes_5000 = models.PositiveIntegerField(default=0)
    notes_1000 = models.PositiveIntegerField(default=0)
    notes_500 = models.PositiveIntegerField(default=0)
    notes_100 = models.PositiveIntegerField(default=0)
    notes_50 = models.PositiveIntegerField(default=0)
    notes_20 = models.PositiveIntegerField(default=0)
    notes_10 = models.PositiveIntegerField(default=0)
    bank_transfer_1 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bank_transfer_2 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bank_transfer_3 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expense = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    market_credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    remarks = models.CharField(max_length=255, blank=True)
    posted_entry = models.OneToOneField(
        'accounting.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, related_name='settlement',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', 'dr__profile__dr_code']
        unique_together = ['date', 'dr']

    def __str__(self):
        return f'{self.date} {self.dr}'

    @property
    def total_cash(self):
        return Decimal(sum(getattr(self, f'notes_{d}') * d for d in self.NOTE_DENOMINATIONS))

    @property
    def total_bank(self):
        return self.bank_transfer_1 + self.bank_transfer_2 + self.bank_transfer_3

    @property
    def total_banam(self):
        return self.madam_banam_fmc + self.madam_banam_nc

    @property
    def total_accounted(self):
        """The slip's TOTAL line: everything the DR handed over or that is adjusted against the sale."""
        return (
            self.total_cash + self.total_bank + self.expense + self.market_credit
            + self.total_banam + self.fbr
        )

    @property
    def difference(self):
        """Positive = DR is short; negative = DR handed over more than due."""
        return self.total_sale + self.madam_wasooli - self.total_accounted

    @transaction.atomic
    def post_to_ledger(self, user=None):
        """
        Clear the DR's account for the money handed over: Dr Cash / Bank /
        Expense / FBR advance tax / Market credit receivable, Cr the DR.
        The DR's account was debited with the actual sale value when the
        day's actual sales were posted, so whatever stays on it is the DR's
        shortage. Banam is company-book only and has no ledger effect.
        """
        dr_party = dr_party_for(self.dr)
        lines = []
        if self.total_cash:
            lines.append({'account': ChartOfAccount.CASH, 'debit': self.total_cash})
        if self.total_bank:
            lines.append({'account': ChartOfAccount.BANK, 'debit': self.total_bank})
        if self.expense:
            lines.append({'account': ChartOfAccount.GENERAL_EXPENSE, 'debit': self.expense})
        if self.fbr:
            lines.append({'account': ChartOfAccount.ADVANCE_TAX_FBR, 'debit': self.fbr})
        if self.market_credit:
            credit_party, _ = Party.objects.get_or_create(
                name='Market credit (retailers on DR credit)', defaults={'party_type': Party.RETAILER},
            )
            lines.append({'account': ChartOfAccount.ACCOUNTS_RECEIVABLE, 'debit': self.market_credit, 'party': credit_party})
        handed_over = sum((line['debit'] for line in lines), Decimal('0'))
        if not handed_over:
            return None
        lines.append({'account': ChartOfAccount.ACCOUNTS_RECEIVABLE, 'credit': handed_over, 'party': dr_party})
        entry = JournalEntry.create_posted(
            source=JournalEntry.SOURCE_PAYMENT_RECEIPT, lines=lines, date=self.date,
            narration=f'DR settlement: {self.dr.get_full_name()}',
            reference=f'SETTLE-{self.dr.profile.dr_code}-{self.date:%Y%m%d}', created_by=user,
        )
        self.posted_entry = entry
        self.save(update_fields=['posted_entry'])
        return entry


def dr_party_for(user):
    """The accounting Party a DR's daily sales and settlements post against."""
    code = getattr(getattr(user, 'profile', None), 'dr_code', '') or user.username
    party, _ = Party.objects.get_or_create(
        name=f'DR {code} - {user.get_full_name() or user.username}',
        defaults={'party_type': Party.DR},
    )
    return party
