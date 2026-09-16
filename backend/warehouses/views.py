from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import RolePermission

from .models import (
    SafetyStockLevel, StockAdjustment, StockLedgerEntry, StockLevel,
    StockTransfer, Warehouse,
)
from .serializers import (
    SafetyStockLevelSerializer, StockAdjustmentSerializer, StockLedgerEntrySerializer,
    StockLevelSerializer, StockTransferSerializer, WarehouseSerializer,
)


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['is_active']
    search_fields = ['name', 'code']


class StockLevelViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View and print stock-at-hand report, filterable by SKU, warehouse, brand
    (requirement doc, Inventory #12).
    """
    queryset = StockLevel.objects.select_related('warehouse', 'sku', 'sku__brand').all()
    serializer_class = StockLevelSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['warehouse', 'sku', 'sku__brand']
    search_fields = ['sku__code', 'sku__name']
    ordering_fields = ['quantity']


class StockLedgerEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """Full movement history behind the stock-on-hand numbers (audit trail)."""
    queryset = StockLedgerEntry.objects.select_related('warehouse', 'sku', 'created_by').all()
    serializer_class = StockLedgerEntrySerializer
    permission_classes = [RolePermission]
    filterset_fields = ['warehouse', 'sku', 'entry_type']
    ordering_fields = ['created_at']


class StockTransferViewSet(viewsets.ModelViewSet):
    """Facilitation & settlement of inventory movement between warehouses (requirement doc, Inventory #5)."""
    queryset = StockTransfer.objects.select_related('from_warehouse', 'to_warehouse').prefetch_related('lines')
    serializer_class = StockTransferSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['status', 'from_warehouse', 'to_warehouse']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def dispatch(self, request, pk=None):
        transfer = self.get_object()
        try:
            transfer.dispatch(user=request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(StockTransferSerializer(transfer).data)

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        transfer = self.get_object()
        try:
            transfer.receive(user=request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(StockTransferSerializer(transfer).data)


class SafetyStockLevelViewSet(viewsets.ModelViewSet):
    """Minimum safety stock config + a `below_minimum` alert list."""
    queryset = SafetyStockLevel.objects.select_related('warehouse', 'sku')
    serializer_class = SafetyStockLevelSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['warehouse', 'sku']

    @action(detail=False, methods=['get'])
    def below_minimum(self, request):
        rows = [
            SafetyStockLevelSerializer(level).data
            for level in self.filter_queryset(self.get_queryset())
            if level.is_below_minimum
        ]
        return Response(rows)


class StockAdjustmentViewSet(viewsets.ModelViewSet):
    """Damaged / lost / stolen stock and physical-count corrections (requirement doc, Inventory #7)."""
    queryset = StockAdjustment.objects.select_related('warehouse', 'sku')
    serializer_class = StockAdjustmentSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['warehouse', 'sku', 'reason']

    def perform_create(self, serializer):
        adjustment = serializer.save(created_by=self.request.user)
        adjustment.apply(user=self.request.user)
