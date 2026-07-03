const ROLE_LABELS = {
  user: 'Tu',
  assistant: 'Assistente',
  system: 'Sistema',
};

export default function MessageBubble({ message }) {
  return (
    <div className={`message-bubble message-bubble--${message.role}`}>
      <span className="message-bubble__role">{ROLE_LABELS[message.role] ?? message.role}</span>
      <p>{message.content}</p>
    </div>
  );
}
