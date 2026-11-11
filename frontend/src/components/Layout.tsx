import { Link, Outlet } from 'react-router-dom';

import { useAuth } from '../auth/auth';

export function Layout() {
  const { utilisateur, deconnecter } = useAuth();

  return (
    <div className="app">
      <header className="entete">
        <Link to="/demandes" className="logo">
          NeoFlow
        </Link>
        {utilisateur && (
          <div className="session">
            <span>
              {utilisateur.login} ({utilisateur.roles.join(', ')})
            </span>
            <button
              type="button"
              className="secondaire"
              onClick={() => {
                deconnecter();
                // Rechargement complet : aucun état de l'utilisateur précédent n'est conservé.
                window.location.assign('/connexion');
              }}
            >
              Se déconnecter
            </button>
          </div>
        )}
      </header>
      <main className="contenu">
        <Outlet />
      </main>
    </div>
  );
}
