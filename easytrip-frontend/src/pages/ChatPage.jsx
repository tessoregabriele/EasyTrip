import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { listConversations, getConversation, createConversation, sendMessage } from '../api/chat';
import ConversationSidebar from '../components/chat/ConversationSidebar';
import MessageBubble from '../components/chat/MessageBubble';
import ItineraryCard from '../components/chat/ItineraryCard';

const CONFERMA_ITINERARIO_MESSAGE =
  "Confermo l'itinerario proposto in tutti i suoi componenti (voli, hotel e attività): procedi pure con la prenotazione.";

export default function ChatPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState([]);
  const [conversation, setConversation] = useState(null);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(true);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    listConversations().then(setConversations);
  }, [conversationId]);

  useEffect(() => {
    if (!conversationId) {
      setConversation(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    getConversation(conversationId)
      .then(setConversation)
      .finally(() => setLoading(false));
  }, [conversationId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation?.messages?.length]);

  async function handleNewChat() {
    const created = await createConversation();
    setConversations((prev) => [created, ...prev]);
    navigate(`/chat/${created.id}`);
  }

  // Invia un messaggio (scritto dall'utente o generato dal pulsante di
  // conferma) e poi ricarica l'intera conversazione dal server: è più
  // semplice che tenere sincronizzati a mano i messaggi e il campo
  // `booking`/`pending_itinerary`, che cambiano entrambi lato server quando
  // l'assistente conferma la prenotazione.
  async function submitMessage(content) {
    let activeConversationId = conversationId;
    if (!activeConversationId) {
      const created = await createConversation();
      setConversations((prev) => [created, ...prev]);
      activeConversationId = created.id;
      navigate(`/chat/${created.id}`, { replace: true });
    }

    const optimisticUserMessage = { id: `local-${Date.now()}`, role: 'user', content, metadata: {} };
    setConversation((prev) => ({
      ...(prev ?? { id: activeConversationId, messages: [] }),
      messages: [...(prev?.messages ?? []), optimisticUserMessage],
    }));

    await sendMessage(activeConversationId, content);
    const refreshed = await getConversation(activeConversationId);
    setConversation(refreshed);
  }

  async function handleSend(e) {
    e.preventDefault();
    const content = draft.trim();
    if (!content) return;
    setDraft('');
    setSending(true);
    try {
      await submitMessage(content);
    } finally {
      setSending(false);
    }
  }

  async function handleConfirmItinerary() {
    setConfirming(true);
    try {
      await submitMessage(CONFERMA_ITINERARIO_MESSAGE);
    } finally {
      setConfirming(false);
    }
  }

  const lastMessage = conversation?.messages?.[conversation.messages.length - 1];
  const pendingItinerary = lastMessage?.metadata?.itinerario_proposto;

  return (
    <div className="chat-page">
      <ConversationSidebar
        conversations={conversations}
        activeId={conversationId ? Number(conversationId) : null}
        onNewChat={handleNewChat}
      />
      <div className="chat-main">
        {loading ? (
          <p>Caricamento...</p>
        ) : (
          <>
            <div className="chat-messages">
              {!conversation && <p>Scrivi un messaggio per iniziare una nuova conversazione.</p>}
              {conversation?.messages?.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}
              {pendingItinerary && (
                <ItineraryCard
                  itinerary={pendingItinerary}
                  onConfirm={handleConfirmItinerary}
                  confirming={confirming}
                />
              )}
              {conversation?.booking && (
                <p>
                  Prenotazione creata: <Link to={`/bookings/${conversation.booking}`}>vai al dettaglio →</Link>
                </p>
              )}
              <div ref={messagesEndRef} />
            </div>
            <form className="chat-input" onSubmit={handleSend}>
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Scrivi un messaggio..."
                disabled={sending}
              />
              <button type="submit" disabled={sending || !draft.trim()}>
                {sending ? 'Invio...' : 'Invia'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
