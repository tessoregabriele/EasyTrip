from rest_framework import viewsets, permissions
from .models import (
    Country, City, Airport, ActivityCategory,
    Hotel, Activity, Flight,
)
from .serializers import (
    CountrySerializer, CitySerializer, AirportSerializer, ActivityCategorySerializer,
    HotelSerializer, ActivitySerializer, FlightSerializer,
)
from .filters import HotelFilter, ActivityFilter, FlightFilter


class CountryViewSet(viewsets.ReadOnlyModelViewSet):
    """Elenco delle nazioni disponibili (lettura pubblica per popolare select nel frontend)."""
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    permission_classes = [permissions.AllowAny]


class CityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = City.objects.select_related('country').all()
    serializer_class = CitySerializer
    permission_classes = [permissions.AllowAny]
    filterset_fields = ['country']


class AirportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Airport.objects.select_related('city', 'city__country').all()
    serializer_class = AirportSerializer
    permission_classes = [permissions.AllowAny]
    filterset_fields = ['city']


class ActivityCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ActivityCategory.objects.all()
    serializer_class = ActivityCategorySerializer
    permission_classes = [permissions.AllowAny]


class HotelViewSet(viewsets.ModelViewSet):
    """
    CRUD completo per gli hotel. Lettura pubblica (serve al frontend per
    mostrare i risultati anche prima del login), scrittura riservata allo staff.
    """
    queryset = Hotel.objects.select_related('city', 'city__country').prefetch_related('availabilities').all()
    serializer_class = HotelSerializer
    filterset_class = HotelFilter

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]


class ActivityViewSet(viewsets.ModelViewSet):
    queryset = Activity.objects.select_related('city', 'category').prefetch_related('availabilities').all()
    serializer_class = ActivitySerializer
    filterset_class = ActivityFilter

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]


class FlightViewSet(viewsets.ModelViewSet):
    queryset = Flight.objects.select_related(
        'departure_airport', 'arrival_airport',
        'departure_airport__city', 'arrival_airport__city',
    ).all()
    serializer_class = FlightSerializer
    filterset_class = FlightFilter

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]
