import DOMPurify from 'dompurify';
import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { api, type Demande, type Evenement } from '../api/client';
import { useAuth } from '../auth/auth';
import { MessageErreur } from '../components/MessageErreur';
import { StatutBadge } from '../components/StatutBadge';
import NeoUtils from '../legacy/utils-legacy.js';

function formatHorodatage(horodatage: string): string {
  return `${NeoUtils.formatDate(horodatage)} ${horodatage.slice(11, 16)}`;
}

interface DescriptionRicheProps {
  html: string;
}

/**
 * Les descriptions reprises de l'ancien intranet contiennent de la mise en forme HTML.
 * F2 corrigée : le HTML est assaini (liste blanche de balises de mise en forme, aucun attribut)
 * avant insertion ; scripts, gestionnaires d'événements et liens javascript: sont supprimés.
 */
const MISE_EN_FORME = { ALLOWED_TAGS: ['p', 'br', 'ul', 'ol', 'li', 'b', 'strong', 'i', 'em'], ALLOWED_ATTR: [] };

function DescriptionRiche({ html }: DescriptionRicheProps) {
  return <div className="description" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(html, MISE_EN_FORME) }} />;
}

export function DemandeDetail() {
  const { id } = useParams();
  const idDemande = Number(id);
  const { utilisateur, aLeRole } = useAuth();
  const [demande, setDemande] = useState<Demande | null>(null);
  const [evenements, setEvenements] = useState<Evenement[]>([]);
  const [erreur, setErreur] = useState<unknown>(null);
  const [motif, setMotif] = useState('');
  const [saisieRefus, setSaisieRefus] = useState(false);
  const [envoi, setEnvoi] = useState(false);

  const charger = useCallback(async () => {
    try {
      const [d, historique] = await Promise.all([api.obtenirDemande(idDemande), api.evenements(idDemande)]);
      setDemande(d);
      setEvenements(historique);
    } catch (e) {
      setErreur(e);
    }
  }, [idDemande]);

  useEffect(() => {
    void charger();
  }, [charger]);

  async function agir(action: () => Promise<Demande>) {
    setErreur(null);
    setEnvoi(true);
    try {
      setDemande(await action());
      setSaisieRefus(false);
      setMotif('');
      setEvenements(await api.evenements(idDemande));
    } catch (e) {
      setErreur(e);
    } finally {
      setEnvoi(false);
    }
  }

  if (!demande) {
    return erreur ? <MessageErreur erreur={erreur} /> : <p>Chargement…</p>;
  }

  const estDemandeur = aLeRole('DEMANDEUR') && utilisateur?.login === demande.demandeur;
  const peutModifier = estDemandeur && demande.statut === 'BROUILLON';
  const peutDecider = aLeRole('VALIDEUR') && demande.statut === 'SOUMISE';
  const peutCloturer = aLeRole('ADMIN') && demande.statut === 'VALIDEE';

  return (
    <section className="carte">
      <p>
        <Link to="/demandes">← Retour à la liste</Link>
      </p>
      <div className="titre-page">
        <h1>{demande.titre}</h1>
        <StatutBadge statut={demande.statut} testId="statut" />
      </div>

      <dl className="fiche">
        <dt>N°</dt>
        <dd>{demande.id}</dd>
        <dt>Type</dt>
        <dd>{demande.type}</dd>
        <dt>Demandeur</dt>
        <dd>
          {demande.demandeur} ({demande.departement ?? 'département inconnu'})
        </dd>
        <dt>Montant</dt>
        <dd>{NeoUtils.formatMontant(demande.montant)}</dd>
        <dt>Période</dt>
        <dd>
          {NeoUtils.formatDate(demande.dateDebut)}
          {demande.dateFin &&
            ` au ${NeoUtils.formatDate(demande.dateFin)} (${NeoUtils.joursOuvres(demande.dateDebut, demande.dateFin)} jours ouvrés)`}
        </dd>
        <dt>Urgent</dt>
        <dd>{demande.urgent ? 'Oui' : 'Non'}</dd>
        <dt>Niveau de validation</dt>
        <dd>{demande.niveauValidation ?? 'calculé à la soumission'}</dd>
        {demande.motifRefus && (
          <>
            <dt>Motif du refus</dt>
            <dd>{demande.motifRefus}</dd>
          </>
        )}
      </dl>

      <h2>Description</h2>
      <DescriptionRiche html={demande.description ?? ''} />

      <MessageErreur erreur={erreur} />

      <div className="actions">
        {peutModifier && (
          <>
            <Link to={`/demandes/${demande.id}/modifier`} className="bouton secondaire">
              Modifier
            </Link>
            <button type="button" disabled={envoi} onClick={() => agir(() => api.soumettre(demande.id))}>
              Soumettre
            </button>
          </>
        )}
        {peutDecider && (
          <>
            <button type="button" disabled={envoi} onClick={() => agir(() => api.valider(demande.id))}>
              Valider
            </button>
            <button type="button" className="danger" disabled={envoi} onClick={() => setSaisieRefus(true)}>
              Refuser
            </button>
          </>
        )}
        {peutCloturer && (
          <button type="button" disabled={envoi} onClick={() => agir(() => api.cloturer(demande.id))}>
            Clôturer
          </button>
        )}
      </div>

      {saisieRefus && (
        <div className="refus">
          <label htmlFor="motif">Motif du refus</label>
          <textarea id="motif" rows={3} value={motif} onChange={(e) => setMotif(e.target.value)} />
          <button
            type="button"
            className="danger"
            disabled={envoi || !motif.trim()}
            onClick={() => agir(() => api.refuser(demande.id, motif.trim()))}
          >
            Confirmer le refus
          </button>
        </div>
      )}

      <h2>Historique</h2>
      <ol className="historique">
        {evenements.map((e) => (
          <li key={e.id}>
            <strong>{e.type}</strong> par {e.auteur} le {formatHorodatage(e.horodatage)}
            {e.commentaire && <> : {e.commentaire}</>}
          </li>
        ))}
      </ol>
    </section>
  );
}
