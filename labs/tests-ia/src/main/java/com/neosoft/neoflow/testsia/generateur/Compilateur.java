package com.neosoft.neoflow.testsia.generateur;

import java.io.IOException;
import java.io.StringWriter;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

/** Compile une classe de test proposée contre le classpath du projet (javax.tools, dans la JVM du lab). */
public final class Compilateur {

    public record Resultat(boolean reussi, List<String> erreurs) {
    }

    private final JavaCompiler compilateur = ToolProvider.getSystemJavaCompiler();

    /**
     * @param nomQualifie nom complet de la classe (package.Classe)
     * @param source      code source
     * @param classpath   classpath de compilation
     * @param sortie      répertoire des .class produits
     */
    public Resultat compiler(String nomQualifie, String source, List<Path> classpath, Path sortie) {
        try {
            Path sources = sortie.resolveSibling("sources-proposees");
            Path fichier = sources.resolve(nomQualifie.replace('.', '/') + ".java");
            Files.createDirectories(fichier.getParent());
            Files.createDirectories(sortie);
            Files.writeString(fichier, source, StandardCharsets.UTF_8);
            DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
            try (StandardJavaFileManager fm = compilateur.getStandardFileManager(diagnostics, Locale.FRENCH, StandardCharsets.UTF_8)) {
                List<String> options = List.of("-d", sortie.toString(), "-cp",
                        String.join(java.io.File.pathSeparator, classpath.stream().map(Path::toString).toList()),
                        "-encoding", "UTF-8", "-proc:none", "-nowarn");
                boolean ok = compilateur.getTask(new StringWriter(), fm, diagnostics, options, null,
                        fm.getJavaFileObjects(fichier.toFile())).call();
                List<String> erreurs = diagnostics.getDiagnostics().stream()
                        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                        .map(d -> "ligne " + d.getLineNumber() + " : " + d.getMessage(Locale.FRENCH))
                        .toList();
                return new Resultat(ok, erreurs);
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
