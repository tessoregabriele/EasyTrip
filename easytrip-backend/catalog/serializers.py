from rest_framework import serializers
from .models import (
    Country, City, Airport, ActivityCategory,
    Hotel, HotelAvailability, Activity, ActivityAvailability, Flight,
)


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ['id', 'name', 'iso_code']


class CitySerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)
    country_id = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(), source='country', write_only=True
    )

    class Meta:
        model = City
        fields = ['id', 'name', 'country', 'country_id', 'latitude', 'longitude']


class AirportSerializer(serializers.ModelSerializer):
    city = CitySerializer(read_only=True)
    city_id = serializers.PrimaryKeyRelatedField(
        queryset=City.objects.all(), source='city', write_only=True
    )

    class Meta:
        model = Airport
        fields = ['id', 'iata_code', 'name', 'city', 'city_id']


class ActivityCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityCategory
        fields = ['id', 'name', 'slug']


class HotelAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = HotelAvailability
        fields = ['id', 'hotel', 'date', 'price_per_night', 'rooms_available']


class HotelSerializer(serializers.ModelSerializer):
    city = CitySerializer(read_only=True)
    city_id = serializers.PrimaryKeyRelatedField(
        queryset=City.objects.all(), source='city', write_only=True
    )
    availabilities = HotelAvailabilitySerializer(many=True, read_only=True)

    class Meta:
        model = Hotel
        fields = [
            'id', 'name', 'city', 'city_id', 'address', 'stars',
            'description', 'target_audience', 'availabilities',
        ]


class ActivityAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityAvailability
        fields = ['id', 'activity', 'date', 'price', 'spots_available']


class ActivitySerializer(serializers.ModelSerializer):
    city = CitySerializer(read_only=True)
    city_id = serializers.PrimaryKeyRelatedField(
        queryset=City.objects.all(), source='city', write_only=True
    )
    category = ActivityCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ActivityCategory.objects.all(), source='category', write_only=True
    )
    availabilities = ActivityAvailabilitySerializer(many=True, read_only=True)

    class Meta:
        model = Activity
        fields = [
            'id', 'name', 'city', 'city_id', 'category', 'category_id',
            'description', 'duration_minutes', 'base_price',
            'target_audience', 'availabilities',
        ]


class FlightSerializer(serializers.ModelSerializer):
    departure_airport = AirportSerializer(read_only=True)
    arrival_airport = AirportSerializer(read_only=True)
    departure_airport_id = serializers.PrimaryKeyRelatedField(
        queryset=Airport.objects.all(), source='departure_airport', write_only=True
    )
    arrival_airport_id = serializers.PrimaryKeyRelatedField(
        queryset=Airport.objects.all(), source='arrival_airport', write_only=True
    )

    class Meta:
        model = Flight
        fields = [
            'id', 'flight_number',
            'departure_airport', 'departure_airport_id',
            'arrival_airport', 'arrival_airport_id',
            'departure_datetime', 'arrival_datetime',
            'price', 'seats_available',
        ]
