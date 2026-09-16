from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class Warehouse(models.Model):
    """
    A branch/warehouse. Seeded from Mumtaz & Co's real branch structure:
    Sargodha (HQ), Bhalwal and Bhera (out-stations — questionnaire answer
    #12 notes these need extra internal PO approval, #28 notes users are
    restricted per branch).
    """

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    location = models.CharField(max_length=200, blank=True)
    is_head_office = models.BooleanField(default=False)
    requires_po_approval = models.BooleanField(
        default=False,
        help_text='Out-station branches (e.g. Bhera, Bhalwal) require internal PO approval before submission to PTC.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def stock_on_hand(self, sku_id):
        level = self.stock_levels.filter(sku_id=sku_id).first()
        return level.quantity if level else 0


class StockLedgerEntry(models.Model):
    """
    Append-only movement log — the single source of truth for stock. Every
    other view (stock-on-hand report, inventory analytics, distribution
    out/in summaries) is derived from this table.
    """

    PURCHASE_IN = 'PURCHASE_IN'
    PURCHASE_RETURN_OUT = 'PURCHASE_RETURN_OUT'
    SALE_OUT = 'SALE_OUT'
    SALE_RETURN_IN = 'SALE_RETURN_IN'
    TRANSFER_OUT = 'TRANSFER_OUT'
    TRANSFER_IN = 'TRANSFER_IN'
    ADJUSTMENT = 'ADJUSTMENT'
    OPENING_BALANCE = 'OPENING_BALANCE'

    ENTRY_TYPE_CHOICES = [
        (PURCHASE_IN, 'Purchase received'),
        (PURCHASE_RETURN_OUT, 'Purchase return claimed back to PTC'),
        (SALE_OUT, 'Sale dispatched'),
        (SALE_RETURN_IN, 'Sale return received'),
        (TRANSFER_OUT, 'Transferred out to another warehouse'),
        (TRANSFER_IN, 'Transferred in from another warehouse'),
        (ADJUSTMENT, 'Adjustment (damage / loss / stolen / stock count)'),
        (OPENING_BALANCE, 'Opening balance (data migration)'),
    ]

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='ledger_entries')
    sku = models.ForeignKey('catalog.SKU', on_delete=models.PROTECT, related_name='ledger_entries')
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPE_CHOICES)
    quantity_change = models.DecimalField(
        max_digits=14, decimal_places=3,
        help_text='Signed quantity in sticks... or whatever base unit the SKU is tracked in. Positive = stock increase.',
    )
    reference = models.CharField(max_length=100, blank=True, help_text='PO/SO/Transfer/Claim number')
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['warehouse', 'sku']),
            models.Index(fields=['entry_type']),
        ]

    def __str__(self):
        return f'{self.warehouse} / {self.sku} {self.quantity_change:+} ({self.entry_type})'

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new:
                StockLevel.apply(self.warehouse_id, self.sku_id, self.quantity_change)


class StockLevel(models.Model):
    """Cached current on-hand quantity per warehouse/SKU, kept in sync by StockLedgerEntry.save()."""

    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stock_levels')
    sku = models.ForeignKey('catalog.SKU', on_delete=models.CASCADE, related_name='stock_levels')
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['warehouse', 'sku']

    def __str__(self):
        return f'{self.warehouse} / {self.sku}: {self.quantity}'

    @classmethod
    def apply(cls, warehouse_id, sku_id, delta):
        level, _ = cls.objects.get_or_create(warehouse_id=warehouse_id, sku_id=sku_id)
        level.quantity = models.F('quantity') + delta
        level.save(update_fields=['quantity', 'updated_at'])


class SafetyStockLevel(models.Model):
    """
    Minimum safety stock per warehouse/SKU (requirement doc, "Unique to
    Tobacco Distribution" #2: distributors must maintain a minimum safety
    stock under the PTC contract; questionnaire #17: "system should
    generate auto alert to maintain safe levels of stock").
    """

    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='safety_stock_levels')
    sku = models.ForeignKey('catalog.SKU', on_delete=models.CASCADE, related_name='safety_stock_levels')
    minimum_quantity = models.DecimalField(max_digits=14, decimal_places=3)

    class Meta:
        unique_together = ['warehouse', 'sku']

    def __str__(self):
        return f'{self.warehouse} / {self.sku}: min {self.minimum_quantity}'

    @property
    def current_quantity(self):
        return self.warehouse.stock_on_hand(self.sku_id)

    @property
    def is_below_minimum(self):
        return self.current_quantity < self.minimum_quantity


class StockTransfer(models.Model):
    """
    Movement of inventory between warehouses (requirement doc, Inventory #5).
    Between dispatch and receipt the stock is "in transit": it has already
    left the source warehouse's on-hand but is not yet in the
    destination's — matching the doc's call to reconcile stock in transit.
    """

    STATUS_DRAFT = 'DRAFT'
    STATUS_IN_TRANSIT = 'IN_TRANSIT'
    STATUS_RECEIVED = 'RECEIVED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_IN_TRANSIT, 'In transit'),
        (STATUS_RECEIVED, 'Received'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    transfer_number = models.CharField(max_length=30, unique=True)
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='transfers_out')
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='transfers_in')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.transfer_number

    @transaction.atomic
    def dispatch(self, user=None):
        if self.status != self.STATUS_DRAFT:
            raise ValueError('Only a draft transfer can be dispatched.')
        for line in self.lines.select_related('sku'):
            StockLedgerEntry.objects.create(
                warehouse=self.from_warehouse, sku=line.sku,
                entry_type=StockLedgerEntry.TRANSFER_OUT,
                quantity_change=-line.quantity, reference=self.transfer_number,
                created_by=user,
            )
        self.status = self.STATUS_IN_TRANSIT
        self.dispatched_at = timezone.now()
        self.save(update_fields=['status', 'dispatched_at'])

    @transaction.atomic
    def receive(self, user=None):
        if self.status != self.STATUS_IN_TRANSIT:
            raise ValueError('Only an in-transit transfer can be received.')
        for line in self.lines.select_related('sku'):
            StockLedgerEntry.objects.create(
                warehouse=self.to_warehouse, sku=line.sku,
                entry_type=StockLedgerEntry.TRANSFER_IN,
                quantity_change=line.quantity, reference=self.transfer_number,
                created_by=user,
            )
        self.status = self.STATUS_RECEIVED
        self.received_at = timezone.now()
        self.save(update_fields=['status', 'received_at'])


class StockTransferLine(models.Model):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='lines')
    sku = models.ForeignKey('catalog.SKU', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)

    def __str__(self):
        return f'{self.transfer.transfer_number}: {self.sku} x {self.quantity}'


class StockAdjustment(models.Model):
    """
    Damaged / lost / stolen stock, and periodic physical-count corrections
    (requirement doc, Inventory #7; questionnaire answer #19: "Periodic
    physical stock count to track discrepancies is mandatory"). Optionally
    linked to a PTC claim reference for reimbursement tracking.
    """

    REASON_DAMAGE = 'DAMAGE'
    REASON_LOST = 'LOST'
    REASON_STOLEN = 'STOLEN'
    REASON_COUNT_CORRECTION = 'COUNT_CORRECTION'
    REASON_CHOICES = [
        (REASON_DAMAGE, 'Damaged'),
        (REASON_LOST, 'Lost'),
        (REASON_STOLEN, 'Stolen'),
        (REASON_COUNT_CORRECTION, 'Physical count correction'),
    ]

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='adjustments')
    sku = models.ForeignKey('catalog.SKU', on_delete=models.PROTECT, related_name='adjustments')
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    quantity = models.DecimalField(
        max_digits=14, decimal_places=3,
        help_text='Enter as a positive number; it is applied as a stock decrease unless it is a positive count correction.',
    )
    is_increase = models.BooleanField(default=False, help_text='Tick only for a physical count correction that found MORE stock than recorded.')
    ptc_claim_reference = models.CharField(max_length=50, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ledger_entry = models.OneToOneField(
        StockLedgerEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name='adjustment'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_reason_display()}: {self.sku} x {self.quantity} @ {self.warehouse}'

    @transaction.atomic
    def apply(self, user=None):
        signed_qty = self.quantity if self.is_increase else -self.quantity
        entry = StockLedgerEntry.objects.create(
            warehouse=self.warehouse, sku=self.sku,
            entry_type=StockLedgerEntry.ADJUSTMENT,
            quantity_change=signed_qty,
            reference=self.ptc_claim_reference,
            notes=f'{self.get_reason_display()}: {self.notes}',
            created_by=user,
        )
        self.ledger_entry = entry
        self.created_by = user
        self.save(update_fields=['ledger_entry', 'created_by'])
