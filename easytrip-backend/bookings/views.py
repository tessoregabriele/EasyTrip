from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from catalog.models import Flight, HotelAvailability, ActivityAvailability
from .models import Booking
from .serializers import BookingSerializer, BookingListSerializer


class BookingViewSet(viewsets.ModelViewSet):
    """
    CRUD per le prenotazioni. Ogni utente vede e gestisce solo le proprie
    prenotazioni (isolamento per utente, niente accesso cross-user).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Booking.objects.filter(user=self.request.user)
            .select_related('country', 'user')
            .prefetch_related(
                'flights', 'flights__flight',
                'flights__flight__departure_airport', 'flights__flight__arrival_airport',
                'hotel_stays', 'hotel_stays__hotel',
                'activities', 'activities__activity',
            )
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return BookingListSerializer
        return BookingSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Conferma una prenotazione in stato 'draft' (azione di prenotazione tramite chat/UI)."""
        booking = self.get_object()
        if booking.status != Booking.Status.CONFIRMED:
            booking.status = Booking.Status.CONFIRMED
            booking.confirmed_at = timezone.now()
            booking.save()
        serializer = BookingSerializer(booking, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Annulla una prenotazione e rilascia l'inventario che era stato
        bloccato al momento della conferma (posti volo, camere hotel, spot
        attività - vedi esegui_conferma_itinerario_finale in
        chat/llm/tools.py, che li decrementa), così tornano disponibili per
        altre prenotazioni. Idempotente: se è già cancellata non rilascia
        una seconda volta.
        """
        booking = self.get_object()
        if booking.status != Booking.Status.CANCELLED:
            with transaction.atomic():
                for booking_flight in booking.flights.all():
                    Flight.objects.filter(id=booking_flight.flight_id).update(
                        seats_available=F("seats_available") + 1
                    )
                for stay in booking.hotel_stays.all():
                    HotelAvailability.objects.filter(
                        hotel_id=stay.hotel_id, date=stay.date,
                    ).update(rooms_available=F("rooms_available") + 1)
                for booking_activity in booking.activities.all():
                    ActivityAvailability.objects.filter(
                        activity_id=booking_activity.activity_id, date=booking_activity.date,
                    ).update(spots_available=F("spots_available") + 1)

                booking.status = Booking.Status.CANCELLED
                booking.save()
        serializer = BookingSerializer(booking, context=self.get_serializer_context())
        return Response(serializer.data)
