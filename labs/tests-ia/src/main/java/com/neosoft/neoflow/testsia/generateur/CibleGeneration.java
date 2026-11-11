package com.neosoft.neoflow.testsia.generateur;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Classe à tester et spécification qui fixe les comportements attendus (exigences ou scénarios du J3).
 *
 * @param classeCible nom qualifié (ex. com.neosoft.neoflow.validation.CircuitValidationService)
 */
public record CibleGeneration(String classeCible, String codeSource, String specification) {

    public static CibleGeneration lire(ContexteProjet projet, String classeCible, Path specification) {
        Path source = projet.sources().resolve(classeCible.replace('.', '/') + ".java");
        try {
            return new CibleGeneration(classeCible, Files.readString(source), Files.readString(specification));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public String paquet() {
        int i = classeCible.lastIndexOf('.');
        return i < 0 ? "" : classeCible.substring(0, i);
    }

    public String nomSimple() {
        return classeCible.substring(classeCible.lastIndexOf('.') + 1);
    }
}
