package com.neosoft.neoflow.testsia.generateur;

import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** Projet minimal pour les tests du lab : classe exemple.Pagination compilée, JUnit et AssertJ du lab. */
final class CibleMini {

    static final String SPEC = """
            | Id | Exigence |
            |---|---|
            | PG-01 | index(page) renvoie page : l'API est numérotée à partir de 0 (page 1 → index 1). |
            | PG-02 | Une page négative est refusée : IllegalArgumentException dont le message contient « négative ». |
            """;

    private CibleMini() {
    }

    static ContexteProjet projet(Path travail) {
        try {
            Path sources = Path.of(CibleMini.class.getResource("/cible-mini").toURI());
            Path classes = travail.resolve("classes-cible");
            String source = Files.readString(sources.resolve("exemple/Pagination.java"));
            Compilateur.Resultat r = new Compilateur().compiler("exemple.Pagination", source, labClasspath(), classes);
            if (!r.reussi()) {
                throw new IllegalStateException(r.erreurs().toString());
            }
            List<Path> cp = new ArrayList<>();
            cp.add(classes);
            cp.addAll(labClasspath());
            return new ContexteProjet(sources, cp, travail);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        } catch (URISyntaxException e) {
            throw new IllegalStateException(e);
        }
    }

    static CibleGeneration cible(ContexteProjet projet) {
        try {
            return new CibleGeneration("exemple.Pagination",
                    Files.readString(projet.sources().resolve("exemple/Pagination.java")), SPEC);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /** JUnit, AssertJ… du lab (surefire est configuré avec useManifestOnlyJar=false). */
    static List<Path> labClasspath() {
        List<Path> cp = new ArrayList<>();
        for (String e : System.getProperty("java.class.path").split(File.pathSeparator)) {
            String nom = Path.of(e).getFileName().toString();
            if (nom.startsWith("junit") || nom.startsWith("assertj") || nom.startsWith("opentest4j") || nom.startsWith("apiguardian")) {
                cp.add(Path.of(e));
            }
        }
        return cp;
    }

    static String test(String nom, String corps) {
        return """
                package exemple;
                import static org.assertj.core.api.Assertions.assertThat;
                import static org.assertj.core.api.Assertions.assertThatThrownBy;
                import static org.junit.jupiter.api.Assertions.assertTrue;
                import org.junit.jupiter.api.Test;
                class %s {
                    @Test
                    void cas() {
                        %s
                    }
                }
                """.formatted(nom, corps);
    }

    static String proposition(String... tests) {
        return "{\"tests\":[" + String.join(",", tests) + "],\"questions\":[]}";
    }

    static String json(String nom, String exigence, String corps) {
        return "{\"nomClasse\":\"" + nom + "\",\"exigence\":\"" + exigence + "\",\"oracle\":\"" + exigence
                + "\",\"source\":" + com.fasterxml.jackson.databind.node.TextNode.valueOf(test(nom, corps)).toString() + "}";
    }
}
