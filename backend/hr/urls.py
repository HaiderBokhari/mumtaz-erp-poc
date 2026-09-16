from rest_framework.routers import DefaultRouter

from .views import EmployeeViewSet, LeaveRequestViewSet, SalaryPaymentViewSet

router = DefaultRouter()
router.register('employees', EmployeeViewSet, basename='employee')
router.register('salary-payments', SalaryPaymentViewSet, basename='salary-payment')
router.register('leave-requests', LeaveRequestViewSet, basename='leave-request')

urlpatterns = router.urls
