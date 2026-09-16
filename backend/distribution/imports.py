"""
Upload PTC sales data (requirement doc, Distribution #4):

    "Upload PTC sales data obtained from the PTC systems (Mobile App or
    SAP)... only if the file to be uploaded is in Excel/csv format and
    complies with the fixed column structure as defined in the template
    which will be provided along with the system."

This module *is* that fixed template — see ``TEMPLATE_COLUMNS`` — plus the
parser that turns an uploaded .csv/.xlsx into confirmed SalesOrders. Real
PTC/BIZOM exports won't match this exactly; the intent for the POC is to
demonstrate the upload -> validate -> post-to-stock pipeline so the mapping
step can be adjusted once a real sample file is available (questionnaire
answer #23: "Daily PTC sales files data is uploaded").
"""
import csv
import io

from django.contrib.auth.models import User
from django.db import transaction

from catalog.models import Channel, SKU
from warehouses.models import Warehouse

from .models import SalesOrder, SalesOrderLine, Shop

TEMPLATE_COLUMNS = [
    'order_date',        # YYYY-MM-DD
    'ptc_reference_number',
    'dr_code',            # matches UserProfile.dr_code, e.g. SGD_SGD_DR01
    'channel_type',       # DD / VDD / WS / VWS / MANDI
    'filer_status',       # FILER / NON_FILER
    'warehouse_code',
    'shop_name',
    'sku_code',
    'quantity',
    'unit_price',
]


def _read_rows(file_obj, filename):
    if filename.lower().endswith('.csv'):
        text = io.TextIOWrapper(file_obj, encoding='utf-8-sig')
        reader = csv.DictReader(text)
        return [row for row in reader]

    if filename.lower().endswith(('.xlsx', '.xlsm')):
        import openpyxl

        wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else '' for h in next(rows_iter)]
        rows = []
        for values in rows_iter:
            if all(v is None for v in values):
                continue
            rows.append(dict(zip(header, values)))
        return rows

    raise ValueError('Only .csv and .xlsx files are accepted.')


def import_ptc_sales_file(file_obj, filename, user):
    rows = _read_rows(file_obj, filename)

    missing_cols = [c for c in TEMPLATE_COLUMNS if c not in (rows[0].keys() if rows else TEMPLATE_COLUMNS)]
    if rows and missing_cols:
        return {'orders_created': 0, 'rows_processed': 0, 'errors': [
            f'File is missing required column(s): {", ".join(missing_cols)}'
        ]}

    # Group rows into one SalesOrder per (ptc_reference_number, dr_code, shop_name, order_date)
    groups = {}
    order = []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        key = (
            str(row.get('ptc_reference_number') or '').strip(),
            str(row.get('dr_code') or '').strip(),
            str(row.get('shop_name') or '').strip(),
            str(row.get('order_date') or '').strip(),
        )
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((i, row))

    errors = []
    orders_created = 0
    rows_processed = 0

    for key in order:
        group_rows = groups[key]
        try:
            with transaction.atomic():
                so = _create_order_for_group(group_rows, user)
                so.confirm(user=user)
            orders_created += 1
            rows_processed += len(group_rows)
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller, not swallowed
            first_line = group_rows[0][0]
            errors.append(f'Row {first_line} ({key[0] or "no PTC ref"}): {exc}')

    return {'orders_created': orders_created, 'rows_processed': rows_processed, 'errors': errors}


def _create_order_for_group(group_rows, user):
    first_line, first_row = group_rows[0]

    dr_code = str(first_row.get('dr_code') or '').strip()
    dr_user = User.objects.filter(profile__dr_code=dr_code).first()
    if not dr_user:
        raise ValueError(f'No DR found with dr_code "{dr_code}"')

    channel_type = str(first_row.get('channel_type') or '').strip().upper()
    filer_status = str(first_row.get('filer_status') or Channel.NON_FILER).strip().upper()
    channel = Channel.objects.filter(channel_type=channel_type, filer_status=filer_status).first()
    if not channel:
        raise ValueError(f'No channel found for type "{channel_type}" / {filer_status}')

    warehouse_code = str(first_row.get('warehouse_code') or '').strip()
    warehouse = Warehouse.objects.filter(code=warehouse_code).first()
    if not warehouse:
        raise ValueError(f'No warehouse found with code "{warehouse_code}"')

    shop_name = str(first_row.get('shop_name') or '').strip()
    shop, _ = Shop.objects.get_or_create(name=shop_name, channel=channel)

    ptc_reference_number = str(first_row.get('ptc_reference_number') or '').strip()
    order_date = str(first_row.get('order_date') or '').strip() or None

    so_number = f'SO-UPLOAD-{ptc_reference_number or SalesOrder.objects.count() + 1}-{first_line}'
    so = SalesOrder.objects.create(
        so_number=so_number,
        ptc_reference_number=ptc_reference_number,
        shop=shop, channel=channel, warehouse=warehouse, dr=dr_user,
        order_date=order_date or None,
        source=SalesOrder.SOURCE_BIZOM_UPLOAD,
        created_by=user,
    )

    for line_no, row in group_rows:
        sku_code = str(row.get('sku_code') or '').strip()
        sku = SKU.objects.filter(code=sku_code).first()
        if not sku:
            raise ValueError(f'Row {line_no}: no SKU found with code "{sku_code}"')
        SalesOrderLine.objects.create(
            sales_order=so, sku=sku,
            quantity=row.get('quantity') or 0,
            unit_price=row.get('unit_price') or 0,
        )

    return so
