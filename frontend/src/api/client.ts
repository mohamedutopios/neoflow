// Client de l'API NeoFlow (backend Spring Boot, relayé par le proxy Vite ou nginx sur /api).
// Authentification HTTP Basic : les identifiants encodés sont conservés en sessionStorage.

export const STATUTS_DEMANDE = ['BROUILLON', 'SOUMISE', 'VALIDEE', 'REFUSEE', 'CLOTUREE'] as const;
export type StatutDemande = (typeof STATUTS_DEMANDE)[number];

export const TYPES_DEMANDE = [
  'GENERIQUE',
  'CONGES',
  'NOTE_DE_FRAIS',
  'MATERIEL_IT',
  'RESERVATION_SALLE',
  'FORMATION',
  'ACCES_APPLICATIF',
  'DEPLACEMENT',
  'ACHAT',
  'INCIDENT',
  'ONBOARDING',
] as const;
export type TypeDemande = (typeof TYPES_DEMANDE)[number];

export type Role = 'DEMANDEUR' | 'VALIDEUR' | 'ADMIN';

export interface Demande {
  id: number;
  type: TypeDemande;
  titre: string;
  description: string | null;
  demandeur: string;
  montant: number | null;
  dateDebut: string;
  dateFin: string | null;
  statut: StatutDemande;
  niveauValidation: number | null;
  departement: string | null;
  urgent: boolean;
  dateCreation: string;
  dateMaj: string;
  motifRefus: string | null;
}

/** Corps de POST /api/demandes et PUT /api/demandes/{id}. */
export interface DemandeSaisie {
  type: TypeDemande;
  titre: string;
  description?: string | null;
  montant?: number | null;
  dateDebut: string;
  dateFin?: string | null;
  departement?: string | null;
  urgent: boolean;
}

export interface Evenement {
  id: number;
  type: 'CREATION' | 'SOUMISSION' | 'VALIDATION' | 'REFUS' | 'CLOTURE';
  auteur: string;
  horodatage: string;
  commentaire: string | null;
}

/** Page Spring Data (page 0-based). */
export interface PageDemandes {
  content: Demande[];
  page: { size: number; number: number; totalElements: number; totalPages: number };
}

export interface Utilisateur {
  login: string;
  roles: Role[];
  departement: string | null;
}

export interface FiltresDemandes {
  statut?: StatutDemande | '';
  type?: TypeDemande | '';
  page?: number;
  size?: number;
}

/** Erreur HTTP traduite depuis un ProblemDetail (RFC 9457). */
export class ApiError extends Error {
  readonly status: number;
  readonly erreurs: string[];

  constructor(status: number, message: string, erreurs: string[] = []) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.erreurs = erreurs;
  }
}

const CLE_SESSION = 'neoflow.auth';

export function enregistrerIdentifiants(login: string, motDePasse: string): void {
  sessionStorage.setItem(CLE_SESSION, btoa(`${login}:${motDePasse}`));
}

export function effacerIdentifiants(): void {
  sessionStorage.removeItem(CLE_SESSION);
}

export function aDesIdentifiants(): boolean {
  return sessionStorage.getItem(CLE_SESSION) !== null;
}

interface ProblemDetail {
  title?: string;
  detail?: string;
  erreurs?: string[];
}

async function requete<T>(chemin: string, options: RequestInit = {}): Promise<T> {
  const entetes = new Headers(options.headers);
  entetes.set('Accept', 'application/json');
  // Évite la fenêtre d'authentification native du navigateur sur une réponse 401.
  entetes.set('X-Requested-With', 'XMLHttpRequest');
  const jeton = sessionStorage.getItem(CLE_SESSION);
  if (jeton) {
    entetes.set('Authorization', `Basic ${jeton}`);
  }
  if (options.body) {
    entetes.set('Content-Type', 'application/json');
  }

  const reponse = await fetch(`/api${chemin}`, { ...options, headers: entetes });
  if (!reponse.ok) {
    let probleme: ProblemDetail = {};
    try {
      probleme = (await reponse.json()) as ProblemDetail;
    } catch {
      // corps vide ou non JSON
    }
    const message =
      reponse.status === 401
        ? 'Identifiant ou mot de passe incorrect.'
        : (probleme.detail ?? probleme.title ?? `Erreur HTTP ${reponse.status}`);
    throw new ApiError(reponse.status, message, probleme.erreurs ?? []);
  }
  if (reponse.status === 204) {
    return undefined as T;
  }
  return (await reponse.json()) as T;
}

function parametres(filtres: FiltresDemandes): string {
  const p = new URLSearchParams();
  if (filtres.statut) p.set('statut', filtres.statut);
  if (filtres.type) p.set('type', filtres.type);
  p.set('page', String(filtres.page ?? 0));
  p.set('size', String(filtres.size ?? 20));
  return p.toString();
}

export const api = {
  moi: () => requete<Utilisateur>('/moi'),
  listerDemandes: (filtres: FiltresDemandes = {}) => requete<PageDemandes>(`/demandes?${parametres(filtres)}`),
  rechercherDemandes: (texte: string) =>
    requete<Demande[]>(`/demandes/recherche?q=${encodeURIComponent(texte)}`),
  obtenirDemande: (id: number) => requete<Demande>(`/demandes/${id}`),
  creerDemande: (saisie: DemandeSaisie) =>
    requete<Demande>('/demandes', { method: 'POST', body: JSON.stringify(saisie) }),
  modifierDemande: (id: number, saisie: DemandeSaisie) =>
    requete<Demande>(`/demandes/${id}`, { method: 'PUT', body: JSON.stringify(saisie) }),
  soumettre: (id: number) => requete<Demande>(`/demandes/${id}/soumettre`, { method: 'POST' }),
  valider: (id: number) => requete<Demande>(`/demandes/${id}/valider`, { method: 'POST' }),
  refuser: (id: number, motif: string) =>
    requete<Demande>(`/demandes/${id}/refuser`, { method: 'POST', body: JSON.stringify({ motif }) }),
  cloturer: (id: number) => requete<Demande>(`/demandes/${id}/cloturer`, { method: 'POST' }),
  evenements: (id: number) => requete<Evenement[]>(`/demandes/${id}/evenements`),
};
