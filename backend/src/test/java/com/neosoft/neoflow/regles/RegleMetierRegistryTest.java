package com.neosoft.neoflow.regles;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.neosoft.neoflow.demande.Demande;
import com.neosoft.neoflow.demande.TypeDemande;

class RegleMetierRegistryTest {

    @Test
    void appliqueLesReglesGeneriquesATousLesTypes() {
        RegleMetierRegistry registre = new RegleMetierRegistry(List.of(regle(TypeDemande.GENERIQUE, "commune")));

        assertThat(registre.verifier(demande(TypeDemande.CONGES))).containsExactly("commune");
        assertThat(registre.verifier(demande(TypeDemande.ACHAT))).containsExactly("commune");
    }

    @Test
    void nAppliqueUneRegleSpecifiqueQuAuTypeConcerne() {
        RegleMetierRegistry registre = new RegleMetierRegistry(List.of(regle(TypeDemande.CONGES, "solde insuffisant")));

        assertThat(registre.verifier(demande(TypeDemande.CONGES))).containsExactly("solde insuffisant");
        assertThat(registre.verifier(demande(TypeDemande.NOTE_DE_FRAIS))).isEmpty();
    }

    @Test
    void agregeLesErreursEnCommencantParLesReglesGeneriques() {
        RegleMetierRegistry registre = new RegleMetierRegistry(List.of(
                regle(TypeDemande.ACHAT, "fournisseur non référencé"),
                regle(TypeDemande.GENERIQUE, "titre trop vague")));

        assertThat(registre.verifier(demande(TypeDemande.ACHAT)))
                .containsExactly("titre trop vague", "fournisseur non référencé");
        assertThat(registre.reglesApplicables(TypeDemande.ACHAT)).hasSize(2);
    }

    @Test
    void renvoieUneListeVideQuandLaDemandeEstConforme() {
        RegleMetierRegistry registre = new RegleMetierRegistry(List.of(new RegleGenerique()));

        Demande conforme = demande(TypeDemande.GENERIQUE);
        conforme.setDateFin(conforme.getDateDebut().plusDays(2));
        conforme.setMontant(new BigDecimal("15.00"));

        assertThat(registre.verifier(conforme)).isEmpty();
    }

    @Test
    void regleGenerique_refuseUneDateDeFinAnterieureEtUnMontantNul() {
        RegleMetierRegistry registre = new RegleMetierRegistry(List.of(new RegleGenerique()));

        Demande incoherente = demande(TypeDemande.DEPLACEMENT);
        incoherente.setDateFin(incoherente.getDateDebut().minusDays(1));
        incoherente.setMontant(BigDecimal.ZERO);

        assertThat(registre.verifier(incoherente)).containsExactly(
                "La date de fin doit être postérieure ou égale à la date de début",
                "Le montant, s'il est renseigné, doit être strictement positif");
    }

    private static RegleMetierDemande regle(TypeDemande type, String erreur) {
        return new RegleMetierDemande() {
            @Override
            public TypeDemande type() {
                return type;
            }

            @Override
            public List<String> verifier(Demande d) {
                return List.of(erreur);
            }
        };
    }

    private static Demande demande(TypeDemande type) {
        Demande d = new Demande();
        d.setType(type);
        d.setTitre("Demande de test");
        d.setDemandeur("alice");
        d.setDateDebut(LocalDate.of(2026, 11, 10));
        return d;
    }
}
