import datetime

from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from distribution.models import PaymentReceipt, SalesOrder, Shop
from purchasing.models import PurchaseOrder
from warehouses.models import SafetyStockLevel, StockLevel

MONEY_FIELD = DecimalField(max_digits=16, decimal_places=2)


def _money_sum(expr):
    return Coalesce(Sum(expr, output_field=MONEY_FIELD), Value(0, output_field=MONEY_FIELD))


class DashboardView(APIView):
    """
    Owner-facing dashboard (questionnaire #2: "Yes owner facing dashboard is
    mandatory"). One aggregated payload rather than many small requests, to
    keep the POC's React dashboard simple and fast.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        thirty_days_ago = today - datetime.timedelta(days=30)
        month_start = today.replace(day=1)

        stock_value = StockLevel.objects.aggregate(
            total=_money_sum(F('quantity') * F('sku__current_cost_price'))
        )['total']

        todays_orders = SalesOrder.objects.filter(order_date=today, status=SalesOrder.STATUS_CONFIRMED)
        todays_sales = todays_orders.aggregate(
            value=_money_sum(F('lines__quantity') * F('lines__unit_price')),
            qty=Coalesce(Sum('lines__quantity'), Value(0, output_field=MONEY_FIELD)),
        )

        mtd_orders = SalesOrder.objects.filter(
            order_date__gte=month_start, order_date__lte=today, status=SalesOrder.STATUS_CONFIRMED
        )
        mtd_sales_value = mtd_orders.aggregate(
            value=_money_sum(F('lines__quantity') * F('lines__unit_price'))
        )['value']

        open_po_count = PurchaseOrder.objects.exclude(
            status__in=[PurchaseOrder.STATUS_RECEIVED, PurchaseOrder.STATUS_CANCELLED]
        ).count()

        low_stock_count = sum(
            1 for level in SafetyStockLevel.objects.select_related('warehouse', 'sku')
            if level.is_below_minimum
        )

        outstanding_receivables = sum((shop.outstanding_balance for shop in Shop.objects.all()), start=0)

        collections_mtd_total = PaymentReceipt.objects.filter(
            received_at__date__gte=month_start, received_at__date__lte=today
        ).aggregate(total=Coalesce(Sum('amount'), Value(0, output_field=MONEY_FIELD)))['total']

        trend_rows = SalesOrder.objects.filter(
            order_date__gte=thirty_days_ago, order_date__lte=today, status=SalesOrder.STATUS_CONFIRMED
        )
        sales_trend = (
            trend_rows.values(day=F('order_date'))
            .annotate(value=_money_sum(F('lines__quantity') * F('lines__unit_price')))
            .order_by('day')
        )

        channel_breakdown = (
            mtd_orders.values('channel__name')
            .annotate(value=_money_sum(F('lines__quantity') * F('lines__unit_price')))
            .order_by('-value')
        )

        return Response({
            'stock_value': stock_value,
            'todays_sales_value': todays_sales['value'],
            'todays_sales_quantity': todays_sales['qty'],
            'mtd_sales_value': mtd_sales_value,
            'open_purchase_orders': open_po_count,
            'low_stock_alerts': low_stock_count,
            'outstanding_receivables': outstanding_receivables,
            'collections_mtd': collections_mtd_total,
            'sales_trend_30d': list(sales_trend),
            'channel_breakdown_mtd': list(channel_breakdown),
        })
