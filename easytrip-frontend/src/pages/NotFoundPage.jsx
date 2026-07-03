import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="not-found-page">
      <h1>Pagina non trovata</h1>
      <Link to="/">Torna alla dashboard</Link>
    </div>
  );
}
