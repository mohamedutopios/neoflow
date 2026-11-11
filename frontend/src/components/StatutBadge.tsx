import type { StatutDemande } from '../api/client';
import { libelleStatut } from './statuts';

export function StatutBadge({ statut, testId }: { statut: StatutDemande; testId?: string }) {
  return (
    <span className={`badge badge-${statut.toLowerCase()}`} data-statut={statut} data-testid={testId}>
      {libelleStatut(statut)}
    </span>
  );
}
