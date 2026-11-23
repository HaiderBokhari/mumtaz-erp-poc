"""
Daily actual-sale entry, in the same shape as Mumtaz & Co's "ACTUAL SALE"
sheet: one row per DR, one column per sheet brand, a retail block and a
scattered-wholesale block, in M's. the KPO keys it in daily; it drives
DR commission and the actual book (stock + revenue).

The sheet tracks brands, not every BIZOM SKU, so each column covers one or
more SKUs. Column meanings confirmed by the distributor (17 Nov 2026):
the header "B&H" is Velo Nano, "CI" is Capstan International *and* Capstan
Select (same commission), and CbPM Q2 LEP is counted under CbPMO.

Saving is append-only like the rest of the ledger: changes to a day post
delta stock movements and a delta journal entry, never edits to old ones.
"""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction

from accounting.models import ChartOfAccount, JournalEntry
from catalog.models import SKU, Channel, ChannelPrice
from warehouses.models import StockLedgerEntry, Warehouse

from .models import ActualSale, DRIssuance, dr_party_for

D0 = Decimal('0')

# key, label (as on their sheet), SKUs by BIZOM name, or a match rule.
SHEET_COLUMNS = [
    {'key': 'BH', 'label': 'B&H', 'skus': ['Benson & Hedges 20HL - New']},
    {'key': 'NANO', 'label': 'Velo Nano', 'match': 'velo_nano', 'default': 'VELO Polar Mint 6MG - Nano - 15s'},
    {'key': 'DHL', 'label': 'DHL', 'skus': ['Dunhill Lights 20HL']},
    {'key': 'DHS', 'label': 'DH Switch', 'skus': ['Dunhill Switch 20HL']},
    {'key': 'JPGL', 'label': 'JPGL', 'skus': ['Gold Leaf Classic 20HL']},
    {'key': 'JPGLSP', 'label': 'JPGL Sp.', 'skus': ['Dunhill Special 20HL']},
    {'key': 'JP', 'label': 'JP', 'skus': ['John Player 20HL Poly Pack']},
    {'key': 'CF', 'label': 'Capstan Filter', 'skus': ['Capstan Filter 20HL']},
    {'key': 'VELO', 'label': 'Velo', 'match': 'velo_other', 'default': 'VELO Polar Mint 10MG'},
    {'key': 'GF', 'label': 'Gold Flake', 'skus': ['Gold Flake by Rothmans 20HL']},
    {'key': 'CBPM', 'label': 'CbPMO', 'skus': ['Capstan by Pall Mall 20HL', 'Capstan by Pall Mall Q2 LEP 20HL']},
    {'key': 'CI', 'label': 'CI (+ Select)', 'skus': ['Capstan International 20HL', 'Capstan Select 20HL']},
    {'key': 'EMB', 'label': 'Embassy', 'skus': ['Embassy Filter 20HL']},
]
COLUMN_BY_KEY = {c['key']: c for c in SHEET_COLUMNS}
BUCKETS = [ActualSale.BUCKET_RETAIL, ActualSale.BUCKET_SCATTERED]


def column_matches(column, name, category):
    """Whether a SKU (by BIZOM name and category) belongs to a sheet column."""
    if 'skus' in column:
        return name in column['skus']
    is_nano = 'nano' in name.lower()
    if column['match'] == 'velo_nano':
        return category == SKU.CATEGORY_NC and is_nano
    return category == SKU.CATEGORY_NC and not is_nano


def column_for_sku(sku):
    for column in SHEET_COLUMNS:
        if column_matches(column, sku.bizom_name or sku.name, sku.category):
            return column['key']
    return None


def default_sku_name(column):
    return column.get('default') or column['skus'][0]


def q3(value):
    return Decimal(value).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)


def q2(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _drs():
    return (
        # Discontinued BIZOM devices (DR05/13/29, 23 Nov 2026) are made inactive.
        User.objects.filter(groups__name=settings.ROLE_DR, is_active=True)
        .select_related('profile').order_by('profile__dr_code')
    )


def _retail_channel():
    return Channel.objects.filter(
        channel_type=Channel.TYPE_DD, filer_status=Channel.NON_FILER).order_by('id').first()


def column_prices(day):
    """Rs per M for each sheet column: the BIZOM retail (DD, non-filer) price of its main SKU."""
    channel = _retail_channel()
    skus = {s.bizom_name or s.name: s for s in SKU.objects.all()}
    prices = {}
    for column in SHEET_COLUMNS:
        sku = skus.get(default_sku_name(column))
        if sku is None:
            continue
        price = (ChannelPrice.current_price(channel.id, sku.id, day) if channel else None) or sku.current_cost_price
        prices[column['key']] = str(price)
    return prices


def day_grid(day):
    """The sheet for one day: DR rows x column values, per bucket."""
    values = defaultdict(lambda: {b: defaultdict(lambda: D0) for b in BUCKETS})
    for sale in ActualSale.objects.filter(date=day).select_related('sku'):
        key = column_for_sku(sale.sku)
        if key:
            values[sale.dr_id][sale.bucket][key] += sale.quantity_m
    issuance = defaultdict(dict)
    for row in DRIssuance.objects.filter(date=day):
        issuance[str(row.dr_id)][row.column] = [str(row.issued_m), str(row.returned_m)]
    return {
        'date': day.isoformat(),
        'columns': [{'key': c['key'], 'label': c['label']} for c in SHEET_COLUMNS],
        'prices': column_prices(day),
        'issuance': issuance,
        'drs': [
            {'id': u.id, 'code': u.profile.dr_code, 'name': u.first_name or u.username}
            for u in _drs()
        ],
        'values': {
            str(dr_id): {b: {k: str(v) for k, v in cols.items()} for b, cols in buckets.items()}
            for dr_id, buckets in values.items()
        },
    }


@transaction.atomic
def save_day(day, grid, user):
    """
    Apply a day's sheet. ``grid`` is {dr_id: {bucket: {column_key: M}}};
    columns left out are unchanged. Returns a short summary.
    """
    skus = {s.bizom_name or s.name: s for s in SKU.objects.all()}
    retail_channel = _retail_channel()
    hq = Warehouse.objects.filter(is_head_office=True).first()
    changed_rows = 0
    drs_touched = 0

    for dr_id, buckets in grid.items():
        dr = User.objects.select_related('profile').get(pk=int(dr_id), groups__name=settings.ROLE_DR)
        warehouse = dr.profile.warehouse or hq
        stock_delta = defaultdict(lambda: D0)   # sku_id -> M
        value_delta = cost_delta = D0
        for bucket, columns in buckets.items():
            if bucket not in BUCKETS:
                continue
            existing = {
                row.sku_id: row for row in ActualSale.objects.filter(date=day, dr=dr, bucket=bucket).select_related('sku')
            }
            for key, raw in columns.items():
                column = COLUMN_BY_KEY.get(key)
                if column is None:
                    continue
                target = q3(raw or 0)
                rows = [r for r in existing.values() if column_for_sku(r.sku) == key]
                current = sum((r.quantity_m for r in rows), D0)
                if target == current:
                    continue
                # Keep the existing variant mix (e.g. Velo flavours) when rescaling;
                # a new entry goes to the column's main SKU.
                if current and rows:
                    new_qty = {r.sku_id: q3(r.quantity_m / current * target) for r in rows}
                    drift = target - sum(new_qty.values(), D0)
                    new_qty[rows[0].sku_id] += drift
                    sku_by_id = {r.sku_id: r.sku for r in rows}
                else:
                    sku = skus[default_sku_name(column)]
                    new_qty = {sku.id: target}
                    sku_by_id = {sku.id: sku}
                for sku_id, qty in new_qty.items():
                    row = existing.get(sku_id)
                    old = row.quantity_m if row else D0
                    sku = sku_by_id[sku_id]
                    if row:
                        price = row.unit_price
                        if qty == 0:
                            row.delete()
                        else:
                            row.quantity_m = qty
                            row.save(update_fields=['quantity_m'])
                    elif qty != 0:
                        price = (ChannelPrice.current_price(retail_channel.id, sku.id, day)
                                 if retail_channel else None) or sku.current_cost_price
                        ActualSale.objects.create(
                            date=day, dr=dr, warehouse=warehouse, sku=sku, bucket=bucket,
                            quantity_m=qty, unit_price=price, source=ActualSale.SOURCE_MANUAL,
                        )
                    else:
                        continue
                    delta = qty - old
                    stock_delta[sku_id] += delta
                    value_delta += delta * price
                    cost_delta += delta * sku.current_cost_price
                    changed_rows += 1

        if not stock_delta:
            continue
        drs_touched += 1
        reference = f'ACT-{dr.profile.dr_code}-{day:%Y%m%d}'
        for sku_id, delta in stock_delta.items():
            if delta == 0:
                continue
            StockLedgerEntry.objects.create(
                warehouse=warehouse, sku_id=sku_id,
                entry_type=StockLedgerEntry.SALE_OUT if delta > 0 else StockLedgerEntry.SALE_RETURN_IN,
                quantity_change=-delta, reference=reference, created_by=user,
                notes='Daily sales entry',
            )
        _post_value_delta(dr, day, q2(value_delta), q2(cost_delta), reference, user)

    return {'rows_changed': changed_rows, 'drs_updated': drs_touched}


@transaction.atomic
def save_issuance(day, values, user):
    """
    Apply the ISSUANCE / RETURN sheet: ``values`` is
    {dr_id: {column_key: {"issued": M, "returned": M}}}; either side may be
    left out to keep what was saved. Each DR's sale (issued - returned) is
    then saved as their retail sale for the day, so stock, accounts and
    commission follow exactly as for the plain sales entry.
    """
    retail = {}
    for dr_id, columns in values.items():
        dr = User.objects.get(pk=int(dr_id), groups__name=settings.ROLE_DR)
        for key, sides in columns.items():
            if key not in COLUMN_BY_KEY:
                continue
            row, _ = DRIssuance.objects.get_or_create(date=day, dr=dr, column=key)
            if 'issued' in sides:
                row.issued_m = q3(sides['issued'] or 0)
            if 'returned' in sides:
                row.returned_m = q3(sides['returned'] or 0)
            row.updated_by = user
            row.save()
            retail.setdefault(str(dr.id), {ActualSale.BUCKET_RETAIL: {}})
            retail[str(dr.id)][ActualSale.BUCKET_RETAIL][key] = str(row.sale_m)
    return save_day(day, retail, user)


def _post_value_delta(dr, day, value, cost, reference, user):
    """Revenue for the change only (append-only): a sale for an increase, a reversal for a decrease."""
    if not value and not cost:
        return
    reversal = value < 0 or (value == 0 and cost < 0)
    value, cost = abs(value), abs(cost)
    lines = [
        {'account': ChartOfAccount.ACCOUNTS_RECEIVABLE, 'debit': value, 'party': dr_party_for(dr)},
        {'account': ChartOfAccount.SALES_REVENUE, 'credit': value},
    ]
    if cost > 0:
        lines += [
            {'account': ChartOfAccount.COST_OF_GOODS_SOLD, 'debit': cost},
            {'account': ChartOfAccount.INVENTORY, 'credit': cost},
        ]
    if reversal:
        lines = [{**line, 'debit': line.get('credit', D0), 'credit': line.get('debit', D0)} for line in lines]
    JournalEntry.create_posted(
        source=JournalEntry.SOURCE_SALE_RETURN if reversal else JournalEntry.SOURCE_SALE,
        date=day, reference=reference, narration=f'Daily sales entry: {dr.first_name}',
        lines=lines, created_by=user,
    )
