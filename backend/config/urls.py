from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, re_path
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

# In a deployment that serves the built React SPA alongside the API
# (WHITENOISE_ROOT set — see settings.py), any path WhiteNoise doesn't
# recognize as a static file falls through to here. That's a client-side
# route (e.g. a deep link or refresh on /sales-orders), so serve the SPA's
# index.html and let React Router take over. Local dev (Vite on :5173)
# never hits this.
if getattr(settings, 'WHITENOISE_ROOT', None):
    def _spa_index(request):
        return HttpResponse((settings.WHITENOISE_ROOT / 'index.html').read_text())

    urlpatterns.append(re_path(r'^(?!admin/|api/|static/).*$', _spa_index))
