from django.contrib import admin
from django.urls import path, include
from saa_collector import views as collector_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('saa_collector.urls')),
    path('health/', collector_views.health_check),
]
