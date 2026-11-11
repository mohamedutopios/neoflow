package com.neosoft.neoflow.legacyia;

import com.neosoft.neoflow.legacyia.analyse.Faits;
import com.neosoft.neoflow.legacyia.analyse.Faits.Constat;
import com.neosoft.neoflow.legacyia.analyse.Faits.Methode;
import com.neosoft.neoflow.legacyia.analyse.Faits.TypeConstat;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.util.List;

import static com.neosoft.neoflow.legacyia.Fixtures.LEGACY;
import static com.neosoft.neoflow.legacyia.Fixtures.REMBOURSEMENT;
import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("Analyse JavaParser du module legacy (copies figées du socle)")
class AnalyseurLegacyTest {

    static Faits faits;

    @BeforeAll
    static void analyser() {
        faits = Fixtures.faits();
    }

    static List<Constat> constats(TypeConstat type) {
        return faits.constats().stream().filter(c -> c.type() == type).toList();
    }

    static Methode methode(String id) {
        return faits.methodes().stream().filter(m -> m.id().equals(id)).findFirst().orElseThrow();
    }

    @Nested
    @DisplayName("Graphe d'appels et points d'entrée")
    class Graphe {

        @Test
        void chaineDeLEndpointJusquAuLegacy() {
            assertThat(faits.appels()).extracting(a -> a.appelant() + " -> " + a.appele() + " @" + a.ligne())
                    .contains("DemandeController.soumettre(Long,Authentication) -> DemandeService.soumettre(Long,String) @73",
                            "DemandeService.soumettre(Long,String) -> CircuitValidationService.calculerNiveau(Demande,int) @125",
                            "CircuitValidationService.calculerNiveau(Demande,int) -> RegleValidationLegacy.determinerNiveau(String,Double,int,String,boolean) @32");
        }

        @Test
        void pointDEntreeHttp() {
            assertThat(faits.pointsEntree()).singleElement().satisfies(pe -> {
                assertThat(pe.verbe()).isEqualTo("POST");
                assertThat(pe.chemin()).isEqualTo("/api/demandes/{id}/soumettre");
            });
        }

        @Test
        void dependancesDeClasses() {
            assertThat(faits.dependances()).extracting(d -> d.de() + "->" + d.vers())
                    .containsExactly("CircuitValidationService->RegleValidationLegacy", "DemandeController->DemandeService",
                            "DemandeService->CircuitValidationService");
        }

        @Test
        void seulesLesMethodesUtilesSontRetenues() {
            assertThat(faits.methodes()).extracting(Methode::nom)
                    .containsExactlyInAnyOrder("soumettre", "soumettre", "calculer", "determinerNiveau", "calculerNiveau");
        }
    }

    @Nested
    @DisplayName("Complexité cyclomatique (TODO 1 du starter)")
    class Complexite {

        @Test
        void determinerNiveauVaut28() {
            assertThat(methode("RegleValidationLegacy.determinerNiveau(String,Double,int,String,boolean)").complexite()).isEqualTo(28);
        }

        @Test
        void calculerVaut10() {
            assertThat(methode("CalculRemboursementLegacy.calculer(String,double,int,boolean)").complexite()).isEqualTo(10);
        }

        @Test
        void unTernaireCompte() {
            assertThat(methode("CircuitValidationService.calculerNiveau(Demande,int)").complexite()).isEqualTo(2);
        }
    }

    @Nested
    @DisplayName("Constats")
    class Constats {

        @Test
        @DisplayName("== sur String détecté ligne 56, pas le test == null de la ligne 26 (TODO 2)")
        void comparaisonDeReferences() {
            assertThat(constats(TypeConstat.COMPARAISON_REFERENCE_STRING))
                    .singleElement().satisfies(c -> {
                        assertThat(c.fichier()).isEqualTo(LEGACY);
                        assertThat(c.ligne()).isEqualTo(56);
                        assertThat(c.extrait()).isEqualTo("departement == DSI");
                    });
        }

        @Test
        @DisplayName("horloge cachée : Calendar.getInstance() ligne 86 (TODO 3)")
        void horlogeCachee() {
            assertThat(constats(TypeConstat.HORLOGE_CACHEE)).extracting(Constat::ligne, Constat::extrait)
                    .containsExactly(org.assertj.core.groups.Tuple.tuple(86, "Calendar.getInstance()"));
        }

        @Test
        void etatStatiqueMutable() {
            assertThat(constats(TypeConstat.ETAT_STATIQUE_MUTABLE)).extracting(Constat::ligne, Constat::extrait)
                    .containsExactly(org.assertj.core.groups.Tuple.tuple(15, "NIVEAU_MAX = 3"));
        }

        @Test
        void nombresMagiques() {
            List<Constat> nombres = constats(TypeConstat.NOMBRE_MAGIQUE);
            assertThat(nombres).extracting(c -> c.fichier().endsWith("RegleValidationLegacy.java") ? c.ligne() + "=" + c.extrait() : "")
                    .contains("31=1000", "33=5000", "43=1000", "46=5000", "58=1500", "63=2400", "87=14");
            assertThat(nombres).extracting(Constat::extrait).doesNotContain("0", "1", "2");
        }

        @Test
        void localeEtDivisionEntiere() {
            assertThat(constats(TypeConstat.LOCALE_IMPLICITE)).extracting(Constat::ligne).containsExactly(51);
            assertThat(constats(TypeConstat.DIVISION_ENTIERE)).singleElement().satisfies(c -> {
                assertThat(c.fichier()).isEqualTo(REMBOURSEMENT);
                assertThat(c.ligne()).isEqualTo(40);
            });
        }

        @Test
        @DisplayName("chaque extrait de constat figure réellement sur sa ligne")
        void extraitsExacts() {
            Fixtures.analyseur().analyser();
            var analyseur = Fixtures.analyseur();
            Faits f = analyseur.analyser();
            for (Constat c : f.constats()) {
                String ligne = analyseur.code().lignes(c.fichier()).get(c.ligne() - 1);
                assertThat(ligne).as(c.toString()).contains(c.extrait());
            }
        }
    }
}
