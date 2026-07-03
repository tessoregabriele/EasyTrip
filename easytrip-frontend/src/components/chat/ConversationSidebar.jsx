import { Link } from 'react-router-dom';

export default function ConversationSidebar({ conversations, activeId, onNewChat }) {
  return (
    <aside className="chat-sidebar">
      <button type="button" onClick={onNewChat}>
        + Nuova chat
      </button>
      <ul>
        {conversations.map((c) => (
          <li key={c.id} className={c.id === activeId ? 'active' : ''}>
            <Link to={`/chat/${c.id}`}>{c.title || `Conversazione #${c.id}`}</Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}
