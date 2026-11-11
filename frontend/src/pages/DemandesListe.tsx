import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import {
  api,
  STATUTS_DEMANDE,
  TYPES_DEMANDE,
  type Demande,
  type PageDemandes,
  type StatutDemande,
  type TypeDemande,
} from '../api/client';
import { useAuth } from '../auth/auth';
import { MessageErreur } from '../components/MessageErreur';
import { StatutBadge } from '../components/StatutBadge';
import { libelleStatut } from '../components/statuts';
import NeoUtils from '../legacy/utils-legacy.js';

const TAILLES_PAGE = [5, 10, 20];

export function DemandesListe() {
  const { aLeRole } = useAuth();
  const [statut, setStatut] = useState<StatutDemande | ''>('');
  const [type, setType] = useState<TypeDemande | ''>('');
  const [page, setPage] = useState(0);
  const [taille, setTaille] = useState(10);
  const [resultat, setResultat] = useState<PageDemandes | null>(null);
  const [recherche, setRecherche] = useState('');
  const [resultatsRecherche, setResultatsRecherche] = useState<Demande[] | null>(null);
  const [erreur, setErreur] = useState<unknown>(null);

  const charger = useCallback(async () => {
    setErreur(null);
    try {
      setResultat(await api.listerDemandes({ statut, type, page, size: taille }));
    } catch (e) {
      setErreur(e);
    }
  }, [statut, type, page, taille]);

  useEffect(() => {
    void charger();
  }, [charger]);

  async function rechercher(evenement: FormEvent) {
    evenement.preventDefault();
    if (!recherche.trim()) {
      setResultatsRecherche(null);
      return;
    }
    setErreur(null);
    try {
      setResultatsRecherche(await api.rechercherDemandes(recherche.trim()));
    } catch (e) {
      setErreur(e);
    }
  }

  const demandes = resultatsRecherche ?? resultat?.content ?? [];
  const infosPage = resultat?.page;

  return (
    <section>
      <div className="titre-page">
        <h1>Demandes</h1>
        {aLeRole('DEMANDEUR') && (
          <Link to="/demandes/nouvelle" className="bouton">
            Nouvelle demande
          </Link>
        )}
      </div>

      <div className="barre-filtres">
        <label>
          Statut
          <select
            value={statut}
            onChange={(e) => {
              setStatut(e.target.value as StatutDemande | '');
              setPage(0);
            }}
          >
            <option value="">Tous</option>
            {STATUTS_DEMANDE.map((s) => (
              <option key={s} value={s}>
                {libelleStatut(s)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Type
          <select
            value={type}
            onChange={(e) => {
              setType(e.target.value as TypeDemande | '');
              setPage(0);
            }}
          >
            <option value="">Tous</option>
            {TYPES_DEMANDE.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <form onSubmit={rechercher} className="recherche">
          <label>
            Rechercher par titre
            <input type="search" value={recherche} onChange={(e) => setRecherche(e.target.value)} />
          </label>
          <button type="submit" className="secondaire">
            Rechercher
          </button>
          {resultatsRecherche && (
            <button
              type="button"
              className="secondaire"
              onClick={() => {
                setRecherche('');
                setResultatsRecherche(null);
              }}
            >
              Effacer
            </button>
          )}
        </form>
      </div>

      <MessageErreur erreur={erreur} />

      <table className="tableau">
        <thead>
          <tr>
            <th>N°</th>
            <th>Titre</th>
            <th>Type</th>
            <th>Demandeur</th>
            <th className="nombre">Montant</th>
            <th>Début</th>
            <th>Statut</th>
          </tr>
        </thead>
        <tbody>
          {demandes.map((d) => (
            <tr key={d.id}>
              <td>{d.id}</td>
              <td>
                <Link to={`/demandes/${d.id}`}>{d.titre}</Link>
                {d.urgent && <span className="urgent"> urgent</span>}
              </td>
              <td>{d.type}</td>
              <td>{d.demandeur}</td>
              <td className="nombre">{NeoUtils.formatMontant(d.montant)}</td>
              <td>{NeoUtils.formatDate(d.dateDebut)}</td>
              <td>
                <StatutBadge statut={d.statut} />
              </td>
            </tr>
          ))}
          {demandes.length === 0 && (
            <tr>
              <td colSpan={7}>Aucune demande.</td>
            </tr>
          )}
        </tbody>
      </table>

      {!resultatsRecherche && infosPage && (
        <nav className="pagination" aria-label="Pagination">
          <button type="button" className="secondaire" disabled={page === 0} onClick={() => setPage(page - 1)}>
            Précédent
          </button>
          <span>
            Page {infosPage.number + 1} / {Math.max(infosPage.totalPages, 1)} ({infosPage.totalElements} demandes)
          </span>
          <button
            type="button"
            className="secondaire"
            disabled={page + 1 >= infosPage.totalPages}
            onClick={() => setPage(page + 1)}
          >
            Suivant
          </button>
          <label>
            Par page
            <select
              value={taille}
              onChange={(e) => {
                setTaille(Number(e.target.value));
                setPage(0);
              }}
            >
              {TAILLES_PAGE.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
        </nav>
      )}
    </section>
  );
}
