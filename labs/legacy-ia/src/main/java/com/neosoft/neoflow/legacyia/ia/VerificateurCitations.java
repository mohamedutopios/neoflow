package com.neosoft.neoflow.legacyia.ia;

import com.neosoft.neoflow.legacyia.analyse.CodeSource;
import com.neosoft.neoflow.legacyia.ia.Reponses.Affirmation;
import com.neosoft.neoflow.legacyia.ia.Reponses.Citation;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Vérifie mécaniquement les citations du modèle : le fichier existe, la ligne existe, l'extrait cité
 * figure sur cette ligne. Une affirmation dont une citation échoue est rejetée.
 *
 * <p>Limite volontairement rappelée dans les rapports : une citation exacte prouve que le modèle a lu la
 * ligne, pas que son interprétation est juste. Seul un test de caractérisation tranche.
 */
public final class VerificateurCitations {

    static final int LONGUEUR_MIN_EXTRAIT = 4;

    private final CodeSource code;

    public VerificateurCitations(CodeSource code) {
        this.code = code;
    }

    /** Résultat de la vérification d'une citation. */
    public record Verdict(boolean valide, String raison) {
        static Verdict ok() {
            return new Verdict(true, "citation vérifiée");
        }

        static Verdict rejet(String raison) {
            return new Verdict(false, raison);
        }
    }

    /** Affirmation et motif de rejet éventuel. */
    public record AffirmationVerifiee(Affirmation affirmation, boolean retenue, List<String> motifs) {}

    public Verdict verifier(Citation citation) {
        // TODO TP1-4 : aujourd'hui tout est accepté, ce qui est précisément le problème. Rejeter :
        //   - une citation null ;
        //   - un fichier que code.resoudre(...) ne trouve pas ;
        //   - une ligne hors de 1..nombre de lignes (motif « ligne N inexistante (...) ») ;
        //   - un extrait normalisé de moins de LONGUEUR_MIN_EXTRAIT caractères (hors espaces) ;
        //   - un extrait normalisé absent de la ligne normalisée (motif « extrait absent de la ligne N ... »).
        // Utiliser normaliser(...) des deux côtés. Tests : VerificateurCitationsTest, ExplicateurTest.
        return Verdict.ok();
    }

    /** Retient les affirmations dont toutes les citations sont vérifiées (et qui en ont au moins une). */
    public List<AffirmationVerifiee> filtrer(List<Affirmation> affirmations) {
        List<AffirmationVerifiee> resultat = new ArrayList<>();
        for (Affirmation affirmation : affirmations == null ? List.<Affirmation>of() : affirmations) {
            List<String> motifs = new ArrayList<>();
            if (affirmation.citations() == null || affirmation.citations().isEmpty()) {
                motifs.add("aucune citation");
            } else {
                for (Citation citation : affirmation.citations()) {
                    Verdict verdict = verifier(citation);
                    if (!verdict.valide()) {
                        motifs.add(verdict.raison());
                    }
                }
            }
            resultat.add(new AffirmationVerifiee(affirmation, motifs.isEmpty(), motifs));
        }
        return resultat;
    }

    /** Espaces multiples réduits, extrémités supprimées : la citation ne dépend pas de l'indentation. */
    static String normaliser(String texte) {
        return texte == null ? "" : texte.strip().replaceAll("\\s+", " ");
    }
}
