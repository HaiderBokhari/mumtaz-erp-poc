from rest_framework.routers import DefaultRouter

from .views import BrandViewSet, ChannelPriceViewSet, ChannelViewSet, SKUViewSet

router = DefaultRouter()
router.register('brands', BrandViewSet, basename='brand')
router.register('skus', SKUViewSet, basename='sku')
router.register('channels', ChannelViewSet, basename='channel')
router.register('channel-prices', ChannelPriceViewSet, basename='channel-price')

urlpatterns = router.urls
