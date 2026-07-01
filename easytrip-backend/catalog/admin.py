from django.contrib import admin
from .models import (
    Country, City, Airport, ActivityCategory,
    Hotel, HotelAvailability, Activity, ActivityAvailability, Flight,
)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ['name', 'iso_code']
    search_fields = ['name']


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ['name', 'country']
    list_filter = ['country']
    search_fields = ['name']


@admin.register(Airport)
class AirportAdmin(admin.ModelAdmin):
    list_display = ['iata_code', 'name', 'city']
    search_fields = ['iata_code', 'name']


@admin.register(ActivityCategory)
class ActivityCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']


class HotelAvailabilityInline(admin.TabularInline):
    model = HotelAvailability
    extra = 1


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'stars']
    list_filter = ['city__country', 'stars']
    search_fields = ['name']
    inlines = [HotelAvailabilityInline]


class ActivityAvailabilityInline(admin.TabularInline):
    model = ActivityAvailability
    extra = 1


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'category', 'base_price']
    list_filter = ['city__country', 'category']
    search_fields = ['name']
    inlines = [ActivityAvailabilityInline]


@admin.register(Flight)
class FlightAdmin(admin.ModelAdmin):
    list_display = ['flight_number', 'departure_airport', 'arrival_airport', 'departure_datetime', 'price']
    list_filter = ['departure_airport', 'arrival_airport']
    search_fields = ['flight_number']
