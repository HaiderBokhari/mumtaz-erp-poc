from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('api/', include('accounts.urls')),
    path('api/', include('catalog.urls')),
    path('api/', include('warehouses.urls')),
    path('api/', include('purchasing.urls')),
    path('api/', include('distribution.urls')),
    path('api/', include('hr.urls')),
    path('api/reports/', include('reports.urls')),
]
