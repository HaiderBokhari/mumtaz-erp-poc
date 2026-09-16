from django.conf import settings
from django.db import models
from django.utils import timezone


class Brand(models.Model):
    """Brand Life Cycle Management (requirement doc, Inventory #2)."""

    STATUS_ACTIVE = 'ACTIVE'
    STATUS_DISCONTINUED = 'DISCONTINUED'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_DISCONTINUED, 'Discontinued'),
    ]

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class SKU(models.Model):
    """
    SKU Life Cycle Management (requirement doc, Inventory #1).

    Mirrors the real PTC catalogue structure seen in Mumtaz & Co's sheets:
    a brand (DUNHILL, GOLD LEAF, CAPSTAN, VELO, ...) broken into SKUs by
    variant/pack, e.g. "Dunhill Lights 20 HL", tracked in Millions of
    sticks (1 M = 1000 sticks) same as PTC's own reporting.
    """

    STATUS_ACTIVE = 'ACTIVE'
    STATUS_DISCONTINUED = 'DISCONTINUED'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_DISCONTINUED, 'Discontinued'),
    ]

    code = models.CharField(max_length=30, unique=True, help_text='Internal SKU code, e.g. DNH-20HL')
    name = models.CharField(max_length=150)
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name='skus')
    variant = models.CharField(max_length=100, blank=True, help_text='e.g. Lights, Swiss, Regular')
    pack_size = models.CharField(max_length=20, help_text='e.g. 20 HL, 10 HL, LEP')
    sticks_per_pack = models.PositiveIntegerField(default=20)
    barcode = models.CharField(max_length=64, blank=True)
    current_cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['brand__name', 'name']
        verbose_name = 'SKU'
        verbose_name_plural = 'SKUs'

    def __str__(self):
        return f'{self.code} - {self.name}'

    def discontinue(self):
        self.status = self.STATUS_DISCONTINUED
        self.save(update_fields=['status', 'updated_at'])

    def set_cost_price(self, new_cost, changed_by=None, note=''):
        """Update the current cost and append a history row (requirement doc, Inventory #8)."""
        CostPriceHistory.objects.create(
            sku=self, cost_price=new_cost, changed_by=changed_by, note=note,
        )
        self.current_cost_price = new_cost
        self.save(update_fields=['current_cost_price', 'updated_at'])


class CostPriceHistory(models.Model):
    """Append-only log of SKU cost changes, per requirement doc Inventory #8."""

    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name='cost_history')
    cost_price = models.DecimalField(max_digits=12, decimal_places=2)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    note = models.CharField(max_length=255, blank=True)
    effective_from = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-effective_from']
        verbose_name_plural = 'Cost price history'

    def __str__(self):
        return f'{self.sku.code} -> {self.cost_price} @ {self.effective_from:%Y-%m-%d}'


class Channel(models.Model):
    """
    Channel lifecycle management (requirement doc, Distribution #1).

    Channel types match PTC's own route-to-market terminology used by
    Mumtaz & Co (see "How PTC Distributor Works"):
      DD    - Direct Sale & Delivery (Urban Retail)
      VDD   - Village Direct Sales & Delivery (Rural Retail)
      WS    - Urban Whole Sale
      VWS   - Village Whole Sale (Rural Wholesale)
      MANDI - Mandi Whole Sale (rates change daily/weekly, biggest channel)
    """

    TYPE_DD = 'DD'
    TYPE_VDD = 'VDD'
    TYPE_WS = 'WS'
    TYPE_VWS = 'VWS'
    TYPE_MANDI = 'MANDI'
    TYPE_CHOICES = [
        (TYPE_DD, 'DD - Urban Retail (Direct Delivery)'),
        (TYPE_VDD, 'VDD - Rural Retail (Village Direct Delivery)'),
        (TYPE_WS, 'WS - Urban Wholesale'),
        (TYPE_VWS, 'VWS - Rural Wholesale'),
        (TYPE_MANDI, 'MANDI - Mandi Wholesale'),
    ]

    FILER = 'FILER'
    NON_FILER = 'NON_FILER'
    FILER_CHOICES = [
        (FILER, 'Filer'),
        (NON_FILER, 'Non-Filer'),
    ]

    STATUS_ACTIVE = 'ACTIVE'
    STATUS_DORMANT = 'DORMANT'
    STATUS_CLOSED = 'CLOSED'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_DORMANT, 'Dormant'),
        (STATUS_CLOSED, 'Closed'),
    ]

    name = models.CharField(max_length=100)
    channel_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    filer_status = models.CharField(max_length=10, choices=FILER_CHOICES, default=NON_FILER)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    opened_on = models.DateField(default=timezone.now)
    closed_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['channel_type', 'name']
        unique_together = ['name', 'channel_type', 'filer_status']

    def __str__(self):
        return f'{self.name} ({self.get_channel_type_display()}, {self.get_filer_status_display()})'


class ChannelPrice(models.Model):
    """
    Channel-wise, filer/non-filer-aware SKU pricing, kept as an append-only
    history so price changes are auditable (requirement doc, Inventory #8
    and Distribution #1: "Each channel will have its own price for each SKU
    which can be modified by an authorized user only as and when needed.").

    The *current* price for a (channel, sku) pair is the row with the latest
    ``effective_from`` that is not in the future.
    """

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='prices')
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name='channel_prices')
    price = models.DecimalField(max_digits=12, decimal_places=2)
    effective_from = models.DateField(default=timezone.now)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_from']
        unique_together = ['channel', 'sku', 'effective_from']
        verbose_name_plural = 'Channel prices'

    def __str__(self):
        return f'{self.sku.code} @ {self.channel.name}: {self.price} (from {self.effective_from})'

    @classmethod
    def current_price(cls, channel_id, sku_id, on_date=None):
        on_date = on_date or timezone.localdate()
        row = (
            cls.objects.filter(channel_id=channel_id, sku_id=sku_id, effective_from__lte=on_date)
            .order_by('-effective_from')
            .first()
        )
        return row.price if row else None
