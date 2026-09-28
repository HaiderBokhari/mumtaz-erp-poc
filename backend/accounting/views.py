from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import RolePermission

from .models import AccountGroup, ChartOfAccount, JournalEntry, JournalLine, Party, Voucher
from .serializers import (
    AccountGroupSerializer, ChartOfAccountSerializer, JournalEntrySerializer,
    PartySerializer, VoucherSerializer,
)


def _next_voucher_number(voucher_type):
    year = timezone.localdate().year
    prefix = {'PAYMENT': 'PV', 'JOURNAL': 'JV', 'EXPENSE': 'EV'}.get(voucher_type, 'VV')
    seq = Voucher.objects.filter(voucher_number__startswith=f'{prefix}-{year}-').count() + 1
    candidate = f'{prefix}-{year}-{seq:05d}'
    while Voucher.objects.filter(voucher_number=candidate).exists():
        seq += 1
        candidate = f'{prefix}-{year}-{seq:05d}'
    return candidate


def _aging_bucket(days):
    if days <= 30:
        return '0-30'
    if days <= 60:
        return '31-60'
    if days <= 90:
        return '61-90'
    return '90+'


def _party_aging(party):
    """
    Days a party's balance has been continuously outstanding, approximated
    by walking their ledger chronologically and tracking the date the
    balance last crossed from settled (<=0) to owing (>0).
    """
    lines = JournalLine.objects.filter(party=party).select_related('entry').order_by('entry__date', 'entry__id', 'id')
    running = Decimal('0')
    start_date = None
    for line in lines:
        delta = line.debit - line.credit
        if party.party_type == Party.SUPPLIER:
            delta = -delta
        prev = running
        running += delta
        if prev <= 0 < running:
            start_date = line.entry.date
        elif running <= 0:
            start_date = None
    if running <= 0:
        return None
    days = (timezone.localdate() - start_date).days if start_date else 0
    return {
        'party_id': party.id, 'party_name': party.name, 'balance': running,
        'days_outstanding': days, 'bucket': _aging_bucket(days),
    }


class AccountGroupViewSet(viewsets.ModelViewSet):
    queryset = AccountGroup.objects.all()
    serializer_class = AccountGroupSerializer
    permission_classes = [RolePermission]


class ChartOfAccountViewSet(viewsets.ModelViewSet):
    """Account Groups, Subgroups, Chart of Accounts (requirement doc, Accounts #1)."""
    queryset = ChartOfAccount.objects.select_related('group').all()
    serializer_class = ChartOfAccountSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['account_type', 'is_active']
    search_fields = ['code', 'name']


class PartyViewSet(viewsets.ModelViewSet):
    """Suppliers, retailers and wholesalers with a running ledger balance (requirement doc, Accounts #5)."""
    queryset = Party.objects.all()
    serializer_class = PartySerializer
    permission_classes = [RolePermission]
    filterset_fields = ['party_type', 'is_active']
    search_fields = ['name']

    @action(detail=True, methods=['get'])
    def ledger(self, request, pk=None):
        """View and print party ledger (requirement doc, Accounts #5, #7): running balance, optional date range."""
        party = self.get_object()
        qs = JournalLine.objects.filter(party=party).select_related('entry', 'account').order_by(
            'entry__date', 'entry__id', 'id'
        )
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(entry__date__gte=date_from)
        if date_to:
            qs = qs.filter(entry__date__lte=date_to)

        # Opening balance = balance of everything strictly before date_from (0 if no date_from given).
        opening_balance = Decimal('0')
        if date_from:
            prior = JournalLine.objects.filter(party=party, entry__date__lt=date_from)
            totals = prior.aggregate(d=Sum('debit'), c=Sum('credit'))
            delta = (totals['d'] or Decimal('0')) - (totals['c'] or Decimal('0'))
            opening_balance = -delta if party.party_type == Party.SUPPLIER else delta

        running = opening_balance
        rows = []
        for line in qs:
            delta = line.debit - line.credit
            if party.party_type == Party.SUPPLIER:
                delta = -delta
            running += delta
            rows.append({
                'date': line.entry.date, 'narration': line.entry.narration,
                'reference': line.entry.reference, 'account_code': line.account.code,
                'debit': line.debit, 'credit': line.credit, 'balance': running,
            })
        return Response({
            'party': PartySerializer(party).data, 'opening_balance': opening_balance,
            'lines': rows, 'closing_balance': running,
        })

    @action(detail=False, methods=['get'])
    def aged_receivables(self, request):
        """Aged receivables — mandatory per questionnaire #3."""
        rows = [
            _party_aging(p) for p in Party.objects.filter(party_type__in=[Party.RETAILER, Party.WHOLESALER])
        ]
        return Response([r for r in rows if r])

    @action(detail=False, methods=['get'])
    def aged_payables(self, request):
        """Aged payables — mandatory per questionnaire #3."""
        rows = [_party_aging(p) for p in Party.objects.filter(party_type=Party.SUPPLIER)]
        return Response([r for r in rows if r])


class VoucherViewSet(viewsets.ModelViewSet):
    """Payment / journal / expense vouchers (requirement doc, Accounts #3, #8, #9)."""
    queryset = Voucher.objects.select_related('party', 'debit_account', 'journal_entry').prefetch_related('lines')
    serializer_class = VoucherSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['voucher_type', 'status', 'party']

    def perform_create(self, serializer):
        extra = {'created_by': self.request.user}
        if not serializer.validated_data.get('voucher_number'):
            extra['voucher_number'] = _next_voucher_number(serializer.validated_data.get('voucher_type', 'JOURNAL'))
        serializer.save(**extra)

    @action(detail=True, methods=['post'])
    def post_voucher(self, request, pk=None):
        voucher = self.get_object()
        try:
            voucher.post(user=request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(VoucherSerializer(voucher).data)


class JournalEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only audit trail of every posted entry, including auto-posted ones from Sales/Purchasing/HR."""
    queryset = JournalEntry.objects.prefetch_related('lines__account', 'lines__party').all()
    serializer_class = JournalEntrySerializer
    permission_classes = [RolePermission]
    filterset_fields = ['source']
    search_fields = ['reference', 'narration']
    ordering_fields = ['date']


class FinancialStatementsViewSet(viewsets.ViewSet):
    """
    Income statement, balance sheet and cashflow statement (requirement
    doc, Accounts #4, #6). A ViewSet (not ModelViewSet) since these are
    computed, not stored — RolePermission checks against JournalEntry's
    `view` permission since all actions here are read-only reports.
    """
    permission_classes = [RolePermission]
    queryset = JournalEntry.objects.none()

    @action(detail=False, methods=['get'])
    def income_statement(self, request):
        date_from = request.query_params.get('date_from') or timezone.localdate().replace(day=1).isoformat()
        date_to = request.query_params.get('date_to') or timezone.localdate().isoformat()
        lines = JournalLine.objects.filter(
            entry__date__gte=date_from, entry__date__lte=date_to
        ).select_related('account')

        income, expenses = {}, {}
        for line in lines:
            acc = line.account
            if acc.account_type == ChartOfAccount.TYPE_INCOME:
                row = income.setdefault(acc.code, {'code': acc.code, 'name': acc.name, 'amount': Decimal('0')})
                row['amount'] += line.credit - line.debit
            elif acc.account_type == ChartOfAccount.TYPE_EXPENSE:
                row = expenses.setdefault(acc.code, {'code': acc.code, 'name': acc.name, 'amount': Decimal('0')})
                row['amount'] += line.debit - line.credit

        total_income = sum((r['amount'] for r in income.values()), Decimal('0'))
        total_expenses = sum((r['amount'] for r in expenses.values()), Decimal('0'))
        return Response({
            'date_from': date_from, 'date_to': date_to,
            'income': list(income.values()), 'expenses': list(expenses.values()),
            'total_income': total_income, 'total_expenses': total_expenses,
            'net_income': total_income - total_expenses,
        })

    @action(detail=False, methods=['get'])
    def balance_sheet(self, request):
        as_of = request.query_params.get('as_of') or timezone.localdate().isoformat()
        lines = JournalLine.objects.filter(entry__date__lte=as_of).select_related('account')

        assets, liabilities, equity = {}, {}, {}
        income_total = expense_total = Decimal('0')
        for line in lines:
            acc = line.account
            net = line.debit - line.credit
            if acc.account_type == ChartOfAccount.TYPE_ASSET:
                assets.setdefault(acc.code, {'code': acc.code, 'name': acc.name, 'amount': Decimal('0')})['amount'] += net
            elif acc.account_type == ChartOfAccount.TYPE_LIABILITY:
                liabilities.setdefault(acc.code, {'code': acc.code, 'name': acc.name, 'amount': Decimal('0')})['amount'] += -net
            elif acc.account_type == ChartOfAccount.TYPE_EQUITY:
                equity.setdefault(acc.code, {'code': acc.code, 'name': acc.name, 'amount': Decimal('0')})['amount'] += -net
            elif acc.account_type == ChartOfAccount.TYPE_INCOME:
                income_total += -net
            elif acc.account_type == ChartOfAccount.TYPE_EXPENSE:
                expense_total += net

        equity_rows = list(equity.values())
        equity_rows.append({'code': 'RE', 'name': 'Retained Earnings (cumulative)', 'amount': income_total - expense_total})
        total_assets = sum((a['amount'] for a in assets.values()), Decimal('0'))
        total_liabilities = sum((l['amount'] for l in liabilities.values()), Decimal('0'))
        total_equity = sum((e['amount'] for e in equity_rows), Decimal('0'))
        return Response({
            'as_of': as_of, 'assets': list(assets.values()), 'liabilities': list(liabilities.values()),
            'equity': equity_rows, 'total_assets': total_assets,
            'total_liabilities': total_liabilities, 'total_equity': total_equity,
        })

    @action(detail=False, methods=['get'])
    def cashflow_statement(self, request):
        date_from = request.query_params.get('date_from') or timezone.localdate().replace(day=1).isoformat()
        date_to = request.query_params.get('date_to') or timezone.localdate().isoformat()
        cash_codes = [ChartOfAccount.CASH, ChartOfAccount.BANK]

        opening = JournalLine.objects.filter(
            account__code__in=cash_codes, entry__date__lt=date_from
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        opening_cash = (opening['d'] or Decimal('0')) - (opening['c'] or Decimal('0'))

        period = JournalLine.objects.filter(
            account__code__in=cash_codes, entry__date__gte=date_from, entry__date__lte=date_to
        ).select_related('entry')

        by_source = {}
        total_in = total_out = Decimal('0')
        for line in period:
            total_in += line.debit
            total_out += line.credit
            row = by_source.setdefault(line.entry.source, {'source': line.entry.source, 'inflow': Decimal('0'), 'outflow': Decimal('0')})
            row['inflow'] += line.debit
            row['outflow'] += line.credit

        return Response({
            'date_from': date_from, 'date_to': date_to, 'opening_cash': opening_cash,
            'total_inflows': total_in, 'total_outflows': total_out,
            'closing_cash': opening_cash + total_in - total_out, 'by_source': list(by_source.values()),
        })
