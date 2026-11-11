import { createContext, useContext } from 'react';

import type { Role, Utilisateur } from '../api/client';

export interface EtatAuth {
  utilisateur: Utilisateur | null;
  chargement: boolean;
  connecter: (login: string, motDePasse: string) => Promise<void>;
  deconnecter: () => void;
  aLeRole: (role: Role) => boolean;
}

export const AuthContext = createContext<EtatAuth | null>(null);

export function useAuth(): EtatAuth {
  const contexte = useContext(AuthContext);
  if (!contexte) {
    throw new Error('useAuth doit être utilisé dans un AuthProvider');
  }
  return contexte;
}
