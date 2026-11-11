// Traduction « moderne » typique proposée par un modèle sans contrainte de parité (Intl, toLocaleDateString).
// Réponse simulée « naive » du lab legacy-ia (option --variante naive).
const euros = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' });

export function formatMontant(m: number | null | undefined): string {
  return m == null ? '-' : euros.format(m);
}

export function formatDate(d: Date | string | number | null | undefined): string {
  return d ? new Date(d).toLocaleDateString('fr-FR') : '';
}

export function joursOuvres(debut: Date | string | number, fin: Date | string | number): number {
  let n = 0;
  for (const d = new Date(debut); d <= new Date(fin); d.setDate(d.getDate() + 1)) {
    if (d.getDay() % 6 !== 0) n++;
  }
  return n;
}

export default { formatMontant, formatDate, joursOuvres };
