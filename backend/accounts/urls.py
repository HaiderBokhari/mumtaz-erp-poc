from rest_framework.routers import DefaultRouter

from .views import GroupViewSet, MeView, UserViewSet

router = DefaultRouter()
router.register('users', UserViewSet, basename='user')
router.register('roles', GroupViewSet, basename='role')
router.register('me', MeView, basename='me')

urlpatterns = router.urls
