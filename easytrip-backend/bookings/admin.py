from django.contrib import admin
from .models import Booking, BookingFlight, BookingHotelStay, BookingActivity


class BookingFlightInline(admin.TabularInline):
    model = BookingFlight
    extra = 0


class BookingHotelStayInline(admin.TabularInline):
    model = BookingHotelStay
    extra = 0


class BookingActivityInline(admin.TabularInline):
    model = BookingActivity
    extra = 0


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'country', 'status', 'total_budget', 'travel_month', 'created_at']
    list_filter = ['status', 'country']
    search_fields = ['user__username']
    inlines = [BookingFlightInline, BookingHotelStayInline, BookingActivityInline]
