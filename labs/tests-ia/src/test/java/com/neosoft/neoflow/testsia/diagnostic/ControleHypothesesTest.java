package com.neosoft.neoflow.testsia.diagnostic;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;

class ControleHypothesesTest {

    private final DossierIncident dossier = new DossierIncident("t", List.of(
            new Fait("F1", "500", "trace"), new Fait("F2", "NPE", "logs")));
    private final TestReproduction test = new TestReproduction("unitaire", "XTest", "cas", "assertThat(x).isEqualTo(1)");

    private ControleHypotheses.Resultat controler(Hypothese... h) {
        return new ControleHypotheses().controler(new Hypotheses(List.of(h), List.of()), dossier);
    }

    @Test
    void hypotheseSourceeAvecTest_estRetenue() {
        assertThat(controler(new Hypothese("H1", "cause", 4, List.of("F1", "F2"), List.of(), "si…", test)).retenues())
                .extracting(Hypothese::id).containsExactly("H1");
    }

    @Test
    void hypotheseCitantUnFaitInexistant_estRejetee() {
        ControleHypotheses.Resultat r = controler(new Hypothese("H1", "cause", 4, List.of("F1", "F7"), List.of(), "si…", test));
        assertThat(r.retenues()).isEmpty();
        assertThat(r.rejets()).singleElement().asString().contains("H1", "F7");
    }

    @Test
    void hypotheseSansFaitOuSansTest_estRejetee() {
        ControleHypotheses.Resultat r = controler(
                new Hypothese("H1", "intuition", 3, List.of(), List.of(), "si…", test),
                new Hypothese("H2", "cause", 3, List.of("F1"), List.of(), "si…", new TestReproduction("unitaire", "XTest", "cas", " ")));
        assertThat(r.retenues()).isEmpty();
        assertThat(r.rejets()).hasSize(2);
    }

    @Test
    void lesRetenuesSontTrieesParVraisemblanceEtLimiteesATrois() {
        ControleHypotheses.Resultat r = controler(
                new Hypothese("H1", "a", 2, List.of("F1"), List.of(), "", test),
                new Hypothese("H2", "b", 5, List.of("F2"), List.of(), "", test),
                new Hypothese("H3", "c", 3, List.of("F1"), List.of(), "", test),
                new Hypothese("H4", "d", 1, List.of("F1"), List.of(), "", test));
        assertThat(r.retenues()).extracting(Hypothese::id).containsExactly("H2", "H3", "H1");
    }
}
