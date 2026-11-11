package com.neosoft.neoflow.legacyia;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;

/** Localise le dépôt NeoFlow : {@code NEOFLOW_RACINE}, sinon remontée depuis le dossier courant. */
public final class Projet {

    static final String SOURCES = "backend/src/main/java";
    static final String MARQUEUR = SOURCES + "/com/neosoft/neoflow/legacy";

    private Projet() {
    }

    public static Optional<Path> localiser(Path depart) {
        String variable = System.getenv("NEOFLOW_RACINE");
        if (variable != null && !variable.isBlank()) {
            Path racine = Path.of(variable).toAbsolutePath().normalize();
            return Files.isDirectory(racine.resolve(MARQUEUR)) ? Optional.of(racine) : Optional.empty();
        }
        for (Path p = depart.toAbsolutePath().normalize(); p != null; p = p.getParent()) {
            if (Files.isDirectory(p.resolve(MARQUEUR))) {
                return Optional.of(p);
            }
            Path dansSupports = p.resolve("fil-rouge/neoflow");
            if (Files.isDirectory(dansSupports.resolve(MARQUEUR))) {
                return Optional.of(dansSupports);
            }
        }
        return Optional.empty();
    }
}
