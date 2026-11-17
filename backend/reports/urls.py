from django.urls import path

from .views import CompanyVsActualView, DashboardView, DRPayoutView, MadamRegisterView

urlpatterns = [
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('company-vs-actual/', CompanyVsActualView.as_view(), name='company-vs-actual'),
    path('dr-payout/', DRPayoutView.as_view(), name='dr-payout'),
    path('madam-register/', MadamRegisterView.as_view(), name='madam-register'),
]
