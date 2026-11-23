"""
Load a Mumtaz & Co data bundle (see ``build_client_bundle``) into the ERP,
replacing the made-up demo data with the distributor's real September
catalogue, DRs, outlets and sales.

Two books are loaded side by side, which is how the business actually runs:

* **Company book** — BIZOM invoices, as ``SalesOrder`` rows with
  ``source=BIZOM_UPLOAD``. No stock movement: an invoice can be raised for
  stock that never leaves the godown ("Madam Banam").
* **Actual book** — the distributor's own daily actual-sale sheet, as
  ``ActualSale`` rows. Physical stock (``SALE_OUT``), revenue and DR cash
  settlement follow this book.

What the files don't contain is seeded and labelled as such (opening
stock, weekly PTC lifting, DR cash split, expenses, targets) so the demo
works end to end; replace it as the real figures arrive.

Loading resets business data (catalogue, shops, stock, sales, accounting,
HR, DR logins). Staff/owner logins, roles, warehouses and the chart of
accounts are kept.
"""
import datetime
import random
import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.db import transaction
from django.db.models import Sum as models_sum
from django.utils import timezone

from accounting.models import ChartOfAccount, JournalEntry, JournalLine, Party, PartyBalance, Voucher
from accounts.models import UserProfile
from catalog.models import Brand, Channel, ChannelPrice, CostPriceHistory, SKU
from distribution.actual_entry import COLUMN_BY_KEY, column_matches, default_sku_name
from distribution.models import (
    ActualSale, DRSettlement, PaymentReceipt, SalesOrder, SalesOrderLine, SalesReturn,
    SalesTarget, Shop, dr_party_for,
)
from hr.models import CommissionRate, Employee, LeaveRequest, PayGrade, SalaryPayment
from purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseReturn
from warehouses.models import (
    SafetyStockLevel, StockAdjustment, StockLedgerEntry, StockLevel, StockTransfer,
    StockTransferLine, Warehouse,
)

D0 = Decimal('0')
SEED_NOTE = 'seeded for demo'

CHANNEL_DEFS = [
    (Channel.TYPE_DD, 'DD - Urban Retail'),
    (Channel.TYPE_VDD, 'VDD - Rural Retail'),
    (Channel.TYPE_WS, 'UWS - Urban Wholesale'),
    (Channel.TYPE_VWS, 'RWS - Rural Wholesale'),
    (Channel.TYPE_MANDI, 'MANDI - Wholesale Mandi'),
]
ADJUSTED_GODOWN = {
    'code': 'SGD-ADJ', 'name': 'Sargodha Adjusted Stock (Madam)', 'location': 'Sargodha',
    'is_head_office': False, 'requires_po_approval': False,
}


def q3(value):
    return Decimal(str(value)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)


def q2(value):
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def aware(day, hour):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour)))


def sku_code(name, brand, used):
    """Readable unique code, e.g. 'Velo Polar Mint 10MG Music Edition' -> 'VELO-PM10ME'."""
    brand_words = {w.lower() for w in re.findall(r'[A-Za-z]+', brand)}
    parts = []
    for word in re.findall(r'[A-Za-z]+|\d+', name):
        if word.lower() in brand_words or word.lower() in {'by', 'new', 'the'}:
            continue
        parts.append(word if word.isdigit() else word[0].upper())
    prefix = re.sub(r'[^A-Z]', '', brand.upper())[:4]
    base = f"{prefix}-{''.join(parts)}"[:28] or prefix
    code, n = base, 2
    while code in used:
        code, n = f'{base}{n}', n + 1
    used.add(code)
    return code


class BundleLoader:
    def __init__(self, bundle, log=print, seed=42):
        self.b = bundle
        self.log = log
        self.rng = random.Random(seed)
        year, month = map(int, bundle['month'].split('-'))
        self.month_start = datetime.date(year, month, 1)
        next_month = (self.month_start + datetime.timedelta(days=32)).replace(day=1)
        self.month_end = next_month - datetime.timedelta(days=1)

    @transaction.atomic
    def run(self):
        self._wipe()
        self._base()
        self._catalog()
        self._channels()
        self._people()
        self._shops()
        self._company_book()
        self._actual_book()
        self._stock()
        self._accounting()
        self._settlements()
        self._payroll()
        StockLevel.rebuild_from_ledger()
        self.log('Client bundle loaded.')

    # -- reset -------------------------------------------------------------

    def _wipe(self):
        self.log('Clearing existing business data...')
        for model in [
            DRSettlement, ActualSale, SalesReturn, PaymentReceipt, SalesOrderLine, SalesOrder,
            SalesTarget, Shop, PurchaseReturn, PurchaseOrderLine, PurchaseOrder, StockAdjustment,
            StockTransferLine, StockTransfer, StockLedgerEntry, StockLevel, SafetyStockLevel,
            Voucher, JournalLine, JournalEntry, PartyBalance, Party, SalaryPayment, LeaveRequest,
            Employee, CommissionRate, PayGrade, ChannelPrice, Channel, CostPriceHistory, SKU, Brand,
        ]:
            # Listed children-first, so a raw delete (no per-row cascade
            # collection, which chokes on ~200k order lines) is safe.
            model.objects.all()._raw_delete(model.objects.db)
        User.objects.filter(groups__name=settings.ROLE_DR).delete()
        User.objects.filter(groups__name=settings.ROLE_FSO, profile__dr_code__startswith='SGD_').delete()

    def _base(self):
        from core.management.commands.seed_demo_data import Command as SeedCommand

        seeder = SeedCommand()
        groups = seeder._seed_roles()
        seeder._seed_chart_of_accounts()
        self.warehouses = seeder._seed_warehouses()
        self.warehouses['SGD-ADJ'], _ = Warehouse.objects.get_or_create(
            code=ADJUSTED_GODOWN['code'], defaults=ADJUSTED_GODOWN,
        )
        self.users = seeder._seed_users(groups)
        self.groups = groups
        self.owner = self.users['owner']
        self.hq = self.warehouses['SGD-HQ']

    # -- catalogue -------------------------------------------------------------

    def _catalog(self):
        self.log('Loading catalogue...')
        self.skus = {}
        self.sku_info = {}
        brands = {}
        used_codes = set()
        for info in self.b['skus']:
            brand_name = info['brand']
            if brand_name not in brands:
                code = re.sub(r'[^A-Z]', '', brand_name.upper())[:12] or 'BRAND'
                brands[brand_name] = Brand.objects.create(name=brand_name, code=code)
            name = info['bizom_name']
            is_velo = info['category'] == SKU.CATEGORY_NC
            mg = re.search(r'(\d+)\s*mg', name, re.I)
            sku = SKU.objects.create(
                code=sku_code(name, brand_name, used_codes), name=name, bizom_name=name,
                brand=brands[brand_name], category=info['category'],
                variant=name.replace(brand_name, '').strip() if not is_velo else name[5:].strip(),
                pack_size=('Pouch can' + (f" {mg.group(1)}mg" if mg else '')) if is_velo else '20 HL',
                sticks_per_pack=15 if 'nano' in name.lower() else 20,
                current_cost_price=q2(info['ptc_rate']),
            )
            CostPriceHistory.objects.create(
                sku=sku, cost_price=sku.current_cost_price, changed_by=self.owner,
                note='PTC invoice rate per M (FMC AND NC list)' if info['ptc_rate_source'] == 'ptc_price_list'
                else 'Estimated: not on PTC rate list yet (retail price less ~4.5%)',
                effective_from=aware(self.month_start, 6),
            )
            retail, scattered = info['commission']
            CommissionRate.objects.create(sku=sku, retail_per_m=retail, scattered_per_m=scattered)
            self.skus[name] = sku
            self.sku_info[name] = info
        self.sku_by_index = [self.skus[n] for n in self.b['sku_names']]

    def retail_price(self, sku_name):
        prices = self.sku_info[sku_name]['prices']
        return q2(prices.get('RETAIL_PRICE_NON_TAX FILER') or max(prices.values()))

    def _channels(self):
        self.channels = {}
        for ctype, label in CHANNEL_DEFS:
            for filer in (Channel.NON_FILER, Channel.FILER):
                name = label + (' (Filer)' if filer == Channel.FILER else '')
                channel = Channel.objects.create(
                    name=name, channel_type=ctype, filer_status=filer, opened_on=datetime.date(2026, 1, 1),
                )
                self.channels[(ctype, filer)] = channel
                wholesale = ctype in (Channel.TYPE_WS, Channel.TYPE_VWS, Channel.TYPE_MANDI)
                for sku_name, sku in self.skus.items():
                    prices = self.sku_info[sku_name]['prices']
                    if wholesale:
                        price = prices.get('WHOLESALE_PRICE_NON_TAX_FILER') or self.retail_price(sku_name)
                    elif filer == Channel.FILER:
                        price = prices.get('RETAIL_PRICE_TAX FILER') or self.retail_price(sku_name)
                    else:
                        price = self.retail_price(sku_name)
                    ChannelPrice.objects.create(
                        channel=channel, sku=sku, price=q2(price), effective_from=self.month_start,
                        changed_by=self.owner,
                    )

    # -- DRs & staff -------------------------------------------------------------

    def _people(self):
        self.log('Loading DRs...')
        for grade in self.b['pay_grades']:
            PayGrade.objects.create(**grade)
        grades = {g.name: g for g in PayGrade.objects.all()}
        fso_profile = self.users['fso'].profile
        dr_group = self.groups[settings.ROLE_DR]
        self.drs = {}
        self.dr_meta = {}
        for dr in self.b['drs']:
            code = dr['code']
            user = User.objects.create(username=code.lower(), first_name=dr['name'], last_name='')
            user.set_unusable_password()
            user.save(update_fields=['password'])
            user.groups.add(dr_group)
            user.profile, _ = UserProfile.objects.update_or_create(
                user=user, defaults={'dr_code': code, 'warehouse': self.hq, 'supervisor': fso_profile},
            )
            grade = grades['VDD' if dr['area'] == 'RURAL' else 'DD']
            Employee.objects.create(
                employee_number=code, full_name=dr['name'], cnic=f"PENDING-{code.split('_')[-1]}",
                role=f'Distribution Representative ({grade.name})', warehouse=self.hq, user=user,
                pay_grade=grade, monthly_salary=grade.fixed, hire_date=datetime.date(2025, 1, 1),
            )
            self.drs[code] = user
            self.dr_meta[code] = dr
        self._fsos(grades)
        self.code_by_number = {d['number']: d['code'] for d in self.b['drs'] if d.get('number')}
        self.dr_by_number = {n: self.drs[c] for n, c in self.code_by_number.items()}

    def _fsos(self, grades):
        """FSO -> DR supervision as given by the distributor (17 Nov 2026)."""
        fso_group = self.groups[settings.ROLE_FSO]
        for fso_code, dr_codes in self.b.get('fsos', {}).items():
            short = fso_code.split('_')[-1]
            user = User.objects.create(username=fso_code.lower(), first_name=f'FSO {short[-2:]}', last_name='')
            user.set_unusable_password()
            user.save(update_fields=['password'])
            user.groups.add(fso_group)
            user.profile, _ = UserProfile.objects.update_or_create(
                user=user, defaults={'dr_code': fso_code, 'warehouse': self.hq},
            )
            Employee.objects.create(
                employee_number=fso_code, full_name=user.first_name, cnic=f'PENDING-{short}',
                role='Field Sales Officer', warehouse=self.hq, user=user, pay_grade=grades.get('FSO'),
                monthly_salary=grades['FSO'].fixed if 'FSO' in grades else 0, hire_date=datetime.date(2025, 1, 1),
            )
            UserProfile.objects.filter(dr_code__in=dr_codes).update(supervisor=user.profile)

    def _shops(self):
        self.log('Loading outlets...')
        rows = []
        for o in self.b['outlets']:
            filer = Channel.FILER if o['filer'] else Channel.NON_FILER
            rows.append(Shop(
                name=o['name'][:150] or f"Outlet {o['id']}",
                channel=self.channels[(o['channel'], filer)],
                address=o['address'], locality=o['area'].title(), bizom_outlet_id=o['id'],
                dr=self.drs.get(o['dr']), beat=o['beat'], visit_days=o['visit_days'], area_type=o['area'],
                latitude=Decimal(o['lat']).quantize(Decimal('0.0000001')) if o['lat'] else None,
                longitude=Decimal(o['lng']).quantize(Decimal('0.0000001')) if o['lng'] else None,
            ))
        Shop.objects.bulk_create(rows, batch_size=1000)
        self.shop_ids = dict(Shop.objects.values_list('bizom_outlet_id', 'id'))
        self.shop_channel = dict(Shop.objects.values_list('id', 'channel_id'))

    # -- company book (BIZOM) -------------------------------------------------

    def _company_book(self):
        self.log('Loading BIZOM invoices (company book)...')
        # (date, dr code, sku name) -> [M, value, ait]
        self.bizom = defaultdict(lambda: [D0, D0, D0])
        batch = []
        for order in self.b['orders']:
            batch.append(order)
            if len(batch) == 2000:
                self._insert_orders(batch)
                batch = []
        if batch:
            self._insert_orders(batch)

    def _insert_orders(self, orders):
        so_rows = []
        for order_id, invoice, outlet, dr_code, date, _pricelist, _lines in orders:
            day = datetime.date.fromisoformat(date)
            shop_id = self.shop_ids[outlet]
            so_rows.append(SalesOrder(
                so_number=f'BZ-{order_id}', ptc_reference_number=invoice[:50], shop_id=shop_id,
                channel_id=self.shop_channel[shop_id], warehouse=self.hq, dr=self.drs[dr_code],
                order_date=day, timestamp=aware(day, 12), status=SalesOrder.STATUS_CONFIRMED,
                source=SalesOrder.SOURCE_BIZOM_UPLOAD, created_by=self.owner,
            ))
        SalesOrder.objects.bulk_create(so_rows)
        ids = dict(SalesOrder.objects.filter(
            so_number__in=[r.so_number for r in so_rows]).values_list('so_number', 'id'))
        line_rows = []
        for order_id, _invoice, _outlet, dr_code, date, _pricelist, lines in orders:
            so_id = ids[f'BZ-{order_id}']
            for sku_idx, m, value, ait in lines:
                sku = self.sku_by_index[sku_idx]
                qty = q3(m)
                if qty <= 0:
                    continue
                line_rows.append(SalesOrderLine(
                    sales_order_id=so_id, sku=sku, quantity=qty, unit_price=q2(Decimal(str(value)) / qty),
                ))
                acc = self.bizom[(date, dr_code, sku.bizom_name)]
                acc[0] += Decimal(str(m))
                acc[1] += Decimal(str(value))
                acc[2] += Decimal(str(ait))
        SalesOrderLine.objects.bulk_create(line_rows, batch_size=2000)

    # -- actual book ---------------------------------------------------------------

    def _actual_book(self):
        self.log('Loading actual sales (actual book)...')
        actual = defaultdict(lambda: D0)  # (date, dr code, sku name, bucket) -> M
        for date, number, column_key, bucket, m in self.b['actual']:
            sku_name = column_key
            code = self.code_by_number.get(number)
            if not code:
                continue
            m = Decimal(str(m))
            for name, share in self._column_mix(date, code, sku_name):
                actual[(date, code, name, bucket)] += m * share
        on_sheet = defaultdict(lambda: D0)
        for (date, code, _s, _b), m in actual.items():
            on_sheet[code] += m
        # DRs with BIZOM sales but nothing on the actual sheet (shop sale
        # counter, SS/RTF routes): assume BIZOM is what physically sold.
        self.assumed_drs = set()
        for (date, code, sku_name), (m, value, _ait) in self.bizom.items():
            if on_sheet[code] == 0:
                self.assumed_drs.add(code)
                actual[(date, code, sku_name, ActualSale.BUCKET_RETAIL)] += m
        rows = []
        for (date, code, sku_name, bucket), m in actual.items():
            qty = q3(m)
            if qty == 0:
                continue
            bz = self.bizom.get((date, code, sku_name))
            if code in self.assumed_drs and bz and bz[0]:
                price = q2(bz[1] / bz[0])
            else:
                price = self.retail_price(sku_name)
            rows.append(ActualSale(
                date=datetime.date.fromisoformat(date), dr=self.drs[code], warehouse=self.hq,
                sku=self.skus[sku_name], bucket=bucket, quantity_m=qty, unit_price=price,
                source=ActualSale.SOURCE_BIZOM_ASSUMED if code in self.assumed_drs else ActualSale.SOURCE_SHEET,
            ))
        ActualSale.objects.bulk_create(rows, batch_size=2000)
        self.log(f'  {len(rows)} actual-sale rows; BIZOM assumed actual for: {", ".join(sorted(self.assumed_drs))}')

    def _column_mix(self, date, code, column_key):
        """
        Split one actual-sheet column (e.g. "Velo", "CI (+ Select)") across
        its SKUs the way that DR's BIZOM sales split that day; single-SKU
        columns pass straight through.
        """
        column = COLUMN_BY_KEY[column_key]
        if not hasattr(self, '_bizom_by_day_dr'):
            # Built once: scanning every BIZOM row per call is far too slow on a small server.
            self._bizom_by_day_dr = defaultdict(list)
            for (d, c, name), (m, _v, _a) in self.bizom.items():
                if m > 0:
                    self._bizom_by_day_dr[(d, c)].append((name, m))
        mix = [(name, m) for name, m in self._bizom_by_day_dr.get((date, code), [])
               if column_matches(column, name, self.skus[name].category)]
        total = sum((m for _n, m in mix), D0)
        if not total:
            return [(default_sku_name(column), Decimal('1'))]
        return [(name, m / total) for name, m in mix]

    # -- stock ---------------------------------------------------------------------

    def _stock(self):
        self.log('Building stock ledger...')
        bizom_by_sku_day = defaultdict(lambda: D0)
        for (date, _code, sku_name), (m, _v, _a) in self.bizom.items():
            bizom_by_sku_day[(sku_name, datetime.date.fromisoformat(date))] += m
        month_bizom = defaultdict(lambda: D0)
        for (sku_name, _day), m in bizom_by_sku_day.items():
            month_bizom[sku_name] += m

        ledger = []
        opening_value = D0
        for sku_name, sku in self.skus.items():
            opening = q3(month_bizom[sku_name] / 3 + 1)  # ~10 days of cover, seeded
            opening_value += opening * sku.current_cost_price
            ledger.append(StockLedgerEntry(
                warehouse=self.hq, sku=sku, entry_type=StockLedgerEntry.OPENING_BALANCE,
                quantity_change=opening, reference='OPENING-SEEDED', notes=SEED_NOTE,
                created_by=self.owner, created_at=aware(self.month_start, 6),
            ))
            for code in ('BHLWAL', 'BHERA'):
                branch_qty = q3(opening * Decimal('0.08'))
                opening_value += branch_qty * sku.current_cost_price
                ledger.append(StockLedgerEntry(
                    warehouse=self.warehouses[code], sku=sku, entry_type=StockLedgerEntry.OPENING_BALANCE,
                    quantity_change=branch_qty, reference='OPENING-SEEDED', notes=SEED_NOTE,
                    created_by=self.owner, created_at=aware(self.month_start, 6),
                ))
        self.opening_value = opening_value

        # Physical dispatch follows the actual book.
        dispatch = defaultdict(lambda: D0)
        for row in ActualSale.objects.select_related('dr__profile').values(
                'date', 'dr__profile__dr_code', 'sku_id', 'quantity_m'):
            dispatch[(row['date'], row['dr__profile__dr_code'], row['sku_id'])] += row['quantity_m']
        sku_by_id = {s.id: s for s in self.skus.values()}
        for (day, code, sku_id), qty in dispatch.items():
            ledger.append(StockLedgerEntry(
                warehouse=self.hq, sku=sku_by_id[sku_id], entry_type=StockLedgerEntry.SALE_OUT,
                quantity_change=-qty, reference=f'ACT-{code}-{day:%Y%m%d}',
                created_by=self.owner, created_at=aware(day, 19),
            ))
        StockLedgerEntry.objects.bulk_create(ledger, batch_size=2000)

        # Weekly PTC lifting, sized to BIZOM (company) volume — PTC primaries
        # track secondaries. Seeded until the real PTC invoices are shared.
        self.log('Seeding weekly PTC purchase orders...')
        ptc = Party.objects.create(name='Pakistan Tobacco Company (PTC)', party_type=Party.SUPPLIER,
                                   address='PTC, Sargodha territory')
        self.ptc = ptc
        self.pos = []
        by_sku_days = defaultdict(list)
        for (sku_name, day), m in bizom_by_sku_day.items():
            by_sku_days[sku_name].append((day, m))
        week_start = self.month_start
        n = 1
        while week_start <= self.month_end:
            week_end = min(week_start + datetime.timedelta(days=6), self.month_end)
            po = PurchaseOrder.objects.create(
                po_number=f'PO-{week_start.year}-{n:05d}', ptc_reference_number=f'PTC-SEEDED-{n:03d}',
                warehouse=self.hq, supplier=ptc, order_date=week_start, created_by=self.owner,
                notes='Seeded: weekly lifting sized to BIZOM volume',
            )
            for sku_name, sku in self.skus.items():
                qty = sum((m for d, m in by_sku_days.get(sku_name, ())
                           if week_start <= d <= week_end), D0)
                if qty > 0:
                    PurchaseOrderLine.objects.create(
                        purchase_order=po, sku=sku, quantity=q3(qty), unit_cost=sku.current_cost_price,
                    )
            po.submit()
            po.receive(self.owner)
            when = aware(week_start, 8)
            StockLedgerEntry.objects.filter(reference=po.po_number).update(created_at=when)
            JournalEntry.objects.filter(reference=po.po_number).update(date=week_start)
            PurchaseOrder.objects.filter(pk=po.pk).update(received_at=when)
            self.pos.append(po)
            week_start = week_end + datetime.timedelta(days=1)
            n += 1

        # Move what BIZOM invoiced but DRs didn't physically sell (Madam
        # Banam) into its own godown, as the warehouse manager asked.
        on_sheet_codes = {c for c in self.drs if c not in self.assumed_drs}
        banam_qty = defaultdict(lambda: D0)
        for (date, code, sku_name), (m, _v, _a) in self.bizom.items():
            if code in on_sheet_codes:
                banam_qty[sku_name] += m
        for row in ActualSale.objects.filter(source=ActualSale.SOURCE_SHEET).values('sku__bizom_name', 'quantity_m'):
            banam_qty[row['sku__bizom_name']] -= row['quantity_m']
        StockLevel.rebuild_from_ledger()
        levels = dict(StockLevel.objects.filter(warehouse=self.hq).values_list('sku_id', 'quantity'))
        transfer = StockTransfer.objects.create(
            transfer_number=f'TR-{self.month_end.year}-00001', from_warehouse=self.hq,
            to_warehouse=self.warehouses['SGD-ADJ'], created_by=self.owner,
        )
        for sku_name, qty in banam_qty.items():
            sku = self.skus[sku_name]
            qty = q3(min(qty, levels.get(sku.id, D0)))
            if qty > 0:
                StockTransferLine.objects.create(transfer=transfer, sku=sku, quantity=qty)
        transfer.dispatch(self.owner)
        transfer.receive(self.owner)
        when = aware(self.month_end, 21)
        StockLedgerEntry.objects.filter(reference=transfer.transfer_number).update(created_at=when)
        StockTransfer.objects.filter(pk=transfer.pk).update(dispatched_at=when, received_at=when)

        # Safety stock: ~3 days of actual sales at HQ.
        actual_month = defaultdict(lambda: D0)
        for sku_id, qty in dispatch_by_sku(dispatch).items():
            actual_month[sku_id] = qty
        days = Decimal((self.month_end - self.month_start).days + 1)
        for sku in self.skus.values():
            minimum = q3(actual_month.get(sku.id, D0) / days * 3)
            if minimum > 0:
                SafetyStockLevel.objects.create(warehouse=self.hq, sku=sku, minimum_quantity=minimum)

    # -- accounting ------------------------------------------------------------------

    def _accounting(self):
        self.log('Posting accounts (actual book)...')
        purchases = sum((po.total_value for po in self.pos), D0)
        bank_opening = q2(purchases * Decimal('0.6'))
        JournalEntry.create_posted(
            source=JournalEntry.SOURCE_OPENING_BALANCE, date=self.month_start, reference='OPENING-SEEDED',
            narration='Opening balances (seeded: replace with real figures for the switch-over date)',
            lines=[
                {'account': ChartOfAccount.INVENTORY, 'debit': q2(self.opening_value)},
                {'account': ChartOfAccount.BANK, 'debit': bank_opening},
                {'account': ChartOfAccount.OWNER_EQUITY, 'credit': q2(self.opening_value) + bank_opening},
            ],
            created_by=self.owner,
        )
        for po in self.pos:
            value = q2(po.total_value)
            JournalEntry.create_posted(
                source=JournalEntry.SOURCE_VOUCHER, date=po.order_date, reference=po.po_number,
                narration=f'Payment to PTC against {po.po_number} (seeded)',
                lines=[
                    {'account': ChartOfAccount.ACCOUNTS_PAYABLE, 'debit': value, 'party': self.ptc},
                    {'account': ChartOfAccount.BANK, 'credit': value},
                ],
                created_by=self.owner,
            )

        # One sale entry per DR per day, valued at the actual book.
        self.actual_value = defaultdict(lambda: D0)       # (date, code, sku) -> value
        per_day = defaultdict(lambda: [D0, D0])            # (date, code) -> [value, cost]
        for row in ActualSale.objects.values('date', 'dr__profile__dr_code', 'sku__bizom_name',
                                             'quantity_m', 'unit_price', 'sku__current_cost_price'):
            key = (row['date'], row['dr__profile__dr_code'])
            value = row['quantity_m'] * row['unit_price']
            per_day[key][0] += value
            per_day[key][1] += row['quantity_m'] * row['sku__current_cost_price']
            self.actual_value[(row['date'], row['dr__profile__dr_code'], row['sku__bizom_name'])] += value
        for (day, code), (value, cost) in sorted(per_day.items()):
            user = self.drs[code]
            value, cost = q2(value), q2(cost)
            if code in self.assumed_drs:
                first = {'account': ChartOfAccount.CASH, 'debit': value}
            else:
                first = {'account': ChartOfAccount.ACCOUNTS_RECEIVABLE, 'debit': value, 'party': dr_party_for(user)}
            lines = [first, {'account': ChartOfAccount.SALES_REVENUE, 'credit': value}]
            if cost:
                lines += [
                    {'account': ChartOfAccount.COST_OF_GOODS_SOLD, 'debit': cost},
                    {'account': ChartOfAccount.INVENTORY, 'credit': cost},
                ]
            if value < 0:
                # Net return day on the actual sheet: post it as a reversal.
                lines = [{**line, 'debit': -line.get('credit', D0), 'credit': -line.get('debit', D0)}
                         for line in lines]
            JournalEntry.create_posted(
                source=JournalEntry.SOURCE_SALE_RETURN if value < 0 else JournalEntry.SOURCE_SALE,
                date=day, reference=f'ACT-{code}-{day:%Y%m%d}',
                narration=f'Actual sales: {user.first_name}', lines=lines, created_by=self.owner,
            )

        # Running costs from the Expences sheet's shape (seeded amounts).
        fuel = q2(Decimal('6000') * len([c for c in self.drs if c not in self.assumed_drs]))
        for narration, amount in [
            ('DR fuel & vehicle running (seeded)', fuel),
            ('Godown rent incl. adjusted-stock house (seeded)', Decimal('120000')),
            ('Electricity, phones & office (seeded)', Decimal('65000')),
            ('Vehicle repair & maintenance (seeded)', Decimal('48000')),
        ]:
            JournalEntry.create_posted(
                source=JournalEntry.SOURCE_VOUCHER, date=self.month_end, reference='EXP-SEEDED',
                narration=narration, created_by=self.owner,
                lines=[
                    {'account': ChartOfAccount.GENERAL_EXPENSE, 'debit': amount},
                    {'account': ChartOfAccount.CASH, 'credit': amount},
                ],
            )

    # -- DR cash settlements ---------------------------------------------------------

    def _settlements(self):
        self.log('Building DR cash settlements...')
        days = defaultdict(set)
        for (day, code, _s) in self.actual_value:
            days[code].add(day)
        for (date, code, _s) in self.bizom:
            days[code].add(datetime.date.fromisoformat(date))
        for code, dr_days in sorted(days.items()):
            if code in self.assumed_drs:
                continue
            user = self.drs[code]
            for day in sorted(dr_days):
                # Netted per category, as the slip carries one FMC and one NC line.
                company = {SKU.CATEGORY_FMC: D0, SKU.CATEGORY_NC: D0}
                actual = {SKU.CATEGORY_FMC: D0, SKU.CATEGORY_NC: D0}
                for sku_name, sku in self.skus.items():
                    category = sku.category
                    bz = self.bizom.get((day.isoformat(), code, sku_name))
                    company[category] += bz[1] if bz else D0
                    actual[category] += self.actual_value.get((day, code, sku_name), D0)
                gaps = {c: company[c] - actual[c] for c in company}
                total_sale = q2(sum(company.values(), D0))
                banam_fmc = q2(max(gaps[SKU.CATEGORY_FMC], D0))
                banam_nc = q2(max(gaps[SKU.CATEGORY_NC], D0))
                wasooli = q2(sum((-g for g in gaps.values() if g < 0), D0))
                if total_sale == 0 and wasooli == 0:
                    continue
                fbr = q2(total_sale * Decimal('0.005'))   # matches the sample slip (~0.5%)
                due = total_sale - banam_fmc - banam_nc + wasooli - fbr
                if due < 0:
                    # Nothing physically sold that day (all Banam): no cash to withhold FBR from.
                    fbr, due = D0, total_sale - banam_fmc - banam_nc + wasooli
                roll = self.rng.random()
                short = D0 if roll < 0.7 else Decimal(self.rng.choice([3, 10, 50, 120, 500, 1500]))
                handed = max(due - short, D0)
                credit = q2(handed * Decimal(self.rng.uniform(0.05, 0.15)))
                bank = (handed * Decimal(self.rng.uniform(0.2, 0.5)) / 1000).quantize(Decimal('1')) * 1000
                cash = handed - credit - bank
                notes, remainder = {}, int(cash)
                for denom in DRSettlement.NOTE_DENOMINATIONS:
                    notes[denom], remainder = divmod(remainder, denom)
                credit = q2(credit + remainder + (cash - int(cash)))  # coins & paisa ride on credit
                settlement = DRSettlement.objects.create(
                    date=day, dr=user, warehouse=self.hq, total_sale=total_sale, fbr=fbr,
                    madam_banam_fmc=banam_fmc, madam_banam_nc=banam_nc, madam_wasooli=wasooli,
                    bank_transfer_1=bank, market_credit=credit, created_by=self.owner,
                    remarks='Seeded split of cash/bank/credit; sale and adjustments from BIZOM vs actual sheet',
                    **{f'notes_{d}': c for d, c in notes.items()},
                )
                settlement.post_to_ledger(user=self.owner)

        # Cash is banked daily (seeded): move each day's cash takings to Bank.
        # A float of Rs 100,000 a day stays in the till for salaries and petty expenses.
        cash_in = (
            JournalLine.objects.filter(account__code=ChartOfAccount.CASH, debit__gt=0,
                                       entry__date__gte=self.month_start, entry__date__lte=self.month_end)
            .values('entry__date').annotate(total=models_sum('debit'))
        )
        float_kept = Decimal('100000')
        for row in cash_in:
            deposit = q2(row['total']) - float_kept
            if deposit <= 0:
                continue
            JournalEntry.create_posted(
                source=JournalEntry.SOURCE_VOUCHER, date=row['entry__date'], reference='DEPOSIT-SEEDED',
                narration='Cash deposited to bank (seeded)', created_by=self.owner,
                lines=[
                    {'account': ChartOfAccount.BANK, 'debit': deposit},
                    {'account': ChartOfAccount.CASH, 'credit': deposit},
                ],
            )

        for sample in self.b.get('sample_settlements', []):
            user = self.dr_by_number.get(sample['dr_number'])
            if not user:
                continue
            transfers = sample.get('bank_transfers', []) + [0, 0, 0]
            DRSettlement.objects.create(
                date=datetime.date.fromisoformat(sample['date']), dr=user, warehouse=self.hq,
                total_sale=sample['total_sale'], fbr=sample['fbr'],
                scattered_wholesale=sample.get('scattered_wholesale', 0),
                madam_banam_fmc=sample['madam_banam_fmc'], madam_banam_nc=sample['madam_banam_nc'],
                madam_wasooli=sample.get('madam_wasooli', 0),
                bank_transfer_1=transfers[0], bank_transfer_2=transfers[1], bank_transfer_3=transfers[2],
                expense=sample.get('expense', 0), market_credit=sample.get('market_credit', 0),
                remarks="Real slip shared by Mumtaz & Co (not posted: that day's sales aren't loaded)",
                created_by=self.owner,
                **{f'notes_{d}': sample['notes'].get(str(d), 0) for d in DRSettlement.NOTE_DENOMINATIONS},
            )

    # -- payroll -----------------------------------------------------------------------

    def _payroll(self):
        self.log('Computing September payroll & targets...')
        from reports.payout import dr_payout_rows

        dd_channel = self.channels[(Channel.TYPE_DD, Channel.NON_FILER)]
        actual_m = defaultdict(lambda: D0)
        for row in ActualSale.objects.filter(source=ActualSale.SOURCE_SHEET).values('dr_id', 'quantity_m'):
            actual_m[row['dr_id']] += row['quantity_m']
        for user_id, m in actual_m.items():
            if m <= 0:
                continue
            target = (m * Decimal(self.rng.uniform(0.92, 1.12))).quantize(Decimal('1'))
            SalesTarget.objects.create(
                dr_id=user_id, channel=dd_channel, year=self.month_start.year,
                month=self.month_start.month, target_volume_m=target,
            )
        paid_on = self.month_end
        for row in dr_payout_rows(self.month_start.year, self.month_start.month):
            if row['actual_m'] <= 0 or row['employee_id'] is None:
                continue
            payment = SalaryPayment.objects.create(
                employee_id=row['employee_id'], year=self.month_start.year, month=self.month_start.month,
                salary_paid=row['salary_total'], commission_amount=row['commission'], paid_on=paid_on,
            )
            payment.post_to_ledger(user=self.owner)


def dispatch_by_sku(dispatch):
    totals = defaultdict(lambda: D0)
    for (_day, _code, sku_id), qty in dispatch.items():
        totals[sku_id] += qty
    return totals


def client_data_loaded():
    return Shop.objects.exclude(bizom_outlet_id='').exists()
