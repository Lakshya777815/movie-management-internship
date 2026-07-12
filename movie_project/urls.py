from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('movies.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # the warning from before was about static files dir not being created; 
    # it's usually not served from STATICFILES_DIRS when using runserver and setting static correctly, 
    # but the static url fallback is useful if we need it. 
