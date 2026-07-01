from rest_framework import serializers
from django.db import transaction
from catalog.models import Country, Flight, Hotel, Activity
from .models import Booking, BookingFlight, BookingHotelStay, BookingActivity


class BookingFlightSerializer(serializers.ModelSerializer):
    flight_id = serializers.PrimaryKeyRelatedField(
        queryset=Flight.objects.all(), source='flight', write_only=True
    )
    flight_number = serializers.CharField(source='flight.flight_number', read_only=True)
    departure_airport = serializers.CharField(source='flight.departure_airport.iata_code', read_only=True)
    arrival_airport = serializers.CharField(source='flight.arrival_airport.iata_code', read_only=True)
    departure_datetime = serializers.DateTimeField(source='flight.departure_datetime', read_only=True)
    arrival_datetime = serializers.DateTimeField(source='flight.arrival_datetime', read_only=True)

    class Meta:
        model = BookingFlight
        fields = [
            'id', 'flight_id', 'direction', 'price',
            'flight_number', 'departure_airport', 'arrival_airport',
            'departure_datetime', 'arrival_datetime',
        ]


class BookingHotelStaySerializer(serializers.ModelSerializer):
    hotel_id = serializers.PrimaryKeyRelatedField(
        queryset=Hotel.objects.all(), source='hotel', write_only=True
    )
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)

    class Meta:
        model = BookingHotelStay
        fields = ['id', 'hotel_id', 'hotel_name', 'date', 'price_per_night']


class BookingActivitySerializer(serializers.ModelSerializer):
    activity_id = serializers.PrimaryKeyRelatedField(
        queryset=Activity.objects.all(), source='activity', write_only=True
    )
    activity_name = serializers.CharField(source='activity.name', read_only=True)

    class Meta:
        model = BookingActivity
        fields = ['id', 'activity_id', 'activity_name', 'date', 'price']


class BookingSerializer(serializers.ModelSerializer):
    """
    Serializer principale per la prenotazione/itinerario completo.
    In lettura espone i dettagli annidati di volo/hotel/attività.
    In scrittura accetta le liste nidificate e crea tutto in una transazione.
    """
    flights = BookingFlightSerializer(many=True)
    hotel_stays = BookingHotelStaySerializer(many=True)
    activities = BookingActivitySerializer(many=True)

    country_id = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(), source='country', write_only=True
    )
    country = serializers.StringRelatedField(read_only=True)
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'user', 'status', 'country', 'country_id',
            'total_budget', 'requested_activity_preferences', 'travel_month',
            'flights', 'hotel_stays', 'activities', 'total_cost',
            'created_at', 'updated_at', 'confirmed_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'confirmed_at']

    def validate(self, attrs):
        flights = attrs.get('flights', [])
        directions = [f['direction'] for f in flights]
        if len(directions) != len(set(directions)):
            raise serializers.ValidationError(
                "Non possono esserci due voli con la stessa direzione (andata/ritorno) nello stesso itinerario."
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        flights_data = validated_data.pop('flights')
        hotel_stays_data = validated_data.pop('hotel_stays')
        activities_data = validated_data.pop('activities')

        user = self.context['request'].user
        booking = Booking.objects.create(user=user, **validated_data)

        for flight_data in flights_data:
            BookingFlight.objects.create(booking=booking, **flight_data)
        for stay_data in hotel_stays_data:
            BookingHotelStay.objects.create(booking=booking, **stay_data)
        for activity_data in activities_data:
            BookingActivity.objects.create(booking=booking, **activity_data)

        return booking

    @transaction.atomic
    def update(self, instance, validated_data):
        # Aggiornamento dell'itinerario: sostituisce interamente le sotto-liste
        # se fornite (semplice e prevedibile; coerente con "modifica itinerario
        # già prenotato" come funzionalità opzionale futura).
        flights_data = validated_data.pop('flights', None)
        hotel_stays_data = validated_data.pop('hotel_stays', None)
        activities_data = validated_data.pop('activities', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if flights_data is not None:
            instance.flights.all().delete()
            for flight_data in flights_data:
                BookingFlight.objects.create(booking=instance, **flight_data)

        if hotel_stays_data is not None:
            instance.hotel_stays.all().delete()
            for stay_data in hotel_stays_data:
                BookingHotelStay.objects.create(booking=instance, **stay_data)

        if activities_data is not None:
            instance.activities.all().delete()
            for activity_data in activities_data:
                BookingActivity.objects.create(booking=instance, **activity_data)

        return instance


class BookingListSerializer(serializers.ModelSerializer):
    """Versione leggera per la lista prenotazioni (dashboard utente), senza dettagli annidati pesanti."""
    country = serializers.StringRelatedField(read_only=True)
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Booking
        fields = ['id', 'status', 'country', 'total_budget', 'total_cost', 'travel_month', 'created_at']
