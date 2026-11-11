import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { aDesIdentifiants, api, effacerIdentifiants, enregistrerIdentifiants, type Utilisateur } from '../api/client';
import { AuthContext, type EtatAuth } from './auth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [utilisateur, setUtilisateur] = useState<Utilisateur | null>(null);
  const [chargement, setChargement] = useState(aDesIdentifiants());

  // Restaure la session après un rechargement de page.
  useEffect(() => {
    if (!aDesIdentifiants()) return;
    api
      .moi()
      .then(setUtilisateur)
      .catch(() => effacerIdentifiants())
      .finally(() => setChargement(false));
  }, []);

  const connecter = useCallback(async (login: string, motDePasse: string) => {
    enregistrerIdentifiants(login, motDePasse);
    try {
      setUtilisateur(await api.moi());
    } catch (erreur) {
      effacerIdentifiants();
      throw erreur;
    }
  }, []);

  const deconnecter = useCallback(() => {
    effacerIdentifiants();
    setUtilisateur(null);
  }, []);

  const valeur = useMemo<EtatAuth>(
    () => ({
      utilisateur,
      chargement,
      connecter,
      deconnecter,
      aLeRole: (role) => utilisateur?.roles.includes(role) ?? false,
    }),
    [utilisateur, chargement, connecter, deconnecter],
  );

  return <AuthContext.Provider value={valeur}>{children}</AuthContext.Provider>;
}
