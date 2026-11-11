package com.neosoft.neoflow.legacyia;

import com.neosoft.neoflow.legacyia.analyse.AnalyseurLegacy;
import com.neosoft.neoflow.legacyia.analyse.Faits;
import com.neosoft.neoflow.legacyia.analyse.Faits.TypeConstat;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/** Même analyse sur le vrai dépôt NeoFlow quand il est présent (ignoré sinon). */
@DisplayName("Analyse du vrai socle NeoFlow")
class SocleReelTest {

    @Test
    void faitsClesDuLegacy() {
        Optional<Path> racine = Projet.localiser(Path.of(""));
        assumeTrue(racine.isPresent(), "dépôt NeoFlow introuvable (NEOFLOW_RACINE)");
        Faits faits = new AnalyseurLegacy(racine.get().resolve(Projet.SOURCES), "com.neosoft.neoflow.legacy").analyser();

        assertThat(faits.constats()).anySatisfy(c -> {
            assertThat(c.type()).isEqualTo(TypeConstat.COMPARAISON_REFERENCE_STRING);
            assertThat(c.extrait()).isEqualTo("departement == DSI");
        });
        assertThat(faits.constats()).anySatisfy(c -> assertThat(c.type()).isEqualTo(TypeConstat.HORLOGE_CACHEE));
        assertThat(faits.appels()).anySatisfy(a -> assertThat(a.appele()).startsWith("RegleValidationLegacy.determinerNiveau"));
        assertThat(faits.pointsEntree()).anySatisfy(pe -> assertThat(pe.chemin()).isEqualTo("/api/demandes/{id}/soumettre"));
    }
}
