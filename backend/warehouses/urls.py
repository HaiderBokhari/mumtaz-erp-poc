from rest_framework.routers import DefaultRouter

from .views import (
    SafetyStockLevelViewSet, StockAdjustmentViewSet, StockLedgerEntryViewSet,
    StockLevelViewSet, StockTransferViewSet, WarehouseViewSet,
)

router = DefaultRouter()
router.register('warehouses', WarehouseViewSet, basename='warehouse')
router.register('stock-levels', StockLevelViewSet, basename='stock-level')
router.register('stock-ledger', StockLedgerEntryViewSet, basename='stock-ledger')
router.register('stock-transfers', StockTransferViewSet, basename='stock-transfer')
router.register('stock-adjustments', StockAdjustmentViewSet, basename='stock-adjustment')
router.register('safety-stock-levels', SafetyStockLevelViewSet, basename='safety-stock-level')

urlpatterns = router.urls
