import datetime
from collections import defaultdict
from decimal import Decimal

from django.db.models import Case, CharField, DecimalField, F, Max, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.models import ChartOfAccount, Party, PartyBalance
from distribution.models import ActualSale, DRSettlement, SalesOrder, SalesOrderLine
from purchasing.models import PurchaseOrder
from warehouses.models import SafetyStockLevel, StockLevel

from .payout import dr_payout_rows

MONEY_FIELD = DecimalField(max_digits=16, decimal_places=2)
D0 = Decimal('0')


def _money_sum(expr):
    return Coalesce(Sum(expr, output_field=MONEY_FIELD), Value(0, output_field=MONEY_FIELD))


def available_months():
    """Months that have any sales in either book, newest first, as 'YYYY-MM'."""
    months = set()
    for d in ActualSale.objects.dates('date', 'month'):
        months.add(d.strftime('%Y-%m'))
    for d in SalesOrder.objects.dates('order_date', 'month'):
        months.add(d.strftime('%Y-%m'))
    return sorted(months, reverse=True)


def month_range(request):
    """
    The reporting month from ?month=YYYY-MM, defaulting to the latest month
    that has data (so a demo on loaded September data opens on September,
    not on an empty current month).
    """
    months = available_months()
    label = request.query_params.get('month') or (months[0] if months else timezone.localdate().strftime('%Y-%m'))
    year, month = map(int, label.split('-'))
    start = datetime.date(year, month, 1)
    end = (start + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    return start, end, label, months


def _company_lines(start, end):
    return SalesOrderLine.objects.filter(
        sales_order__order_date__gte=start, sales_order__order_date__lte=end,
        sales_order__status=SalesOrder.STATUS_CONFIRMED,
    )


def _actual_rows(start, end):
    return ActualSale.objects.filter(date__gte=start, date__lte=end)


def _f(value):
    return float(value or 0)


class DashboardView(APIView):
    """
    Owner-facing dashboard (questionnaire #2: "Yes owner facing dashboard is
    mandatory"), now built around the two books: actual sales (what DRs
    physically sold) beside the company/BIZOM version (US-19), plus the
    Madam adjustment gap between them.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start, end, label, months = month_range(request)
        company = _company_lines(start, end)
        actual = _actual_rows(start, end)

        company_tot = company.aggregate(m=_money_sum('quantity'), value=_money_sum(F('quantity') * F('unit_price')))
        actual_tot = actual.aggregate(
            m=_money_sum('quantity_m'), value=_money_sum(F('quantity_m') * F('unit_price')),
            cost=_money_sum(F('quantity_m') * F('sku__current_cost_price')),
        )

        settlements = DRSettlement.objects.filter(date__gte=start, date__lte=end)
        settle = defaultdict(lambda: D0)
        for s in settlements:
            settle['cash'] += s.total_cash
            settle['bank'] += s.total_bank
            settle['market_credit'] += s.market_credit
            settle['fbr'] += s.fbr
            settle['banam'] += s.total_banam
            settle['wasooli'] += s.madam_wasooli
            if s.difference > 0:
                settle['short'] += s.difference
            settle['count'] += 1

        by_warehouse = (
            StockLevel.objects.values('warehouse__name', 'warehouse__code')
            .annotate(m=_money_sum('quantity'), value=_money_sum(F('quantity') * F('sku__current_cost_price')))
            .order_by('warehouse__name')
        )
        stock_value = sum((row['value'] for row in by_warehouse), D0)
        adjusted_value = sum((row['value'] for row in by_warehouse if row['warehouse__code'] == 'SGD-ADJ'), D0)

        daily = defaultdict(lambda: {'actual_value': 0.0, 'company_value': 0.0, 'actual_m': 0.0, 'company_m': 0.0})
        for row in company.values(day=F('sales_order__order_date')).annotate(
                m=_money_sum('quantity'), value=_money_sum(F('quantity') * F('unit_price'))):
            daily[row['day']]['company_value'] = _f(row['value'])
            daily[row['day']]['company_m'] = _f(row['m'])
        for row in actual.values(day=F('date')).annotate(
                m=_money_sum('quantity_m'), value=_money_sum(F('quantity_m') * F('unit_price'))):
            daily[row['day']]['actual_value'] = _f(row['value'])
            daily[row['day']]['actual_m'] = _f(row['m'])

        brands = defaultdict(lambda: {'actual_m': 0.0, 'company_m': 0.0, 'actual_value': 0.0, 'company_value': 0.0})
        for row in company.values(brand=F('sku__brand__name')).annotate(
                m=_money_sum('quantity'), value=_money_sum(F('quantity') * F('unit_price'))):
            brands[row['brand']]['company_m'] = _f(row['m'])
            brands[row['brand']]['company_value'] = _f(row['value'])
        for row in actual.values(brand=F('sku__brand__name')).annotate(
                m=_money_sum('quantity_m'), value=_money_sum(F('quantity_m') * F('unit_price'))):
            brands[row['brand']]['actual_m'] = _f(row['m'])
            brands[row['brand']]['actual_value'] = _f(row['value'])

        channels = (
            company.values(channel=F('sales_order__channel__channel_type'))
            .annotate(value=_money_sum(F('quantity') * F('unit_price')))
            .order_by('-value')
        )

        receivable_parties = Party.objects.exclude(party_type=Party.SUPPLIER).values_list('id', flat=True)
        outstanding = PartyBalance.objects.filter(party_id__in=receivable_parties).aggregate(
            total=_money_sum('balance'))['total']

        low_stock_count = sum(
            1 for level in SafetyStockLevel.objects.select_related('warehouse', 'sku') if level.is_below_minimum
        )

        revenue = actual_tot['value']
        return Response({
            'month': label,
            'months': months,
            'actual_sales_value': revenue,
            'actual_sales_m': actual_tot['m'],
            'company_sales_value': company_tot['value'],
            'company_sales_m': company_tot['m'],
            'gap_value': company_tot['value'] - revenue,
            'gap_m': company_tot['m'] - actual_tot['m'],
            'gross_profit': revenue - actual_tot['cost'],
            'gross_margin_pct': round(_f(revenue - actual_tot['cost']) / _f(revenue) * 100, 2) if revenue else 0,
            'net_profit': _net_profit(start, end),
            'stock_value': stock_value,
            'adjusted_stock_value': adjusted_value,
            'stock_by_warehouse': [
                {'warehouse': r['warehouse__name'], 'code': r['warehouse__code'], 'm': r['m'], 'value': r['value']}
                for r in by_warehouse
            ],
            'settlements': {k: v for k, v in settle.items()},
            'outstanding_receivables': outstanding,
            'open_purchase_orders': PurchaseOrder.objects.exclude(
                status__in=[PurchaseOrder.STATUS_RECEIVED, PurchaseOrder.STATUS_CANCELLED]).count(),
            'low_stock_alerts': low_stock_count,
            'daily': [{'day': day.isoformat(), **vals} for day, vals in sorted(daily.items())],
            'brands': sorted(
                [{'brand': b, **vals} for b, vals in brands.items()], key=lambda r: -r['company_value'],
            ),
            'channels': [{'channel': r['channel'], 'value': r['value']} for r in channels],
        })


def _net_profit(start, end):
    """Income less expenses from the general ledger for the month (actual book)."""
    from accounting.models import JournalLine

    lines = JournalLine.objects.filter(entry__date__gte=start, entry__date__lte=end)
    income = lines.filter(account__account_type=ChartOfAccount.TYPE_INCOME).aggregate(
        c=_money_sum('credit'), d=_money_sum('debit'))
    expense = lines.filter(account__account_type=ChartOfAccount.TYPE_EXPENSE).aggregate(
        c=_money_sum('credit'), d=_money_sum('debit'))
    return (income['c'] - income['d']) - (expense['d'] - expense['c'])


class CompanyVsActualView(APIView):
    """
    US-19: actual sales beside the company (BIZOM) version, grouped by DR,
    brand, SKU or day. The gap is the Madam adjustment: positive = invoiced
    in BIZOM but not physically sold (Banam).
    """
    permission_classes = [IsAuthenticated]

    GROUPS = {
        'dr': ('sales_order__dr__profile__dr_code', 'dr__profile__dr_code'),
        'brand': ('sku__brand__name', 'sku__brand__name'),
        'sku': ('sku__name', 'sku__name'),
        'day': ('sales_order__order_date', 'date'),
        # Shop-sale and mandi devices count as their own channel on both books.
        'channel': (
            Case(When(sales_order__dr__profile__sales_channel__in=['SHOP', 'MANDI'],
                      then=F('sales_order__dr__profile__sales_channel')),
                 default=F('sales_order__channel__channel_type'), output_field=CharField()),
            'channel_type',
        ),
        'fso': ('sales_order__dr__profile__supervisor__dr_code', 'dr__profile__supervisor__dr_code'),
    }

    def get(self, request):
        start, end, label, months = month_range(request)
        group = request.query_params.get('group', 'dr')
        if group not in self.GROUPS:
            group = 'dr'
        company_key, actual_key = self.GROUPS[group]
        rows = defaultdict(lambda: {'company_m': D0, 'company_value': D0, 'actual_m': D0, 'actual_value': D0,
                                    'assumed': False})
        company_expr = F(company_key) if isinstance(company_key, str) else company_key
        for r in _company_lines(start, end).values(key=company_expr).annotate(
                m=_money_sum('quantity'), value=_money_sum(F('quantity') * F('unit_price'))):
            rows[r['key']]['company_m'] = r['m']
            rows[r['key']]['company_value'] = r['value']
        if actual_key:
            actual = _actual_rows(start, end)
            for r in actual.values(key=F(actual_key)).annotate(
                    m=_money_sum('quantity_m'), value=_money_sum(F('quantity_m') * F('unit_price'))):
                rows[r['key']]['actual_m'] = r['m']
                rows[r['key']]['actual_value'] = r['value']
            if group == 'dr':
                for key in actual.filter(source=ActualSale.SOURCE_BIZOM_ASSUMED).values_list(
                        actual_key, flat=True).distinct():
                    rows[key]['assumed'] = True

        labels = {}
        if group == 'dr':
            from django.contrib.auth.models import User
            for code, first in User.objects.filter(profile__dr_code__in=list(rows)).values_list(
                    'profile__dr_code', 'first_name'):
                labels[code] = first

        if group == 'channel':
            from distribution.channels import LABELS
            for key in rows:
                labels[key] = LABELS.get(key, key or 'Not tagged')

        if group == 'fso':
            from accounts.models import UserProfile
            for code, first in UserProfile.objects.filter(dr_code__in=[k for k in rows if k]).values_list(
                    'dr_code', 'user__first_name'):
                labels[code] = first
            for key in rows:
                if not key:  # no supervisor, or the generic demo FSO with no code
                    labels[key] = 'No FSO assigned yet'

        out = []
        totals = defaultdict(lambda: D0)
        for key, vals in rows.items():
            gap_m = vals['company_m'] - vals['actual_m']
            gap_value = vals['company_value'] - vals['actual_value']
            out.append({
                'key': str(key), 'label': labels.get(key, str(key)), **vals,
                'gap_m': gap_m, 'gap_value': gap_value,
                'gap_pct': round(_f(gap_value) / _f(vals['company_value']) * 100, 1) if vals['company_value'] else None,
            })
            for field in ('company_m', 'company_value', 'actual_m', 'actual_value'):
                totals[field] += vals[field]
        totals['gap_m'] = totals['company_m'] - totals['actual_m']
        totals['gap_value'] = totals['company_value'] - totals['actual_value']
        sort_key = (lambda r: r['key']) if group in ('day', 'dr', 'fso') else (lambda r: -r['company_value'])
        if group == 'channel':
            from distribution.channels import ORDER
            sort_key = lambda r: ORDER.index(r['key']) if r['key'] in ORDER else len(ORDER)  # noqa: E731
        return Response({
            'month': label, 'months': months, 'group': group,
            'rows': sorted(out, key=sort_key), 'totals': totals,
        })


class DRPayoutView(APIView):
    """DR monthly salary + commission (distributor's revised salary structure and commission sheet)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start, _end, label, months = month_range(request)
        rows = dr_payout_rows(start.year, start.month)
        totals = defaultdict(lambda: D0)
        for row in rows:
            for field in ('actual_m', 'salary_total', 'commission', 'total_payable'):
                totals[field] += row[field]
        return Response({'month': label, 'months': months, 'rows': rows, 'totals': totals})


class MadamRegisterView(APIView):
    """
    Day-by-day Madam adjustments from DR settlements (Banam: invoiced, not
    sold; Wasooli: sold, not invoiced) with the running balance, and the
    stock currently held in the adjusted-stock godown.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start, end, label, months = month_range(request)
        days = (
            DRSettlement.objects.filter(date__gte=start, date__lte=end)
            .values('date')
            .annotate(
                banam_fmc=_money_sum('madam_banam_fmc'), banam_nc=_money_sum('madam_banam_nc'),
                wasooli=_money_sum('madam_wasooli'), total_sale=_money_sum('total_sale'),
            )
            .order_by('date')
        )
        running = D0
        out = []
        for d in days:
            net = d['banam_fmc'] + d['banam_nc'] - d['wasooli']
            running += net
            out.append({**d, 'net': net, 'running': running})
        held = (
            StockLevel.objects.filter(warehouse__code='SGD-ADJ', quantity__gt=0)
            .values(sku_name=F('sku__name'), brand=F('sku__brand__name'))
            .annotate(m=_money_sum('quantity'), value=_money_sum(F('quantity') * F('sku__current_cost_price')))
            .order_by('-value')
        )
        return Response({'month': label, 'months': months, 'days': out, 'adjusted_stock': list(held)})
