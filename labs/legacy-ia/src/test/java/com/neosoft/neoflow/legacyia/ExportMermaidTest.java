package com.neosoft.neoflow.legacyia;

import com.neosoft.neoflow.legacyia.analyse.ExportJson;
import com.neosoft.neoflow.legacyia.analyse.ExportMermaid;
import com.neosoft.neoflow.legacyia.analyse.Faits;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ExportMermaidTest {

    @Test
    void grapheDAppelsEtDependances() {
        Faits faits = Fixtures.faits();
        String graphe = ExportMermaid.grapheAppels(faits);
        assertThat(graphe).startsWith("flowchart LR\n")
                .contains("subgraph cible[\"com.neosoft.neoflow.legacy\"]")
                .contains("RegleValidationLegacy.determinerNiveau<br/>CCN 28")
                .contains("([\"POST /api/demandes/{id}/soumettre\"])")
                .contains("-->|\"l.32\"|")
                .contains("class ");
        assertThat(ExportMermaid.dependances(faits)).contains("CircuitValidationService -->|\"1 appel(s)\"| RegleValidationLegacy");
    }

    @Test
    void jsonRelisible() {
        Faits faits = Fixtures.faits();
        Faits relu = ExportJson.lire(ExportJson.ecrire(faits), Faits.class);
        assertThat(relu).isEqualTo(faits);
    }
}
