import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useAuth } from '../auth/auth';

export function RouteProtegee({ children }: { children: ReactNode }) {
  const { utilisateur, chargement } = useAuth();
  const location = useLocation();

  if (chargement) {
    return <p>Chargement…</p>;
  }
  if (!utilisateur) {
    return <Navigate to="/connexion" replace state={{ depuis: location.pathname }} />;
  }
  return <>{children}</>;
}
