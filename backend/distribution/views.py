import csv

from django.db.models import Case, DecimalField, F, Sum, When
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from accounts.permissions import RolePermission
from warehouses.models import StockLedgerEntry

from .imports import TEMPLATE_COLUMNS, import_ptc_sales_file
from .actual_entry import day_grid, save_day
from .models import ActualSale, DRSettlement, PaymentReceipt, SalesOrder, SalesReturn, SalesTarget, Shop
from .serializers import (
    DRSettlementSerializer, PaymentReceiptSerializer, SalesOrderSerializer, SalesReturnSerializer,
    SalesTargetSerializer, ShopSerializer,
)


def _next_so_number():
    year = timezone.localdate().year
    seq = SalesOrder.objects.filter(so_number__startswith=f'SO-{year}-').count() + 1
    candidate = f'SO-{year}-{seq:05d}'
    while SalesOrder.objects.filter(so_number=candidate).exists():
        seq += 1
        candidate = f'SO-{year}-{seq:05d}'
    return candidate


class ShopViewSet(viewsets.ModelViewSet):
    """Shop lifecycle management (requirement doc, Distribution #2)."""
    queryset = Shop.objects.select_related('channel', 'dr', 'party').all()
    serializer_class = ShopSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['channel', 'status', 'dr', 'channel__channel_type', 'area_type']
    search_fields = ['name', 'locality', 'contact_phone', 'address', 'bizom_outlet_id', 'beat']


class ActualSaleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    The actual book (US-19). ``day/`` is the daily sales entry: GET the
    sheet for ?date=, POST {date, values} to save it — same layout as the
    distributor's ACTUAL SALE sheet (see distribution.actual_entry).
    """
    queryset = ActualSale.objects.select_related('dr', 'sku').all()
    permission_classes = [RolePermission]
    filterset_fields = ['date', 'dr', 'sku', 'bucket', 'source']

    def get_serializer_class(self):
        from rest_framework import serializers

        class _Serializer(serializers.ModelSerializer):
            class Meta:
                model = ActualSale
                fields = '__all__'
        return _Serializer

    @action(detail=False, methods=['get', 'post'])
    def day(self, request):
        import datetime

        raw = request.data.get('date') if request.method == 'POST' else request.query_params.get('date')
        try:
            day = datetime.date.fromisoformat(raw or timezone.localdate().isoformat())
        except ValueError:
            return Response({'detail': 'date must be YYYY-MM-DD'}, status=400)
        if request.method == 'POST':
            values = request.data.get('values') or {}
            try:
                summary = save_day(day, values, request.user)
            except (KeyError, ValueError, ArithmeticError) as exc:
                return Response({'detail': f'Could not save: {exc}'}, status=400)
            return Response({**day_grid(day), 'saved': summary})
        return Response(day_grid(day))


class DRSettlementViewSet(viewsets.ModelViewSet):
    """
    DR end-of-day cash settlement, laid out like the distributor's paper
    slip (KPO portion + DR portion, difference = short/excess).
    """
    queryset = DRSettlement.objects.select_related('dr__profile', 'warehouse').all()
    serializer_class = DRSettlementSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['date', 'dr', 'warehouse']
    search_fields = ['dr__first_name', 'dr__profile__dr_code', 'remarks']
    ordering_fields = ['date', 'total_sale']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def post_to_ledger(self, request, pk=None):
        settlement = self.get_object()
        if settlement.posted_entry_id:
            return Response({'detail': 'Already posted.'}, status=400)
        settlement.post_to_ledger(user=request.user)
        return Response(DRSettlementSerializer(settlement).data)


class SalesOrderViewSet(viewsets.ModelViewSet):
    """
    Sales orders (requirement doc, Distribution #3, #7, #8, #11). Lookup by
    shop/retailer/wholesale, channel, salesperson, warehouse for the
    various summary/history views is done via filterset_fields + `search`.
    """
    queryset = SalesOrder.objects.select_related('shop', 'channel', 'warehouse', 'dr').prefetch_related('lines__sku')
    serializer_class = SalesOrderSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['shop', 'channel', 'warehouse', 'dr', 'status', 'source']
    search_fields = ['so_number', 'ptc_reference_number']
    ordering_fields = ['order_date', 'timestamp']

    def perform_create(self, serializer):
        extra = {'created_by': self.request.user}
        if not serializer.validated_data.get('so_number'):
            extra['so_number'] = _next_so_number()
        if not serializer.validated_data.get('dr'):
            extra['dr'] = self.request.user
        serializer.save(**extra)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        so = self.get_object()
        try:
            so.confirm(user=request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(SalesOrderSerializer(so).data)

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser])
    def upload_ptc_sales(self, request):
        """Upload PTC/BIZOM sales data as .csv or .xlsx (requirement doc, Distribution #4)."""
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'No file provided (expected multipart field "file").'}, status=400)
        try:
            result = import_ptc_sales_file(upload.file, upload.name, request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(result)

    @action(detail=False, methods=['get'])
    def upload_template(self, request):
        """Download the fixed-column CSV template for the PTC sales upload."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="ptc_sales_upload_template.csv"'
        writer = csv.writer(response)
        writer.writerow(TEMPLATE_COLUMNS)
        writer.writerow([
            timezone.localdate().isoformat(), 'PTC-REF-0001', 'SGD_SGD_DR01', 'DD', 'NON_FILER',
            'SGD-HQ', 'Sample Retail Shop', 'DNH-20HL', '5', '1250.00',
        ])
        return response

    @action(detail=False, methods=['get'])
    def closing_summary(self, request):
        """Today's sales closing summary (requirement doc, Distribution #7)."""
        from django.db.models import F

        today = timezone.localdate()
        qs = self.filter_queryset(self.get_queryset()).filter(
            order_date=today, status=SalesOrder.STATUS_CONFIRMED
        )
        totals = qs.aggregate(
            total_quantity=Sum('lines__quantity'),
            total_value=Sum(F('lines__quantity') * F('lines__unit_price')),
        )
        return Response({
            'date': today,
            'order_count': qs.count(),
            'total_quantity': totals['total_quantity'] or 0,
            'total_value': totals['total_value'] or 0,
        })

    @action(detail=False, methods=['get'])
    def stock_movement_summary(self, request):
        """
        Daily distribution out/in stock summary (requirement doc,
        Distribution #9): sales dispatched out vs. sales returns received
        in, grouped by day and warehouse. ?date_from=&date_to=&warehouse=
        """
        qs = StockLedgerEntry.objects.filter(
            entry_type__in=[StockLedgerEntry.SALE_OUT, StockLedgerEntry.SALE_RETURN_IN]
        )
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        warehouse = request.query_params.get('warehouse')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if warehouse:
            qs = qs.filter(warehouse_id=warehouse)

        qty_field = DecimalField(max_digits=14, decimal_places=3)
        rows = (
            qs.values(date=F('created_at__date'), warehouse_name=F('warehouse__name'))
            .annotate(
                out_quantity=Sum(
                    Case(When(entry_type=StockLedgerEntry.SALE_OUT, then=-F('quantity_change')), default=0, output_field=qty_field)
                ),
                in_quantity=Sum(
                    Case(When(entry_type=StockLedgerEntry.SALE_RETURN_IN, then=F('quantity_change')), default=0, output_field=qty_field)
                ),
            )
            .order_by('-date', 'warehouse_name')
        )
        return Response(list(rows))

    @action(detail=False, methods=['get'])
    def stock_movement_history(self, request):
        """
        Daily distribution out/in stock history report (requirement doc,
        Distribution #10): the underlying line-item detail behind the
        summary above. ?date_from=&date_to=&warehouse=
        """
        qs = StockLedgerEntry.objects.filter(
            entry_type__in=[StockLedgerEntry.SALE_OUT, StockLedgerEntry.SALE_RETURN_IN]
        ).select_related('warehouse', 'sku')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        warehouse = request.query_params.get('warehouse')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if warehouse:
            qs = qs.filter(warehouse_id=warehouse)

        rows = [
            {
                'date': entry.created_at.date(), 'warehouse_name': entry.warehouse.name,
                'sku_code': entry.sku.code, 'sku_name': entry.sku.name,
                'entry_type': entry.entry_type, 'quantity_change': entry.quantity_change,
                'reference': entry.reference,
            }
            for entry in qs.order_by('-created_at')[:500]
        ]
        return Response(rows)

    @action(detail=False, methods=['get'])
    def summary_by(self, request):
        """
        Sales summary grouped by salesperson, channel, brand/SKU or warehouse
        (requirement doc, Distribution #8). ?group_by=dr|channel|sku|brand|warehouse
        """
        group_map = {
            'dr': ('dr__id', 'dr__first_name', 'dr__last_name'),
            'channel': ('channel__id', 'channel__name'),
            'sku': ('lines__sku__id', 'lines__sku__code', 'lines__sku__name'),
            'brand': ('lines__sku__brand__id', 'lines__sku__brand__name'),
            'warehouse': ('warehouse__id', 'warehouse__name'),
        }
        group_by = request.query_params.get('group_by', 'channel')
        fields = group_map.get(group_by, group_map['channel'])

        from django.db.models import F

        qs = self.filter_queryset(self.get_queryset()).filter(status=SalesOrder.STATUS_CONFIRMED)
        rows = (
            qs.values(*fields)
            .annotate(
                total_quantity=Sum('lines__quantity'),
                total_value=Sum(F('lines__quantity') * F('lines__unit_price')),
            )
            .order_by('-total_value')
        )
        return Response(list(rows))


class SalesReturnViewSet(viewsets.ModelViewSet):
    """Add/change/view/delete sales returns (requirement doc, Distribution #5)."""
    queryset = SalesReturn.objects.select_related('shop', 'warehouse', 'sku', 'sales_order')
    serializer_class = SalesReturnSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['shop', 'warehouse', 'sku']

    def perform_create(self, serializer):
        sales_return = serializer.save(created_by=self.request.user)
        sales_return.apply(user=self.request.user)


class PaymentReceiptViewSet(viewsets.ModelViewSet):
    """Payment receipts / collections (requirement doc, Distribution #6)."""
    queryset = PaymentReceipt.objects.select_related('shop', 'sales_order')
    serializer_class = PaymentReceiptSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['shop', 'method']

    def perform_create(self, serializer):
        receipt = serializer.save(created_by=self.request.user)
        receipt.post_to_ledger(user=self.request.user)


class SalesTargetViewSet(viewsets.ModelViewSet):
    """DR-wise, channel-wise monthly targets (requirement doc + questionnaire #24)."""
    queryset = SalesTarget.objects.select_related('dr', 'channel')
    serializer_class = SalesTargetSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['dr', 'channel', 'year', 'month']

    @action(detail=False, methods=['get'])
    def achievement(self, request):
        """Target vs. actual, per DR, for a given year/month."""
        from django.db.models import F

        year = request.query_params.get('year', timezone.localdate().year)
        month = request.query_params.get('month', timezone.localdate().month)

        targets = SalesTarget.objects.filter(year=year, month=month).select_related('dr', 'channel')
        rows = []
        for t in targets:
            actual = (
                SalesOrder.objects.filter(
                    dr=t.dr, channel=t.channel, status=SalesOrder.STATUS_CONFIRMED,
                    order_date__year=year, order_date__month=month,
                )
                .aggregate(total=Sum(F('lines__quantity')))['total']
                or 0
            )
            rows.append({
                'dr_id': t.dr_id,
                'dr_name': t.dr.get_full_name() or t.dr.username,
                'channel': t.channel.name,
                'target_volume_m': t.target_volume_m,
                'actual_volume': actual,
            })
        return Response(rows)
