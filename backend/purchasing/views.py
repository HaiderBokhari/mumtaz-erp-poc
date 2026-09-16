from django.db.models import Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounting.models import Party
from accounts.permissions import RolePermission

from .models import PurchaseOrder, PurchaseReturn
from .serializers import PurchaseOrderSerializer, PurchaseReturnSerializer


def _next_po_number():
    year = timezone.localdate().year
    seq = PurchaseOrder.objects.filter(po_number__startswith=f'PO-{year}-').count() + 1
    candidate = f'PO-{year}-{seq:05d}'
    while PurchaseOrder.objects.filter(po_number=candidate).exists():
        seq += 1
        candidate = f'PO-{year}-{seq:05d}'
    return candidate


def _default_supplier():
    party, _ = Party.objects.get_or_create(
        name='Pakistan Tobacco Company (PTC)', defaults={'party_type': Party.SUPPLIER}
    )
    return party


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    """
    Create/view/print purchase orders (requirement doc, Purchase #1, #4).
    Lookup works by either the internal PO number or the PTC SAP reference
    number via the `search` query param (e.g. ?search=PO-2026-00004).
    """
    queryset = PurchaseOrder.objects.select_related('warehouse', 'supplier').prefetch_related('lines__sku')
    serializer_class = PurchaseOrderSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['warehouse', 'supplier', 'status']
    search_fields = ['po_number', 'ptc_reference_number']
    ordering_fields = ['order_date', 'created_at']

    def perform_create(self, serializer):
        extra = {'created_by': self.request.user}
        if not serializer.validated_data.get('po_number'):
            extra['po_number'] = _next_po_number()
        if not serializer.validated_data.get('supplier'):
            extra['supplier'] = _default_supplier()
        serializer.save(**extra)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        po = self.get_object()
        try:
            po.submit()
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        po = self.get_object()
        try:
            po.approve(request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        po = self.get_object()
        try:
            po.receive(request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=False, methods=['get'])
    def history_by_sku(self, request):
        """Purchase order history grouped by SKU/brand (requirement doc, Purchase #5)."""
        rows = (
            self.filter_queryset(self.get_queryset())
            .values('lines__sku__code', 'lines__sku__name', 'lines__sku__brand__name')
            .annotate(total_quantity=Sum('lines__quantity'), total_value=Sum('lines__unit_cost'))
            .order_by('lines__sku__brand__name', 'lines__sku__code')
        )
        return Response(list(rows))


class PurchaseReturnViewSet(viewsets.ModelViewSet):
    """Purchase return claims aligned with PTC workflow (requirement doc, Purchase #2)."""
    queryset = PurchaseReturn.objects.select_related('warehouse', 'sku', 'purchase_order')
    serializer_class = PurchaseReturnSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['warehouse', 'sku', 'status']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        ret = self.get_object()
        try:
            ret.submit(request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(PurchaseReturnSerializer(ret).data)
