import django_filters
from .models import Hotel, Activity, Flight


class HotelFilter(django_filters.FilterSet):
    city = django_filters.NumberFilter(field_name='city__id')
    country = django_filters.NumberFilter(field_name='city__country__id')
    min_stars = django_filters.NumberFilter(field_name='stars', lookup_expr='gte')
    available_from = django_filters.DateFilter(field_name='availabilities__date', lookup_expr='gte')
    available_to = django_filters.DateFilter(field_name='availabilities__date', lookup_expr='lte')
    max_price_per_night = django_filters.NumberFilter(field_name='availabilities__price_per_night', lookup_expr='lte')

    class Meta:
        model = Hotel
        fields = ['city', 'country', 'min_stars', 'available_from', 'available_to', 'max_price_per_night']


class ActivityFilter(django_filters.FilterSet):
    city = django_filters.NumberFilter(field_name='city__id')
    country = django_filters.NumberFilter(field_name='city__country__id')
    category = django_filters.NumberFilter(field_name='category__id')
    category_slug = django_filters.CharFilter(field_name='category__slug')
    date = django_filters.DateFilter(field_name='availabilities__date')
    max_price = django_filters.NumberFilter(field_name='base_price', lookup_expr='lte')

    class Meta:
        model = Activity
        fields = ['city', 'country', 'category', 'category_slug', 'date', 'max_price']


class FlightFilter(django_filters.FilterSet):
    departure_airport = django_filters.CharFilter(field_name='departure_airport__iata_code')
    arrival_airport = django_filters.CharFilter(field_name='arrival_airport__iata_code')
    date_from = django_filters.DateFilter(field_name='departure_datetime', lookup_expr='date__gte')
    date_to = django_filters.DateFilter(field_name='departure_datetime', lookup_expr='date__lte')
    max_price = django_filters.NumberFilter(field_name='price', lookup_expr='lte')

    class Meta:
        model = Flight
        fields = ['departure_airport', 'arrival_airport', 'date_from', 'date_to', 'max_price']
