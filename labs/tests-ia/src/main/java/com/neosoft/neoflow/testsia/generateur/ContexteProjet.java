package com.neosoft.neoflow.testsia.generateur;

import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import com.neosoft.neoflow.testsia.commun.CommandesAutorisees;

/**
 * Projet contenant la classe cible : sources, classpath de test, répertoire de travail du lab.
 *
 * @param sources   répertoire des sources principales (src/main/java), pour PIT et pour lire la classe cible
 * @param classpath classes compilées du projet et dépendances de test (JUnit, AssertJ, Mockito...)
 * @param travail   répertoire où le lab compile et exécute les tests proposés (jamais src/test du projet)
 */
public record ContexteProjet(Path sources, List<Path> classpath, Path travail) {

    /**
     * Projet Maven (ex. backend NeoFlow) : compile le projet et calcule son classpath de test
     * avec le wrapper du projet (commandes de la liste blanche).
     */
    public static ContexteProjet depuisProjetMaven(Path projet, Path travail, CommandesAutorisees commandes) {
        Path fichierClasspath = travail.toAbsolutePath().resolve("classpath-projet.txt");
        try {
            Files.createDirectories(travail);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        CommandesAutorisees.Resultat r = commandes.executer(List.of("./mvnw", "-q", "-B", "test-compile",
                "dependency:build-classpath", "-Dmdep.includeScope=test", "-Dmdep.outputFile=" + fichierClasspath),
                projet, 900);
        if (!r.reussi()) {
            throw new IllegalStateException("Compilation du projet impossible :\n" + r.sortie());
        }
        try {
            List<Path> cp = new ArrayList<>();
            cp.add(projet.resolve("target/classes").toAbsolutePath());
            cp.add(projet.resolve("target/test-classes").toAbsolutePath());
            Arrays.stream(Files.readString(fichierClasspath).trim().split(File.pathSeparator))
                    .filter(s -> !s.isBlank()).map(Path::of).forEach(cp::add);
            return new ContexteProjet(projet.resolve("src/main/java").toAbsolutePath(), cp, travail.toAbsolutePath());
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public String classpathTexte() {
        return String.join(File.pathSeparator, classpath.stream().map(Path::toString).toList());
    }
}
