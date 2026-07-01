from django.contrib import admin
from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ['created_at']


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'title', 'booking', 'has_pending_itinerary', 'updated_at']
    search_fields = ['user__username', 'title']
    readonly_fields = ['pending_itinerary']
    inlines = [MessageInline]

    def has_pending_itinerary(self, obj):
        return bool(obj.pending_itinerary)
    has_pending_itinerary.short_description = "Itinerario in revisione"
    has_pending_itinerary.boolean = True
