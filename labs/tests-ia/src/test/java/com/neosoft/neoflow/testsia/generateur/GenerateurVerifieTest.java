package com.neosoft.neoflow.testsia.generateur;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import com.neosoft.neoflow.testsia.commun.CommandesAutorisees;
import com.neosoft.neoflow.testsia.commun.Journal;
import com.neosoft.neoflow.testsia.modele.ModeleSimule;

/** Boucle Generator–Verifier bornée, sur une cible minimale, avec un modèle simulé (aucun appel réseau). */
class GenerateurVerifieTest {

    @TempDir
    Path travail;

    private ModeleSimule modeleDeuxTours() {
        return new ModeleSimule()
                .repondre(PromptsGenerateur.TACHE, CibleMini.proposition(
                        CibleMini.json("PageUnIaTest", "PG-01", "assertThat(Pagination.index(1)).isEqualTo(1);"),
                        CibleMini.json("ConstanteIaTest", "PG-01", "Pagination.index(1); assertTrue(true);"),
                        CibleMini.json("CompileKoIaTest", "PG-02", "assertThat(Pagination.indice(-1)).isEqualTo(0);"),
                        CibleMini.json("OracleFauxIaTest", "PG-01", "assertThat(Pagination.index(1)).isEqualTo(0);")))
                .repondre(PromptsGenerateur.TACHE, CibleMini.proposition(
                        CibleMini.json("PageNegativeIaTest", "PG-02",
                                "assertThatThrownBy(() -> Pagination.index(-1)).isInstanceOf(IllegalArgumentException.class).hasMessageContaining(\"négative\");"),
                        CibleMini.json("PageZeroIaTest", "PG-01", "assertThat(Pagination.index(0)).isZero();")))
                .repondre(PromptsGenerateur.TACHE, CibleMini.proposition());
    }

    private GenerateurVerifie generateur(ModeleSimule modele, boolean mutation) {
        CommandesAutorisees commandes = new CommandesAutorisees(Journal.desactive());
        return new GenerateurVerifie(modele, new Verificateur(new ExecuteurTests(commandes)),
                mutation ? new MesureMutation(commandes) : null, Journal.desactive());
    }

    @Test
    void rejette_accepte_signale_puis_renvoieLesMotifsAuModele() {
        ContexteProjet projet = CibleMini.projet(travail);
        ModeleSimule modele = modeleDeuxTours();

        RapportGeneration rapport = generateur(modele, false).generer(CibleMini.cible(projet), projet, 3, 0.0);

        assertThat(rapport.tours()).isEqualTo(2);
        assertThat(rapport.acceptes()).extracting(v -> v.test().nomClasse())
                .containsExactlyInAnyOrder("PageUnIaTest", "PageNegativeIaTest", "PageZeroIaTest");
        assertThat(rapport.aArbitrer()).extracting(v -> v.test().nomClasse()).containsExactly("OracleFauxIaTest");
        assertThat(rapport.rejetes()).extracting(VerdictTest::statut)
                .containsExactlyInAnyOrder(Statut.REJETE_TAUTOLOGIE, Statut.REJETE_COMPILATION);

        String retourTour2 = modele.demandesRecues().get(1).utilisateur();
        assertThat(retourTour2).contains("ConstanteIaTest [REJETE_TAUTOLOGIE]", "assertion constante",
                "CompileKoIaTest [REJETE_COMPILATION]", "PageUnIaTest");
        assertThat(retourTour2).as("un test rouge n'est jamais renvoyé avec son échec : le modèle alignerait l'oracle sur le code")
                .doesNotContain("expected").contains("OracleFauxIaTest");
    }

    @Test
    void laBoucleEstBornee() {
        ContexteProjet projet = CibleMini.projet(travail);
        ModeleSimule modele = new ModeleSimule();
        for (int i = 0; i < 5; i++) {
            modele.repondre(PromptsGenerateur.TACHE, CibleMini.proposition(
                    CibleMini.json("Constante" + i + "IaTest", "PG-01", "assertTrue(true);")));
        }

        RapportGeneration rapport = generateur(modele, false).generer(CibleMini.cible(projet), projet, 2, 0.0);

        assertThat(rapport.tours()).isEqualTo(2);
        assertThat(modele.demandesRecues()).hasSize(2);
        assertThat(rapport.acceptes()).isEmpty();
    }

    @Test
    void lesTestsAcceptesSontMesuresParPit() {
        ContexteProjet projet = CibleMini.projet(travail);

        RapportGeneration rapport = generateur(modeleDeuxTours(), true).generer(CibleMini.cible(projet), projet, 3, 0.9);

        assertThat(rapport.mutation()).isNotNull();
        assertThat(rapport.mutation().generes()).isPositive();
        assertThat(rapport.mutation().score()).isEqualTo(1.0);
        assertThat(rapport.versMarkdown()).contains("Mutation (PIT)");
    }
}
