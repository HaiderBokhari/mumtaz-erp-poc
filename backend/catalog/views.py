from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import RolePermission

from .models import Brand, Channel, ChannelPrice, SKU
from .serializers import (
    BrandSerializer, ChannelPriceSerializer, ChannelSerializer,
    SKUDetailSerializer, SKUPriceMatrixSerializer, SKUSerializer,
)


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['status']
    search_fields = ['name', 'code']


class SKUViewSet(viewsets.ModelViewSet):
    """
    SKU Life Cycle management (requirement doc, Inventory #1, #4, #10).
    Supports search by SKU code/name and filtering by brand/status.
    """
    queryset = SKU.objects.select_related('brand').all()
    permission_classes = [RolePermission]
    filterset_fields = ['brand', 'status']
    search_fields = ['code', 'name', 'barcode']
    ordering_fields = ['code', 'name', 'current_cost_price']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SKUDetailSerializer
        return SKUSerializer

    @action(detail=True, methods=['post'])
    def discontinue(self, request, pk=None):
        sku = self.get_object()
        sku.discontinue()
        return Response(SKUSerializer(sku).data)

    @action(detail=True, methods=['post'])
    def set_cost_price(self, request, pk=None):
        sku = self.get_object()
        cost = request.data.get('cost_price')
        note = request.data.get('note', '')
        sku.set_cost_price(cost, changed_by=request.user, note=note)
        return Response(SKUSerializer(sku).data)

    @action(detail=False, methods=['get'])
    def price_matrix(self, request):
        """SKUs x active channels current-price grid (requirement doc, Inventory #11)."""
        channels = list(Channel.objects.filter(status=Channel.STATUS_ACTIVE))
        rows = []
        for sku in self.filter_queryset(self.get_queryset()):
            prices = {}
            for ch in channels:
                prices[str(ch.id)] = ChannelPrice.current_price(ch.id, sku.id)
            rows.append({
                'sku_id': sku.id, 'sku_code': sku.code, 'sku_name': sku.name,
                'brand_name': sku.brand.name, 'prices': prices,
            })
        return Response({
            'channels': ChannelSerializer(channels, many=True).data,
            'rows': SKUPriceMatrixSerializer(rows, many=True).data,
        })


class ChannelViewSet(viewsets.ModelViewSet):
    """Channel lifecycle management (requirement doc, Distribution #1)."""
    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['channel_type', 'filer_status', 'status']
    search_fields = ['name']

    @action(detail=True, methods=['post'])
    def set_status(self, request, pk=None):
        channel = self.get_object()
        new_status = request.data.get('status')
        if new_status not in dict(Channel.STATUS_CHOICES):
            return Response({'detail': 'invalid status'}, status=400)
        channel.status = new_status
        if new_status == Channel.STATUS_CLOSED:
            channel.closed_on = timezone.localdate()
        channel.save()
        return Response(ChannelSerializer(channel).data)


class ChannelPriceViewSet(viewsets.ModelViewSet):
    """Per-channel, per-SKU price history (append-only; see ChannelPrice.current_price)."""
    queryset = ChannelPrice.objects.select_related('channel', 'sku').all()
    serializer_class = ChannelPriceSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['channel', 'sku']

    def perform_create(self, serializer):
        serializer.save(changed_by=self.request.user)
