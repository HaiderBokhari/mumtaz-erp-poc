"""
Accounting module — POC STUB.

The full requirement (Chart of Accounts, double-entry vouchers, financial
statements, party ledgers with running balances) is a substantial module of
its own — see CLAUDE.md "Suggested build order" for the plan. For this POC
we only model the two pieces that Purchasing/Distribution already need to
point at:

  * ``Party`` — a supplier (PTC), retailer or wholesaler that money moves
    to/from. Purchase orders and shops reference this so the real ledger
    can be layered in later without a schema migration on those apps.
  * ``ChartOfAccount`` — enough structure (groups + accounts with unique
    codes) to demo the "Account Groups, Subgroups, Chart of Accounts"
    requirement, without yet posting real journal entries against it.
"""
from django.db import models


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

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    account_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    group = models.ForeignKey(AccountGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name='accounts')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} - {self.name}'


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
