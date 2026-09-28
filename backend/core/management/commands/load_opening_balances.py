"""
Load opening balances from CSVs the client provides (PDF "Data Transfer":
"client will provide us with the closing balances of all the accounts which
we will enter into the new system as opening balances"; questionnaire #31:
the client's historical data starts January 2026). Two independent,
optional CSV inputs:

  --stock-csv: warehouse_code,sku_code,quantity[,batch_number,expiry_date]
      -> one StockLedgerEntry(entry_type=OPENING_BALANCE) per row, the same
      pattern seed_demo_data._seed_opening_stock already uses.

  --accounts-csv: account_code,debit,credit[,party_name,party_type,narration]
      -> one balanced JournalEntry(source=OPENING_BALANCE) per row, each
      posted against Owner's Equity as the offsetting side. Posting row by
      row like this (rather than requiring one big pre-balanced entry)
      means a raw trial-balance export — which lists every account's
      balance on one side only — can be loaded directly; Owner's Equity
      nets to zero automatically as long as the trial balance itself
      balances (assets = liabilities + equity).

Usage:
  python manage.py load_opening_balances --stock-csv stock.csv --accounts-csv accounts.csv [--date 2026-01-01]

Not safe to re-run on the same data: each run posts new ledger entries with
no de-duplication (matching how seed_demo_data's OPENING_BALANCE rows work
too) — run it once per real data set.
"""
import csv
from datetime import date as date_cls, datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounting.models import ChartOfAccount, JournalEntry, Party
from catalog.models import SKU
from warehouses.models import StockLedgerEntry, Warehouse


class Command(BaseCommand):
    help = 'Load opening stock and/or opening account balances from CSV files provided by the client.'

    def add_arguments(self, parser):
        parser.add_argument('--stock-csv', help='Path to a warehouse_code,sku_code,quantity[,batch_number,expiry_date] CSV.')
        parser.add_argument('--accounts-csv', help='Path to an account_code,debit,credit[,party_name,party_type,narration] CSV.')
        parser.add_argument('--date', default=None, help='Opening balance date, YYYY-MM-DD (default: today).')

    def handle(self, *args, **options):
        if not options['stock_csv'] and not options['accounts_csv']:
            raise CommandError('Pass at least one of --stock-csv or --accounts-csv.')

        as_of = date_cls.fromisoformat(options['date']) if options['date'] else timezone.localdate()

        if options['stock_csv']:
            self._load_stock(options['stock_csv'], as_of)
        if options['accounts_csv']:
            self._load_accounts(options['accounts_csv'], as_of)

    @transaction.atomic
    def _load_stock(self, path, as_of):
        as_of_dt = timezone.make_aware(datetime.combine(as_of, datetime.min.time()))
        created = 0
        with open(path, newline='', encoding='utf-8-sig') as f:
            for i, row in enumerate(csv.DictReader(f), start=2):
                warehouse = Warehouse.objects.filter(code=row['warehouse_code'].strip()).first()
                if not warehouse:
                    raise CommandError(f'Row {i}: no warehouse with code "{row["warehouse_code"]}"')
                sku = SKU.objects.filter(code=row['sku_code'].strip()).first()
                if not sku:
                    raise CommandError(f'Row {i}: no SKU with code "{row["sku_code"]}"')
                try:
                    qty = Decimal(row['quantity'])
                except (InvalidOperation, KeyError):
                    raise CommandError(f'Row {i}: invalid quantity "{row.get("quantity")}"')
                StockLedgerEntry.objects.create(
                    warehouse=warehouse, sku=sku, entry_type=StockLedgerEntry.OPENING_BALANCE,
                    quantity_change=qty, reference='OPENING-BALANCE-IMPORT',
                    batch_number=(row.get('batch_number') or '').strip(),
                    expiry_date=row.get('expiry_date') or None,
                    created_at=as_of_dt,
                )
                created += 1
        self.stdout.write(self.style.SUCCESS(f'Loaded {created} opening stock line(s).'))

    @transaction.atomic
    def _load_accounts(self, path, as_of):
        created = 0
        with open(path, newline='', encoding='utf-8-sig') as f:
            for i, row in enumerate(csv.DictReader(f), start=2):
                account = ChartOfAccount.objects.filter(code=row['account_code'].strip()).first()
                if not account:
                    raise CommandError(f'Row {i}: no chart-of-accounts entry with code "{row["account_code"]}"')
                try:
                    debit = Decimal(row.get('debit') or 0)
                    credit = Decimal(row.get('credit') or 0)
                except InvalidOperation:
                    raise CommandError(f'Row {i}: invalid debit/credit amount.')
                if debit and credit:
                    raise CommandError(f'Row {i}: a single opening-balance row cannot have both a debit and a credit.')
                if not debit and not credit:
                    continue

                party = None
                party_name = (row.get('party_name') or '').strip()
                if party_name:
                    party_type = (row.get('party_type') or Party.RETAILER).strip().upper()
                    party, _ = Party.objects.get_or_create(name=party_name, defaults={'party_type': party_type})

                lines = [{'account': account, 'debit': debit, 'credit': credit, 'party': party}]
                equity = ChartOfAccount.get(ChartOfAccount.OWNER_EQUITY)
                lines.append({'account': equity, 'credit': debit} if debit else {'account': equity, 'debit': credit})

                JournalEntry.create_posted(
                    source=JournalEntry.SOURCE_OPENING_BALANCE, lines=lines, date=as_of,
                    narration=(row.get('narration') or f'Opening balance: {account.name}').strip(),
                    reference='OPENING-BALANCE-IMPORT',
                )
                created += 1
        self.stdout.write(self.style.SUCCESS(f'Loaded {created} opening account balance entr{"y" if created == 1 else "ies"}.'))
