import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';

import type { Role, Utilisateur } from '../api/client';
import { AuthContext, type EtatAuth } from '../auth/auth';

/** Rend un composant sous une route donnée avec un utilisateur connecté simulé. */
export function rendreAvecUtilisateur(
  element: ReactElement,
  utilisateur: Utilisateur,
  { route = '/', chemin = '/' }: { route?: string; chemin?: string } = {},
) {
  const auth: EtatAuth = {
    utilisateur,
    chargement: false,
    connecter: vi.fn(),
    deconnecter: vi.fn(),
    aLeRole: (role: Role) => utilisateur.roles.includes(role),
  };
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={[route]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path={chemin} element={element} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

export const ALICE: Utilisateur = { login: 'alice', roles: ['DEMANDEUR'], departement: 'COMMERCIAL' };
export const BOB: Utilisateur = { login: 'bob', roles: ['VALIDEUR'], departement: 'FINANCE' };
