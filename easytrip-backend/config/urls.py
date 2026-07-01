from django.contrib import admin
from django.urls import path, include

admin.site.site_header = "EasyTrip Admin"
admin.site.site_title = "EasyTrip Admin"
admin.site.index_title = "Gestione EasyTrip"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('users.urls')),
    path('api/', include('catalog.urls')),
    path('api/', include('bookings.urls')),
    path('api/', include('chat.urls')),
]
