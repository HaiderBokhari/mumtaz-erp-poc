from rest_framework.routers import DefaultRouter

from .views import PurchaseOrderViewSet, PurchaseReturnViewSet

router = DefaultRouter()
router.register('purchase-orders', PurchaseOrderViewSet, basename='purchase-order')
router.register('purchase-returns', PurchaseReturnViewSet, basename='purchase-return')

urlpatterns = router.urls
