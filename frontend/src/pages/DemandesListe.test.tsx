import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, type Demande } from '../api/client';
import { ALICE, BOB, rendreAvecUtilisateur } from '../test/rendu';
import { DemandesListe } from './DemandesListe';

const DEMANDE: Demande = {
  id: 2,
  type: 'NOTE_DE_FRAIS',
  titre: 'Déjeuner client Lyon',
  description: null,
  demandeur: 'alice',
  montant: 1286.4,
  dateDebut: '2026-10-08',
  dateFin: null,
  statut: 'SOUMISE',
  niveauValidation: 1,
  departement: 'COMMERCIAL',
  urgent: false,
  dateCreation: '2026-10-09T18:20:00',
  dateMaj: '2026-10-09T18:25:00',
  motifRefus: null,
};

describe('DemandesListe', () => {
  beforeEach(() => {
    vi.spyOn(api, 'listerDemandes').mockResolvedValue({
      content: [DEMANDE],
      page: { size: 10, number: 0, totalElements: 1, totalPages: 1 },
    });
  });

  it('affiche les demandes avec le montant formaté par NeoUtils', async () => {
    rendreAvecUtilisateur(<DemandesListe />, ALICE);

    expect(await screen.findByRole('link', { name: 'Déjeuner client Lyon' })).toBeInTheDocument();
    expect(screen.getByText('1 286,40 €')).toBeInTheDocument();
    expect(api.listerDemandes).toHaveBeenCalledWith({ statut: '', type: '', page: 0, size: 10 });
  });

  it('propose la création uniquement au rôle DEMANDEUR', async () => {
    rendreAvecUtilisateur(<DemandesListe />, BOB);

    await screen.findByRole('link', { name: 'Déjeuner client Lyon' });
    expect(screen.queryByRole('link', { name: 'Nouvelle demande' })).not.toBeInTheDocument();
  });
});
