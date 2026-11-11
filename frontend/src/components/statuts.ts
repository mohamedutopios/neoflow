import type { StatutDemande } from '../api/client';

const LIBELLES: Record<StatutDemande, string> = {
  BROUILLON: 'Brouillon',
  SOUMISE: 'Soumise',
  VALIDEE: 'Validée',
  REFUSEE: 'Refusée',
  CLOTUREE: 'Clôturée',
};

export function libelleStatut(statut: StatutDemande): string {
  return LIBELLES[statut];
}
