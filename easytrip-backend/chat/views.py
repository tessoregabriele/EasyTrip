from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Conversation, Message
from .serializers import ConversationSerializer, ConversationListSerializer, MessageSerializer
from .llm.orchestrator import handle_user_message


class ConversationViewSet(viewsets.ModelViewSet):
    """
    CRUD per le conversazioni. Ogni utente vede solo le proprie.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user).prefetch_related('messages')

    def get_serializer_class(self):
        if self.action == 'list':
            return ConversationListSerializer
        return ConversationSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """
        Invia un messaggio dell'utente nella conversazione e fa rispondere
        l'assistente: l'orchestratore (chat/llm/orchestrator.py) si occupa
        del ciclo di conversazione con l'LLM, incluse eventuali tool call
        per la generazione dell'itinerario o la ricerca di attività.

        Ritorna il messaggio dell'assistente generato (non quello
        dell'utente, già noto al client che l'ha inviato).
        """
        conversation = self.get_object()
        content = request.data.get('content', '').strip()
        if not content:
            return Response(
                {"detail": "Il campo 'content' è obbligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            assistant_message = handle_user_message(conversation, content)
        except RuntimeError as e:
            # Tipicamente: provider LLM non configurato (manca la API key nel .env)
            return Response(
                {"detail": f"Assistente non disponibile: {e}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = MessageSerializer(assistant_message)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
