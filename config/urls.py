from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.views import manifest_json, service_worker, favicon_redirect

urlpatterns = [
    path('manifest.json', manifest_json),
    path('sw.js', service_worker),
    path('favicon.ico', favicon_redirect),
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
]

handler404 = 'core.views.page_not_found'
handler500 = 'core.views.server_error'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
