import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { api, TYPES_DEMANDE, type DemandeSaisie, type TypeDemande } from '../api/client';
import { MessageErreur } from '../components/MessageErreur';

interface Champs {
  type: TypeDemande;
  titre: string;
  description: string;
  montant: string;
  dateDebut: string;
  dateFin: string;
  departement: string;
  urgent: boolean;
}

const VIDE: Champs = {
  type: 'GENERIQUE',
  titre: '',
  description: '',
  montant: '',
  dateDebut: '',
  dateFin: '',
  departement: '',
  urgent: false,
};

function versSaisie(c: Champs): DemandeSaisie {
  return {
    type: c.type,
    titre: c.titre,
    description: c.description || null,
    montant: c.montant === '' ? null : Number(c.montant),
    dateDebut: c.dateDebut,
    dateFin: c.dateFin || null,
    departement: c.departement || null,
    urgent: c.urgent,
  };
}

/** Création (/demandes/nouvelle) et modification d'un brouillon (/demandes/:id/modifier). */
export function DemandeFormulaire() {
  const { id } = useParams();
  const edition = id !== undefined;
  const navigate = useNavigate();
  const [champs, setChamps] = useState<Champs>(VIDE);
  const [erreur, setErreur] = useState<unknown>(null);
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    if (!edition) return;
    api
      .obtenirDemande(Number(id))
      .then((d) =>
        setChamps({
          type: d.type,
          titre: d.titre,
          description: d.description ?? '',
          montant: d.montant === null ? '' : String(d.montant),
          dateDebut: d.dateDebut,
          dateFin: d.dateFin ?? '',
          departement: d.departement ?? '',
          urgent: d.urgent,
        }),
      )
      .catch(setErreur);
  }, [edition, id]);

  function maj<K extends keyof Champs>(cle: K, valeur: Champs[K]) {
    setChamps((precedent) => ({ ...precedent, [cle]: valeur }));
  }

  async function enregistrer(evenement: FormEvent) {
    evenement.preventDefault();
    setErreur(null);
    setEnvoi(true);
    try {
      const demande = edition
        ? await api.modifierDemande(Number(id), versSaisie(champs))
        : await api.creerDemande(versSaisie(champs));
      navigate(`/demandes/${demande.id}`);
    } catch (e) {
      setErreur(e);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <section className="carte">
      <h1>{edition ? `Modifier la demande n° ${id}` : 'Nouvelle demande'}</h1>
      <form onSubmit={enregistrer} className="formulaire">
        <label htmlFor="type">Type</label>
        <select id="type" value={champs.type} onChange={(e) => maj('type', e.target.value as TypeDemande)}>
          {TYPES_DEMANDE.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <label htmlFor="titre">Titre</label>
        <input id="titre" value={champs.titre} maxLength={120} onChange={(e) => maj('titre', e.target.value)} required />

        <label htmlFor="description">Description</label>
        <textarea
          id="description"
          rows={5}
          maxLength={4000}
          value={champs.description}
          onChange={(e) => maj('description', e.target.value)}
        />

        <label htmlFor="montant">Montant (€, facultatif)</label>
        <input
          id="montant"
          type="number"
          min="0"
          step="0.01"
          value={champs.montant}
          onChange={(e) => maj('montant', e.target.value)}
        />

        <label htmlFor="dateDebut">Date de début</label>
        <input
          id="dateDebut"
          type="date"
          value={champs.dateDebut}
          onChange={(e) => maj('dateDebut', e.target.value)}
          required
        />

        <label htmlFor="dateFin">Date de fin (facultative)</label>
        <input id="dateFin" type="date" value={champs.dateFin} onChange={(e) => maj('dateFin', e.target.value)} />

        <label htmlFor="departement">Département (par défaut : le vôtre)</label>
        <input
          id="departement"
          value={champs.departement}
          maxLength={40}
          onChange={(e) => maj('departement', e.target.value)}
        />

        <label className="case">
          <input type="checkbox" checked={champs.urgent} onChange={(e) => maj('urgent', e.target.checked)} />
          Urgent
        </label>

        <MessageErreur erreur={erreur} />

        <div className="actions">
          <button type="submit" disabled={envoi}>
            Enregistrer le brouillon
          </button>
          <button type="button" className="secondaire" onClick={() => navigate(-1)}>
            Annuler
          </button>
        </div>
      </form>
    </section>
  );
}
