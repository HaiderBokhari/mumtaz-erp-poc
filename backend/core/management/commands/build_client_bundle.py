"""
Turn the files Mumtaz & Co shared (BIZOM exports, their FMC/NC price list,
their daily "ACTUAL SALE" workbook) into one compact JSON bundle that
``load_client_bundle`` (or the owner-only upload endpoint) can load.

The bundle holds real business data, so it is written to the git-ignored
``client_data/`` folder and never committed. Only what the ERP needs is
kept: no CNIC/NTN or phone numbers, just the filer flag they imply.

Usage:
    python manage.py build_client_bundle \
        --source "../artifacts/mumtaz and co response " \
        --manual ../client_data/manual_inputs.json \
        --out ../client_data/bundle.json.gz
"""
import csv
import glob
import gzip
import io
import json
import os
import re
import zipfile
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from distribution.actual_entry import SHEET_COLUMNS

# Columns of the distributor's ACTUAL SALE sheet, left to right, as sheet
# column keys (see distribution.actual_entry.SHEET_COLUMNS for what each
# covers); the loader splits multi-SKU columns by that day's BIZOM mix.
ACTUAL_SHEET_COLUMNS = [c['key'] for c in SHEET_COLUMNS]

# BIZOM SKU name fragments -> (brand, variant) for the catalogue.
BRAND_RULES = [
    ('dunhill', 'Dunhill'), ('benson', 'Benson & Hedges'), ('gold leaf', 'Gold Leaf'),
    ('john player', 'John Player'), ('capstan by pall mall', 'Capstan by Pall Mall'),
    ('capstan', 'Capstan'), ('gold flake', 'Gold Flake'), ('embassy', 'Embassy'),
    ('cbpm', 'Capstan by Pall Mall'), ('lucky strike', 'Lucky Strike'), ('velo', 'VELO'),
]

PTC_RATE_ALIASES = {
    # FMC AND NC.xlsx spells a few names differently from BIZOM.
    'cbpm elite': 'cbpmo ellite',
    # Limited-edition pack of CbPM, same rate (distributor, 17 Nov 2026).
    'capstan by pall mall q2 lep 20hl': 'capstan by pall mall 20hl',
}


def norm(text):
    return re.sub(r'[^a-z0-9]+', ' ', str(text).lower()).strip()


def brand_for(name):
    low = name.lower()
    for fragment, brand in BRAND_RULES:
        if fragment in low:
            return brand
    return name.split()[0].title()


def velo_mg(name):
    match = re.search(r'(\d+)\s*mg', name.lower())
    return match.group(1) if match else None


class Command(BaseCommand):
    help = "Build a loadable data bundle from Mumtaz & Co's BIZOM exports and sheets."

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True, help='Folder with the files the distributor shared.')
        parser.add_argument('--manual', required=True, help='manual_inputs.json (commission, pay, sample slips).')
        parser.add_argument('--out', required=True, help='Output .json.gz path (keep it git-ignored).')

    def handle(self, *args, **opts):
        try:
            import openpyxl
        except ImportError as exc:
            raise CommandError('openpyxl is required') from exc

        src = opts['source']
        manual = json.load(open(opts['manual'], encoding='utf-8'))

        orders_zip = self._one(src, 'OutletOrderBySKUReport*.zip')
        outlets_csv = self._one(src, 'CustomerListReport*.csv')
        rates_xlsx = self._one(src, 'FMC AND NC.xlsx')
        actual_xlsx = self._one(src, 'ACTUAL SALE*.xlsx')

        # -- BIZOM orders (company book) ------------------------------------
        zf = zipfile.ZipFile(orders_zip)
        reader = csv.DictReader(io.TextIOWrapper(zf.open(zf.namelist()[0]), encoding='utf-8-sig'))
        orders = {}
        sku_price = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))  # sku -> pricelist -> [M, value]
        order_outlets = {}
        for row in reader:
            if row['Order_Status'] != 'CL':
                continue
            sku = row['Sku'].strip()
            m = float(row['SKU_qty_in_sticks'] or 0) / 1000
            value = float(row['Sku_Order_Value'] or 0)
            key = row['Order_ID']
            order = orders.get(key)
            if order is None:
                order = orders[key] = {
                    'order_id': key, 'invoice': row['Invoice_Number'].lstrip("'"),
                    'outlet': row['Outlet_ID'], 'dr': row['DSR_ID'], 'date': row['Date_Of_Visit'],
                    'pricelist': row['Price_list'], 'lines': defaultdict(lambda: [0.0, 0.0, 0.0]),
                }
                order_outlets.setdefault(row['Outlet_ID'], row['Outlet_Name'].strip())
            line = order['lines'][sku]
            line[0] += m
            line[1] += value
            line[2] += float(row['AIT'] or 0)
            acc = sku_price[sku][row['Price_list']]
            acc[0] += m
            acc[1] += value

        sku_names = sorted(sku_price)
        sku_index = {name: i for i, name in enumerate(sku_names)}

        # -- PTC invoice rates per M -----------------------------------------
        wb = openpyxl.load_workbook(rates_xlsx, data_only=True, read_only=True)
        ptc_rates = {}
        for row in wb['Sheet2'].iter_rows(values_only=True):
            cells = [c for c in row if c not in (None, '')]
            if len(cells) >= 2 and isinstance(cells[0], str) and isinstance(cells[1], (int, float)):
                ptc_rates[norm(cells[0])] = float(cells[1])
        velo_rate_by_mg = {'6': ptc_rates.get(norm('VELO Polar Mint 6MG NANO')),
                           '10': ptc_rates.get(norm('Polar Mint 10 MG')),
                           '14': ptc_rates.get(norm('Polar Mint 14 MG')),
                           '17': ptc_rates.get(norm('Polar Mint 17 MG'))}

        def ptc_rate_for(name):
            key = norm(name)
            key = PTC_RATE_ALIASES.get(key, key)
            if key in ptc_rates:
                return ptc_rates[key]
            if 'velo' in key:
                return velo_rate_by_mg.get(velo_mg(name))
            for rate_key, rate in ptc_rates.items():
                if rate_key and (rate_key in key or key in rate_key):
                    return rate
            return None

        commission = manual['commission_by_brand']
        velo_commission = manual['velo_commission_by_mg']

        def commission_for(name):
            if 'velo' in name.lower():
                rate = velo_commission.get(velo_mg(name) or '10', 150)
                return [rate, 0]
            best = None
            for brand_key, rates in commission.items():
                if brand_key.lower() in name.lower() and (best is None or len(brand_key) > len(best[0])):
                    best = (brand_key, rates)
            return best[1] if best else [0, 0]

        skus = []
        for name in sku_names:
            prices = {}
            for pricelist, (m, value) in sku_price[name].items():
                if m > 0:
                    prices[pricelist] = round(value / m, 2)
            rate = ptc_rate_for(name)
            if rate is None:
                retail = prices.get('RETAIL_PRICE_NON_TAX FILER') or max(prices.values())
                rate = round(retail * 0.955, 2)  # ~4.5% distributor margin seen on matched SKUs
                rate_source = 'estimated'
            else:
                rate_source = 'ptc_price_list'
            skus.append({
                'bizom_name': name, 'brand': brand_for(name),
                'category': 'NC' if 'velo' in name.lower() else 'FMC',
                'ptc_rate': rate, 'ptc_rate_source': rate_source,
                'prices': prices, 'commission': commission_for(name),
            })

        # -- Outlets ------------------------------------------------------------
        outlets = {}
        dr_area_votes = defaultdict(lambda: defaultdict(int))
        with open(outlets_csv, encoding='utf-8-sig', errors='replace') as fh:
            for row in csv.DictReader(fh):
                oid = row['Outlet_Id']
                area = (row['Free_Field_2'] or '').upper()
                kind = (row['Free_Field_1'] or '').upper()
                if area == 'MANDI':
                    channel = 'MANDI'
                elif kind == 'WHOLESALE':
                    channel = 'VWS' if area == 'RURAL' else 'WS'
                else:
                    channel = 'VDD' if area == 'RURAL' else 'DD'
                dr_area_votes[row['DSR_Code']][area] += 1
                if oid in outlets:
                    continue
                pricelist = row['Pricelist_Name'].upper()
                outlets[oid] = {
                    'id': oid, 'name': row['Outlet_Name'].strip(), 'dr': row['DSR_Code'],
                    'channel': channel, 'filer': 'NON' not in pricelist,
                    'area': area, 'address': row['Outlet_Address'].strip()[:255],
                    'beat': row['Beat_Name'][:255], 'visit_days': row['Visit_Day'][:100],
                    'lat': row['Outlet_Latitude'] or None, 'lng': row['Outlet_Longitude'] or None,
                }
        for oid, name in order_outlets.items():
            outlets.setdefault(oid, {
                'id': oid, 'name': name, 'dr': '', 'channel': 'DD', 'filer': False, 'area': '',
                'address': '', 'beat': '', 'visit_days': '', 'lat': None, 'lng': None,
            })

        # -- Actual-sale sheet (actual book) ------------------------------------
        wb = openpyxl.load_workbook(actual_xlsx, data_only=True, read_only=True)
        month = sorted({o['date'][:7] for o in orders.values()})[-1]
        dr_names = {}
        for row in wb['TOTAL'].iter_rows(values_only=True):
            sr_col = self._sr_col(row)
            if (sr_col is not None and isinstance(row[sr_col], (int, float))
                    and 0 < row[sr_col] < 100 and row[sr_col + 1]):
                dr_names[int(row[sr_col])] = str(row[sr_col + 1]).strip().title()
        actual = defaultdict(float)
        for sheet in wb.sheetnames:
            day = sheet.rstrip('.')
            if not day.isdigit():
                continue
            date = f'{month}-{int(day):02d}'
            try:
                import datetime
                datetime.date.fromisoformat(date)
            except ValueError:
                continue
            blocks = None
            for row in wb[sheet].iter_rows(values_only=True):
                if blocks is None:
                    # Header row: "Sr. No." starts the retail block, then the
                    # scattered-wholesale block repeats the same columns.
                    starts = [i for i, c in enumerate(row) if isinstance(c, str) and c.strip().lower().startswith('sr')]
                    if len(starts) >= 2:
                        blocks = [('RETAIL', starts[0]), ('SCATTERED', starts[1])]
                    continue
                sr_col = blocks[0][1]
                if len(row) <= sr_col or not isinstance(row[sr_col], (int, float)):
                    continue
                dr_no = int(row[sr_col])
                for bucket, start in blocks:
                    for offset, sku_name in enumerate(ACTUAL_SHEET_COLUMNS):
                        col = start + 2 + offset
                        value = row[col] if col < len(row) else None
                        if isinstance(value, (int, float)) and abs(value) > 1e-6:
                            actual[(date, dr_no, sku_name, bucket)] += value

        # The sheet's "Sr. No." is a row number, not the BIZOM device: Raza Sarwar
        # is row 3 but device DR21 (distributor's DR list, 25 Nov 2026). Map rows
        # to devices, and name each device after the person on it now.
        row_to_dr = {int(k): int(v) for k, v in manual.get('sheet_row_to_dr', {}).items()}
        if row_to_dr:
            remapped = defaultdict(float)
            for (date, dr_no, col, bucket), m in actual.items():
                if dr_no in row_to_dr:
                    remapped[(date, row_to_dr[dr_no], col, bucket)] += m
                elif abs(m) > 1e-6:
                    self.stderr.write(f'Sheet row {dr_no} has sales but no BIZOM device mapping; skipped.')
            actual = remapped
            sheet_drs = set(row_to_dr.values())
            dr_names = {int(k): v for k, v in manual.get('dr_names', {}).items()}
        else:
            sheet_drs = set(dr_names)

        drs = {}
        for code, votes in dr_area_votes.items():
            drs[code] = {'code': code, 'area': max(votes, key=votes.get)}
        for o in orders.values():
            drs.setdefault(o['dr'], {'code': o['dr'], 'area': 'URBAN'})
        for number, name in dr_names.items():
            code = f'SGD_SGD_DR{number:02d}'
            drs.setdefault(code, {'code': code, 'area': 'URBAN'})
        for code, dr in drs.items():
            match = re.search(r'_DR(\d+)$', code)
            number = int(match.group(1)) if match else None
            dr['number'] = number
            dr['on_actual_sheet'] = number in sheet_drs
            dr['name'] = dr_names.get(number) or code.split('_')[-1]

        bundle = {
            'month': month,
            'skus': skus,
            'drs': sorted(drs.values(), key=lambda d: d['code']),
            'outlets': list(outlets.values()),
            'sku_names': sku_names,
            # [order_id, invoice, outlet, dr, date, pricelist, [[sku_idx, M, value, ait], ...]]
            'orders': [
                [o['order_id'], o['invoice'], o['outlet'], o['dr'], o['date'], o['pricelist'],
                 [[sku_index[s], round(l[0], 4), round(l[1], 2), round(l[2], 2)] for s, l in o['lines'].items()]]
                for o in orders.values()
            ],
            # [date, dr_number, sheet column key, bucket, M]
            'actual': [[d, n, s, b, round(m, 3)] for (d, n, s, b), m in sorted(actual.items())],
            'pay_grades': manual['pay_grades'],
            'sample_settlements': manual.get('sample_settlements', []),
            'fsos': manual.get('fsos', {}),
            'opening_stock': read_godown_opening(opts['source'], manual.get('godown_opening'), skus),
            'ptc_invoices': read_ptc_invoices(opts['source'], manual.get('ptc_invoices'), month),
        }
        os.makedirs(os.path.dirname(os.path.abspath(opts['out'])), exist_ok=True)
        with gzip.open(opts['out'], 'wt', encoding='utf-8') as fh:
            json.dump(bundle, fh, separators=(',', ':'))
        self.stdout.write(self.style.SUCCESS(
            f"Wrote {opts['out']}: {len(skus)} SKUs, {len(bundle['drs'])} DRs, {len(outlets)} outlets, "
            f"{len(orders)} BIZOM orders, {len(bundle['actual'])} actual-sale rows for {month}."
        ))

    @staticmethod
    def _sr_col(row):
        for i, cell in enumerate(row or ()):
            if cell not in (None, ''):
                return i if isinstance(cell, (int, float)) else None
        return None

    def _one(self, folder, pattern):
        matches = sorted(glob.glob(os.path.join(folder, pattern)))
        if not matches:
            raise CommandError(f'No file matching {pattern!r} in {folder!r}')
        return matches[-1]


def _norm(text):
    return re.sub(r'[^a-z]', '', str(text or '').lower())


# Godown sheet headers that don't match a BIZOM SKU name by spelling.
GODOWN_ALIASES = {'capstanelite': 'CbPM Elite', 'capstanbypallmalllep': 'Capstan by Pall Mall Q2 LEP 20HL',
                  'johnplayerpolypack': 'John Player 20HL Poly Pack'}


def read_godown_opening(source, spec, skus):
    """Their GODOWN sheet for one evening: the "Actual On Hand" row, per SKU, in M."""
    if not spec:
        return None
    import openpyxl

    ws = openpyxl.load_workbook(os.path.join(source, spec['file']), data_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header = next(r for r in rows if any(str(c or '').strip().lower() == "sku's" for c in r))
    on_hand = next(r for r in rows if str(r[1] or '').strip().lower() == 'actual on hand')
    by_norm = {}
    for sku in skus:
        name = sku['bizom_name']
        by_norm[_norm(re.sub(r'\s*20\s*HL.*$', '', name, flags=re.IGNORECASE))] = name
    out = {}
    for i, label in enumerate(header):
        key = _norm(label)
        name = GODOWN_ALIASES.get(key) or by_norm.get(key)
        value = on_hand[i] if i < len(on_hand) else None
        if name and isinstance(value, (int, float)):
            out[name] = round(float(value), 3)
    return {'date': spec['date'], 'stock': out}


def read_ptc_invoices(source, spec, month):
    """PTC's invoices for the month: date, number, quantity (M) and the tax split."""
    if not spec:
        return None
    import datetime

    import openpyxl

    year, mon = map(int, month.split('-'))
    ws = openpyxl.load_workbook(os.path.join(source, spec['file']), data_only=True).worksheets[0]
    out = []
    header = None
    for row in ws.iter_rows(values_only=True):
        cells = [str(c).strip().upper() if c is not None else '' for c in row]
        if header is None:
            if 'INVOICE NO' in cells:
                header = {name: i for i, name in enumerate(cells) if name}
            continue
        raw_date = row[header['DATE']]
        qty = row[header['QUANTITY UNITS']]
        if raw_date is None or not isinstance(qty, (int, float)):
            continue
        # Excel read "01-09-2026" as 9 Jan for days <= 12; the sheet is one month, so
        # take the day from whichever part is not the month.
        if isinstance(raw_date, datetime.datetime):
            day = raw_date.day if raw_date.month == mon else raw_date.month
        else:
            match = re.match(r'\s*(\d{1,2})[-/.]', str(raw_date))
            if not match:
                continue  # TOTAL row and the like
            day = int(match.group(1))
        num = lambda key: float(row[header[key]] or 0) if isinstance(row[header[key]], (int, float)) else 0.0  # noqa: E731
        out.append({
            'date': datetime.date(year, mon, day).isoformat(),
            'invoice': str(row[header['INVOICE NO']]).strip(),
            'quantity': round(float(qty), 3),
            'excise': num('FEDERAL EXCISE DUTY'),
            'value_incl_excise': num('VALUE INC OF EXCISE DUTY'),
            'ait': num('ADVANCE INCOME TAX'),
            'sales_tax': num('SALE TAX'),
            'cost': num('IN S TAX & SED'),
        })
    return out
