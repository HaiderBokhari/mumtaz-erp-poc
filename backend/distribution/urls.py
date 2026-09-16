from rest_framework.routers import DefaultRouter

from .views import (
    PaymentReceiptViewSet, SalesOrderViewSet, SalesReturnViewSet,
    SalesTargetViewSet, ShopViewSet,
)

router = DefaultRouter()
router.register('shops', ShopViewSet, basename='shop')
router.register('sales-orders', SalesOrderViewSet, basename='sales-order')
router.register('sales-returns', SalesReturnViewSet, basename='sales-return')
router.register('payment-receipts', PaymentReceiptViewSet, basename='payment-receipt')
router.register('sales-targets', SalesTargetViewSet, basename='sales-target')

urlpatterns = router.urls
