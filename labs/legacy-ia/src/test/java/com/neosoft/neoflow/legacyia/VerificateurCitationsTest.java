package com.neosoft.neoflow.legacyia;

import com.neosoft.neoflow.legacyia.analyse.AnalyseurLegacy;
import com.neosoft.neoflow.legacyia.ia.Reponses.Affirmation;
import com.neosoft.neoflow.legacyia.ia.Reponses.Citation;
import com.neosoft.neoflow.legacyia.ia.VerificateurCitations;
import com.neosoft.neoflow.legacyia.ia.VerificateurCitations.AffirmationVerifiee;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static com.neosoft.neoflow.legacyia.Fixtures.LEGACY;
import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("Vérification des citations de ligne (TODO 4 du starter)")
class VerificateurCitationsTest {

    static VerificateurCitations verificateur;

    @BeforeAll
    static void preparer() {
        AnalyseurLegacy analyseur = Fixtures.analyseur();
        analyseur.analyser();
        verificateur = new VerificateurCitations(analyseur.code());
    }

    @Test
    void citationExacteAcceptee() {
        assertThat(verificateur.verifier(new Citation(LEGACY, 56, "if (departement == DSI) {")).valide()).isTrue();
    }

    @Test
    void indentationEtNomDeFichierSeulTolérés() {
        assertThat(verificateur.verifier(new Citation("RegleValidationLegacy.java", 56, "departement   ==   DSI")).valide()).isTrue();
    }

    @Test
    void ligneInexistanteRejetee() {
        var verdict = verificateur.verifier(new Citation(LEGACY, 156, "if (niveau > NIVEAU_MAX)"));
        assertThat(verdict.valide()).isFalse();
        assertThat(verdict.raison()).contains("ligne 156 inexistante");
    }

    @Test
    void extraitAbsentDeLaLigneRejete() {
        var verdict = verificateur.verifier(new Citation(LEGACY, 57, "departement.equals(DSI)"));
        assertThat(verdict.valide()).isFalse();
        assertThat(verdict.raison()).contains("extrait absent de la ligne 57");
    }

    @Test
    void fichierInconnuEtExtraitTropCourtRejetes() {
        assertThat(verificateur.verifier(new Citation("Inexistant.java", 1, "package")).valide()).isFalse();
        assertThat(verificateur.verifier(new Citation(LEGACY, 56, " { ")).valide()).isFalse();
        assertThat(verificateur.verifier(new Citation(LEGACY, 0, "package")).valide()).isFalse();
    }

    @Test
    void affirmationSansCitationOuAvecUneCitationFausseRejetee() {
        List<AffirmationVerifiee> resultat = verificateur.filtrer(List.of(
                new Affirmation("sans citation", "HYPOTHESE", List.of(), "test"),
                new Affirmation("une bonne, une fausse", "VERIFIE",
                        List.of(new Citation(LEGACY, 56, "departement == DSI"), new Citation(LEGACY, 999, "niveau")), "test"),
                new Affirmation("correcte", "VERIFIE", List.of(new Citation(LEGACY, 86, "Calendar.getInstance()")), "test")));
        assertThat(resultat).extracting(AffirmationVerifiee::retenue).containsExactly(false, false, true);
        assertThat(resultat.get(0).motifs()).containsExactly("aucune citation");
    }
}
