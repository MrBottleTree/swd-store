from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.views.static import serve as static_serve
from django.urls import re_path
from . import settings

urlpatterns = [
    path('admin/', admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("core.urls")),
    path('social-auth/', include('social_django.urls', namespace='social')),
    re_path(r'^\.well-known/assetlinks\.json$', static_serve, {
    'path': 'assetlinks.json',
    'document_root': settings.STATIC_ROOT / 'wellknown',
}),
]