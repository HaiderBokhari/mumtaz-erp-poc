from rest_framework.routers import DefaultRouter

from .views import (
    AccountGroupViewSet, ChartOfAccountViewSet, FinancialStatementsViewSet,
    JournalEntryViewSet, PartyViewSet, VoucherViewSet,
)

router = DefaultRouter()
router.register('account-groups', AccountGroupViewSet, basename='account-group')
router.register('chart-of-accounts', ChartOfAccountViewSet, basename='chart-of-account')
router.register('parties', PartyViewSet, basename='party')
router.register('vouchers', VoucherViewSet, basename='voucher')
router.register('journal-entries', JournalEntryViewSet, basename='journal-entry')
router.register('statements', FinancialStatementsViewSet, basename='statement')

urlpatterns = router.urls
