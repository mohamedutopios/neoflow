package com.neosoft.neoflow.legacyia;

import com.neosoft.neoflow.legacyia.analyse.AnalyseurLegacy;
import com.neosoft.neoflow.legacyia.analyse.Faits;

import java.net.URISyntaxException;
import java.nio.file.Path;

/** Analyse des copies figées du socle (src/test/resources/socle-extrait). */
public final class Fixtures {

    public static final String LEGACY = "com/neosoft/neoflow/legacy/RegleValidationLegacy.java";
    public static final String REMBOURSEMENT = "com/neosoft/neoflow/legacy/CalculRemboursementLegacy.java";

    private Fixtures() {
    }

    public static Path racine() {
        try {
            return Path.of(Fixtures.class.getResource("/socle-extrait").toURI());
        } catch (URISyntaxException e) {
            throw new IllegalStateException(e);
        }
    }

    public static AnalyseurLegacy analyseur() {
        return new AnalyseurLegacy(racine(), "com.neosoft.neoflow.legacy");
    }

    public static Faits faits() {
        return analyseur().analyser();
    }
}
