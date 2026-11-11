package com.neosoft.neoflow.legacyia;

import com.neosoft.neoflow.legacyia.analyse.AnalyseurLegacy;
import com.neosoft.neoflow.legacyia.analyse.Faits;
import com.neosoft.neoflow.legacyia.ia.Explicateur;
import com.neosoft.neoflow.legacyia.ia.Explicateur.RapportExplication;
import com.neosoft.neoflow.legacyia.ia.Explicateur.RapportImpact;
import com.neosoft.neoflow.legacyia.ia.ModeleSimule;
import com.neosoft.neoflow.legacyia.ia.VerificateurCitations.AffirmationVerifiee;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("Explication et analyse d'impact hors ligne (modèle simulé)")
class ExplicateurTest {

    static Faits faits;
    static Explicateur explicateur;

    @BeforeAll
    static void preparer() {
        AnalyseurLegacy analyseur = Fixtures.analyseur();
        faits = analyseur.analyser();
        explicateur = new Explicateur(new ModeleSimule(analyseur.code(), null), analyseur.code());
    }

    @Test
    @DisplayName("les deux citations inventées sont rejetées, l'interprétation fausse mais bien citée est retenue")
    void verificationDesCitations() {
        RapportExplication rapport = explicateur.expliquer(faits);

        assertThat(rapport.affirmations().stream().filter(a -> !a.retenue()))
                .extracting(a -> a.affirmation().texte())
                .containsExactlyInAnyOrder("Le montant remboursable est arrondi au centime supérieur.",
                        "La règle du vendredi est appliquée avant le plafonnement du niveau.");
        assertThat(rapport.affirmations().stream().filter(AffirmationVerifiee::retenue))
                .extracting(a -> a.affirmation().texte())
                .contains("Pour MATERIEL_IT, un demandeur de la DSI obtient toujours le niveau 1.");
        assertThat(rapport.risquesRetenus()).hasSizeGreaterThanOrEqualTo(3);
        assertThat(Explicateur.enMarkdown(rapport)).contains("Affirmations rejetées", "ligne 157 inexistante",
                "extrait absent de la ligne 40");
    }

    @Test
    @DisplayName("impact du remplacement de == par equals : chaîne d'appels, endpoint, changement métier")
    void impact() {
        RapportImpact rapport = explicateur.impact(faits, "RegleValidationLegacy.java:56",
                "remplacer departement == DSI par DSI.equals(departement)");

        assertThat(rapport.deterministe().methodeModifiee())
                .isEqualTo("RegleValidationLegacy.determinerNiveau(String,Double,int,String,boolean)");
        assertThat(rapport.deterministe().appelants()).hasSize(3);
        assertThat(rapport.deterministe().pointsEntree()).extracting(p -> p.chemin())
                .containsExactly("/api/demandes/{id}/soumettre");
        assertThat(rapport.deterministe().constatsSurLaLigne()).isNotEmpty();
        assertThat(rapport.nature()).isEqualTo("CHANGEMENT_METIER");
        assertThat(rapport.consequences()).allMatch(AffirmationVerifiee::retenue);
    }
}
