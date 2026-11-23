from rest_framework.routers import DefaultRouter

from .views import (
    ActualSaleViewSet, DRSettlementViewSet, PaymentReceiptViewSet, SalesOrderViewSet, SalesReturnViewSet,
    SalesTargetViewSet, ShopViewSet,
)

router = DefaultRouter()
router.register('shops', ShopViewSet, basename='shop')
router.register('sales-orders', SalesOrderViewSet, basename='sales-order')
router.register('sales-returns', SalesReturnViewSet, basename='sales-return')
router.register('payment-receipts', PaymentReceiptViewSet, basename='payment-receipt')
router.register('sales-targets', SalesTargetViewSet, basename='sales-target')
router.register('dr-settlements', DRSettlementViewSet, basename='dr-settlement')
router.register('actual-sales', ActualSaleViewSet, basename='actual-sale')

urlpatterns = router.urls
