import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function AppLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="app-layout">
      <header className="app-header">
        <div className="app-header__brand">EasyTrip</div>
        <nav className="app-nav">
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/chat">Chat</NavLink>
          <NavLink to="/bookings">Prenotazioni</NavLink>
          <NavLink to="/profile">Profilo</NavLink>
        </nav>
        <div className="app-header__user">
          <span>{user?.username}</span>
          <button type="button" onClick={logout}>
            Esci
          </button>
        </div>
      </header>
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  );
}
