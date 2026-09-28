from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from accounting.models import ChartOfAccount, JournalEntry
from warehouses.models import StockLedgerEntry


class PurchaseOrder(models.Model):
    """
    Purchase order aligned with the order placed with PTC on its SAP
    portal (requirement doc, Purchase #1). Out-station branches (Bhera,
    Bhalwal) require an internal approval step before the order is
    considered submitted (questionnaire answer #12).
    """

    STATUS_DRAFT = 'DRAFT'
    STATUS_PENDING_APPROVAL = 'PENDING_APPROVAL'
    STATUS_SUBMITTED = 'SUBMITTED_TO_PTC'
    STATUS_RECEIVED = 'RECEIVED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PENDING_APPROVAL, 'Pending internal approval'),
        (STATUS_SUBMITTED, 'Submitted to PTC'),
        (STATUS_RECEIVED, 'Received'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    po_number = models.CharField(max_length=30, unique=True)
    ptc_reference_number = models.CharField(
        max_length=50, blank=True,
        help_text="PTC SAP reference number, once the order is placed on PTC's portal.",
    )
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='purchase_orders')
    supplier = models.ForeignKey('accounting.Party', on_delete=models.PROTECT, related_name='purchase_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    order_date = models.DateField(default=timezone.localdate)
    notes = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-order_date', '-id']

    def __str__(self):
        return self.po_number

    @property
    def total_value(self):
        return sum((line.quantity * line.unit_cost for line in self.lines.all()), Decimal('0'))

    def submit(self):
        if self.status != self.STATUS_DRAFT:
            raise ValueError('Only a draft PO can be submitted.')
        if self.warehouse.requires_po_approval:
            self.status = self.STATUS_PENDING_APPROVAL
        else:
            self.status = self.STATUS_SUBMITTED
        self.save(update_fields=['status', 'updated_at'])

    def approve(self, user):
        if self.status != self.STATUS_PENDING_APPROVAL:
            raise ValueError('Only a PO pending approval can be approved.')
        self.status = self.STATUS_SUBMITTED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

    @transaction.atomic
    def receive(self, user):
        """Update product inventory upon purchase (requirement doc, Inventory #3), and post the accounting entry."""
        if self.status != self.STATUS_SUBMITTED:
            raise ValueError('Only a PO submitted to PTC can be received.')
        for line in self.lines.select_related('sku'):
            StockLedgerEntry.objects.create(
                warehouse=self.warehouse, sku=line.sku,
                entry_type=StockLedgerEntry.PURCHASE_IN,
                quantity_change=line.quantity,
                reference=self.po_number, created_by=user,
                batch_number=line.batch_number, expiry_date=line.expiry_date,
            )
            if line.unit_cost and line.unit_cost != line.sku.current_cost_price:
                line.sku.set_cost_price(line.unit_cost, changed_by=user, note=f'Received on {self.po_number}')
        self.status = self.STATUS_RECEIVED
        self.received_at = timezone.now()
        self.save(update_fields=['status', 'received_at', 'updated_at'])
        self.post_accounting_entry(user=user)

    def post_accounting_entry(self, user=None):
        """
        Split out from receive() so a management command can backfill this
        for any PO that was received before the accounting module existed,
        without re-running receive() (which would re-dispatch stock).
        """
        value_total = self.total_value
        if value_total > 0:
            JournalEntry.create_posted(
                source=JournalEntry.SOURCE_PURCHASE,
                lines=[
                    {'account': ChartOfAccount.INVENTORY, 'debit': value_total},
                    {'account': ChartOfAccount.ACCOUNTS_PAYABLE, 'credit': value_total, 'party': self.supplier},
                ],
                narration=f'PO received from {self.supplier.name}', reference=self.po_number, created_by=user,
            )


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    sku = models.ForeignKey('catalog.SKU', on_delete=models.PROTECT, related_name='purchase_order_lines')
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    batch_number = models.CharField(
        max_length=50, blank=True, help_text='Optional — needed for batch-tracked SKUs like VELO (questionnaire #18).'
    )
    expiry_date = models.DateField(null=True, blank=True, help_text='Optional — needed for batch-tracked SKUs like VELO.')

    def __str__(self):
        return f'{self.purchase_order.po_number}: {self.sku} x {self.quantity}'

    @property
    def line_total(self):
        return self.quantity * self.unit_cost


class PurchaseReturn(models.Model):
    """Purchase return claim aligned with PTC workflow (requirement doc, Purchase #2)."""

    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_SETTLED = 'SETTLED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SUBMITTED, 'Submitted to PTC'),
        (STATUS_SETTLED, 'Settled'),
    ]

    return_number = models.CharField(max_length=30, unique=True)
    purchase_order = models.ForeignKey(
        PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name='returns'
    )
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='purchase_returns')
    sku = models.ForeignKey('catalog.SKU', on_delete=models.PROTECT, related_name='purchase_returns')
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    reason = models.CharField(max_length=255)
    ptc_claim_reference = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.return_number

    def _resolve_unit_cost(self):
        """Best-effort purchase cost for reversing the payable: the original PO line, else the SKU's current cost."""
        if self.purchase_order:
            line = self.purchase_order.lines.filter(sku=self.sku).first()
            if line:
                return line.unit_cost
        return self.sku.current_cost_price

    @transaction.atomic
    def submit(self, user):
        if self.status != self.STATUS_DRAFT:
            raise ValueError('Only a draft return can be submitted.')
        StockLedgerEntry.objects.create(
            warehouse=self.warehouse, sku=self.sku,
            entry_type=StockLedgerEntry.PURCHASE_RETURN_OUT,
            quantity_change=-self.quantity,
            reference=self.return_number, created_by=user,
        )
        self.status = self.STATUS_SUBMITTED
        self.save(update_fields=['status'])

        supplier = self.purchase_order.supplier if self.purchase_order else None
        value_total = self.quantity * self._resolve_unit_cost()
        if supplier and value_total > 0:
            JournalEntry.create_posted(
                source=JournalEntry.SOURCE_PURCHASE_RETURN,
                lines=[
                    {'account': ChartOfAccount.ACCOUNTS_PAYABLE, 'debit': value_total, 'party': supplier},
                    {'account': ChartOfAccount.INVENTORY, 'credit': value_total},
                ],
                narration=f'Purchase return to {supplier.name}', reference=self.return_number, created_by=user,
            )
