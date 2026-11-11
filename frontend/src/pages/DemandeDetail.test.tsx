import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { api, type Demande } from '../api/client';
import { ALICE, BOB, rendreAvecUtilisateur } from '../test/rendu';
import { DemandeDetail } from './DemandeDetail';

function demande(statut: Demande['statut']): Demande {
  return {
    id: 7,
    type: 'GENERIQUE',
    titre: 'Badge parking',
    description: 'Badge à renouveler',
    demandeur: 'alice',
    montant: null,
    dateDebut: '2026-11-16',
    dateFin: null,
    statut,
    niveauValidation: null,
    departement: 'COMMERCIAL',
    urgent: false,
    dateCreation: '2026-10-27T09:12:00',
    dateMaj: '2026-10-27T09:12:00',
    motifRefus: null,
  };
}

function preparer(statut: Demande['statut']) {
  vi.spyOn(api, 'obtenirDemande').mockResolvedValue(demande(statut));
  vi.spyOn(api, 'evenements').mockResolvedValue([
    { id: 1, type: 'CREATION', auteur: 'alice', horodatage: '2026-10-27T09:12:00', commentaire: null },
  ]);
}

describe('DemandeDetail', () => {
  it('permet au demandeur de soumettre son brouillon', async () => {
    preparer('BROUILLON');
    rendreAvecUtilisateur(<DemandeDetail />, ALICE, { route: '/demandes/7', chemin: '/demandes/:id' });

    expect(await screen.findByRole('button', { name: 'Soumettre' })).toBeInTheDocument();
    expect(screen.getByTestId('statut')).toHaveAttribute('data-statut', 'BROUILLON');
    expect(screen.queryByRole('button', { name: 'Valider' })).not.toBeInTheDocument();
  });

  it('propose valider et refuser au valideur sur une demande soumise', async () => {
    preparer('SOUMISE');
    rendreAvecUtilisateur(<DemandeDetail />, BOB, { route: '/demandes/7', chemin: '/demandes/:id' });

    expect(await screen.findByRole('button', { name: 'Valider' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refuser' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Soumettre' })).not.toBeInTheDocument();
    expect(screen.getByText(/CREATION/)).toBeInTheDocument();
  });
});
