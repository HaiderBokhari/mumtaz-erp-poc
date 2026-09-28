"""
Accounting module (requirement doc, Accounts management #1-9).

Follows the same append-only-ledger pattern as ``warehouses.StockLedgerEntry``:
``JournalLine`` is the single source of truth for every debit/credit, and
``PartyBalance``/account balances are derived from it (never written to
directly). Everything that moves money — a confirmed sale, a received
purchase order, a payment receipt, a stock adjustment, or a manually entered
``Voucher`` — ends up as one balanced ``JournalEntry``.

  * ``ChartOfAccount`` — Account Groups, Subgroups, Chart of Accounts with a
    unique code per account (Accounts #1). ``ChartOfAccount.get(code)`` is
    how posting code elsewhere in the app finds "the" inventory/cash/payable
    account without hardcoding a primary key — see ``DEFAULT_ACCOUNTS``
    below and ``core.management.commands.seed_demo_data``.
  * ``JournalEntry`` / ``JournalLine`` — double-entry bookkeeping (Accounts
    #2): a balanced set of debit/credit lines against accounts, optionally
    tagged with a ``Party`` for receivable/payable tracking.
  * ``Voucher`` / ``VoucherLine`` — the payment/journal/expense voucher
    system users interact with directly (Accounts #3). Distribution and
    Purchasing post their own ``JournalEntry`` automatically on confirm/
    receive rather than going through a Voucher, per the requirement doc:
    "Distribution module related accounting entries will be embedded within
    the relevant features."
  * ``Party`` — a supplier (PTC), retailer or wholesaler with a running
    ledger balance, used by both Purchasing (``PurchaseOrder.supplier``) and
    Distribution (``Shop.party``).
"""
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class AccountGroup(models.Model):
    """Requirement doc, Accounts #1: "Account Groups, Subgroups"."""

    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='children')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ChartOfAccount(models.Model):
    """Requirement doc, Accounts #1: "Charts of Account with unique code for each account"."""

    TYPE_ASSET = 'ASSET'
    TYPE_LIABILITY = 'LIABILITY'
    TYPE_EQUITY = 'EQUITY'
    TYPE_INCOME = 'INCOME'
    TYPE_EXPENSE = 'EXPENSE'
    TYPE_CHOICES = [
        (TYPE_ASSET, 'Asset'),
        (TYPE_LIABILITY, 'Liability'),
        (TYPE_EQUITY, 'Equity'),
        (TYPE_INCOME, 'Income'),
        (TYPE_EXPENSE, 'Expense'),
    ]

    # Well-known codes that posting code elsewhere in the app (Distribution,
    # Purchasing, Warehouses) looks up by code rather than by primary key.
    # Seeded by seed_demo_data / seed_chart_of_accounts — see ChartOfAccount.get().
    CASH = '1000'
    BANK = '1010'
    ACCOUNTS_RECEIVABLE = '1100'
    INVENTORY = '1200'
    ACCOUNTS_PAYABLE = '2100'
    OWNER_EQUITY = '3000'
    SALES_REVENUE = '4000'
    COST_OF_GOODS_SOLD = '5000'
    INVENTORY_ADJUSTMENTS = '5100'
    SALARY_EXPENSE = '5200'
    GENERAL_EXPENSE = '5900'

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    account_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    group = models.ForeignKey(AccountGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name='accounts')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} - {self.name}'

    @classmethod
    def get(cls, code):
        try:
            return cls.objects.get(code=code)
        except cls.DoesNotExist:
            raise ValueError(
                f'Chart of accounts is missing required account "{code}". '
                'Run `python manage.py seed_demo_data` (or create it in /admin/) first.'
            )

    @property
    def normal_balance_is_debit(self):
        """Asset/Expense accounts increase on debit; Liability/Equity/Income increase on credit."""
        return self.account_type in (self.TYPE_ASSET, self.TYPE_EXPENSE)

    @property
    def balance(self):
        """Running balance of this account, signed per its normal balance side."""
        totals = self.journal_lines.aggregate(debit=models.Sum('debit'), credit=models.Sum('credit'))
        debit = totals['debit'] or Decimal('0')
        credit = totals['credit'] or Decimal('0')
        return (debit - credit) if self.normal_balance_is_debit else (credit - debit)


class Party(models.Model):
    """
    A supplier, retailer or wholesaler with a running account balance.
    Requirement doc, Purchase #3 and Accounts #5 ("party ledgers").
    """

    SUPPLIER = 'SUPPLIER'
    RETAILER = 'RETAILER'
    WHOLESALER = 'WHOLESALER'
    PARTY_TYPE_CHOICES = [
        (SUPPLIER, 'Supplier'),
        (RETAILER, 'Retailer'),
        (WHOLESALER, 'Wholesaler'),
    ]

    name = models.CharField(max_length=150)
    party_type = models.CharField(max_length=20, choices=PARTY_TYPE_CHOICES)
    contact_phone = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    credit_limit = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text='Questionnaire #9: credit limits are set for wholesalers; most retailers get none.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Parties'

    def __str__(self):
        return self.name

    @property
    def control_account_code(self):
        """Which control account this party's ledger lines post against."""
        return ChartOfAccount.ACCOUNTS_PAYABLE if self.party_type == self.SUPPLIER else ChartOfAccount.ACCOUNTS_RECEIVABLE

    @property
    def balance(self):
        """
        Running balance since inception. For a supplier this is what we owe
        them (credit-normal, shown positive when we owe money). For a
        retailer/wholesaler this is what they owe us (debit-normal, shown
        positive when they owe money).
        """
        bal, _ = PartyBalance.objects.get_or_create(party=self)
        return bal.balance


class PartyBalance(models.Model):
    """
    Cached running balance per party, kept in sync by JournalLine.save() —
    same pattern as warehouses.StockLevel for StockLedgerEntry. Positive =
    they owe us (retailer/wholesaler) or we owe them (supplier), matching
    each party's control account's normal balance side.
    """

    party = models.OneToOneField(Party, on_delete=models.CASCADE, related_name='_balance_cache')
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.party}: {self.balance}'

    @classmethod
    def apply(cls, party_id, delta):
        bal, _ = cls.objects.get_or_create(party_id=party_id)
        bal.balance = models.F('balance') + delta
        bal.save(update_fields=['balance', 'updated_at'])


class JournalEntry(models.Model):
    """
    Append-only header for a balanced set of debit/credit lines — the
    accounting equivalent of ``warehouses.StockLedgerEntry``. Never edited
    after posting; corrections are made with a reversing entry.
    """

    SOURCE_VOUCHER = 'VOUCHER'
    SOURCE_PURCHASE = 'PURCHASE'
    SOURCE_PURCHASE_RETURN = 'PURCHASE_RETURN'
    SOURCE_SALE = 'SALE'
    SOURCE_SALE_RETURN = 'SALE_RETURN'
    SOURCE_PAYMENT_RECEIPT = 'PAYMENT_RECEIPT'
    SOURCE_STOCK_ADJUSTMENT = 'STOCK_ADJUSTMENT'
    SOURCE_OPENING_BALANCE = 'OPENING_BALANCE'
    SOURCE_CHOICES = [
        (SOURCE_VOUCHER, 'Voucher'),
        (SOURCE_PURCHASE, 'Purchase order received'),
        (SOURCE_PURCHASE_RETURN, 'Purchase return'),
        (SOURCE_SALE, 'Sales order confirmed'),
        (SOURCE_SALE_RETURN, 'Sales return'),
        (SOURCE_PAYMENT_RECEIPT, 'Payment receipt'),
        (SOURCE_STOCK_ADJUSTMENT, 'Stock adjustment'),
        (SOURCE_OPENING_BALANCE, 'Opening balance (data migration)'),
    ]

    date = models.DateField(default=timezone.localdate)
    narration = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    reference = models.CharField(max_length=100, blank=True, help_text='PO/SO/Voucher/Claim number')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name_plural = 'Journal entries'

    def __str__(self):
        return f'JE-{self.id} {self.date} {self.get_source_display()} ({self.reference})'

    @property
    def total_debit(self):
        return sum((line.debit for line in self.lines.all()), Decimal('0'))

    @property
    def total_credit(self):
        return sum((line.credit for line in self.lines.all()), Decimal('0'))

    @classmethod
    @transaction.atomic
    def create_posted(cls, *, source, lines, date=None, narration='', reference='', created_by=None):
        """
        Create a JournalEntry and its lines atomically, validating the
        entry balances (Accounts #2: "keep the business books balanced").
        ``lines`` is a list of dicts: {account (code or ChartOfAccount),
        debit=0, credit=0, party=None}.
        """
        if not lines:
            raise ValueError('A journal entry needs at least one line.')

        entry = cls.objects.create(
            date=date or timezone.localdate(), narration=narration,
            source=source, reference=reference, created_by=created_by,
        )
        total_debit = total_credit = Decimal('0')
        for line in lines:
            account = line['account']
            if isinstance(account, str):
                account = ChartOfAccount.get(account)
            debit = Decimal(line.get('debit') or 0)
            credit = Decimal(line.get('credit') or 0)
            total_debit += debit
            total_credit += credit
            JournalLine.objects.create(
                entry=entry, account=account, party=line.get('party'),
                debit=debit, credit=credit,
            )
        if total_debit != total_credit:
            raise ValueError(f'Unbalanced journal entry: total debit {total_debit} != total credit {total_credit}')
        return entry


class JournalLine(models.Model):
    """One debit or credit against one account, optionally tied to a Party."""

    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(ChartOfAccount, on_delete=models.PROTECT, related_name='journal_lines')
    party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.PROTECT, related_name='journal_lines')
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        indexes = [
            models.Index(fields=['account']),
            models.Index(fields=['party']),
        ]

    def __str__(self):
        side = f'Dr {self.debit}' if self.debit else f'Cr {self.credit}'
        return f'{self.account.code} {side}'

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new and self.party_id:
                # Party balance convention: debit increases it, credit decreases
                # it — correct for both a receivable (debit-normal, retailer
                # owes more) and a payable (credit-normal debits *reduce* what
                # we owe, e.g. paying a supplier), since PartyBalance.balance
                # is interpreted per the party's own control-account side.
                delta = self.debit - self.credit
                if self.party.party_type == Party.SUPPLIER:
                    delta = -delta
                PartyBalance.apply(self.party_id, delta)


class Voucher(models.Model):
    """
    Payment (cash/bank), journal, or expense voucher (Accounts #3): "The
    vouchers will be limited to payment (cash or bank modes), journal
    voucher, expense voucher only."
    """

    TYPE_PAYMENT = 'PAYMENT'
    TYPE_JOURNAL = 'JOURNAL'
    TYPE_EXPENSE = 'EXPENSE'
    TYPE_CHOICES = [
        (TYPE_PAYMENT, 'Payment voucher'),
        (TYPE_JOURNAL, 'Journal voucher'),
        (TYPE_EXPENSE, 'Expense voucher'),
    ]

    MODE_CASH = 'CASH'
    MODE_BANK = 'BANK'
    MODE_CHOICES = [(MODE_CASH, 'Cash'), (MODE_BANK, 'Bank')]

    STATUS_DRAFT = 'DRAFT'
    STATUS_POSTED = 'POSTED'
    STATUS_CHOICES = [(STATUS_DRAFT, 'Draft'), (STATUS_POSTED, 'Posted')]

    voucher_number = models.CharField(max_length=30, unique=True)
    voucher_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    date = models.DateField(default=timezone.localdate)
    narration = models.CharField(max_length=255, blank=True)
    party = models.ForeignKey(
        Party, null=True, blank=True, on_delete=models.PROTECT, related_name='vouchers',
        help_text='Payment voucher: who the payment is to/from.',
    )
    payment_mode = models.CharField(max_length=10, choices=MODE_CHOICES, blank=True, help_text='Payment/Expense vouchers only.')
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Payment/Expense vouchers: the single amount moved. Journal vouchers use the line items instead.',
    )
    debit_account = models.ForeignKey(
        ChartOfAccount, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
        help_text='Payment: the payable/expense account being debited. Expense: the expense account.',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    journal_entry = models.OneToOneField(JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name='voucher')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f'{self.voucher_number} ({self.get_voucher_type_display()})'

    @transaction.atomic
    def post(self, user=None):
        if self.status != self.STATUS_DRAFT:
            raise ValueError('Only a draft voucher can be posted.')

        if self.voucher_type == self.TYPE_JOURNAL:
            lines = [
                {'account': l.account, 'debit': l.debit, 'credit': l.credit, 'party': l.party}
                for l in self.lines.all()
            ]
        else:
            if not self.amount or not self.debit_account:
                raise ValueError('Payment/expense vouchers need an amount and a debit account.')
            cash_or_bank = ChartOfAccount.get(ChartOfAccount.BANK if self.payment_mode == self.MODE_BANK else ChartOfAccount.CASH)
            lines = [
                {'account': self.debit_account, 'debit': self.amount, 'party': self.party},
                {'account': cash_or_bank, 'credit': self.amount},
            ]

        entry = JournalEntry.create_posted(
            source=JournalEntry.SOURCE_VOUCHER, lines=lines, date=self.date,
            narration=self.narration, reference=self.voucher_number, created_by=user,
        )
        self.journal_entry = entry
        self.status = self.STATUS_POSTED
        self.save(update_fields=['journal_entry', 'status'])


class VoucherLine(models.Model):
    """Line items for a JOURNAL-type voucher only (payment/expense vouchers use amount + debit_account)."""

    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(ChartOfAccount, on_delete=models.PROTECT, related_name='+')
    party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    def __str__(self):
        return f'{self.voucher.voucher_number}: {self.account.code} Dr{self.debit}/Cr{self.credit}'
