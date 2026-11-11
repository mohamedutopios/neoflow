package com.neosoft.neoflow.testsia.generateur;

import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import com.neosoft.neoflow.testsia.commun.CommandesAutorisees;

/**
 * Score de mutation des tests acceptés sur la classe cible : PIT en ligne de commande, dans une JVM fille.
 * Score = mutants tués / mutants couverts (« test strength » de PIT).
 */
public final class MesureMutation {

    public record Resultat(int generes, int tues, int survivants, int sansCouverture, List<String> mutantsSurvivants) {
        public double score() {
            int couverts = tues + survivants;
            return couverts == 0 ? 0.0 : (double) tues / couverts;
        }
    }

    private static final String[] CLASSES_PIT = {
        "org.pitest.mutationtest.commandline.MutationCoverageReport",
        "org.pitest.mutationtest.tooling.EntryPoint",
        "org.pitest.mutationtest.engine.gregor.config.GregorEngineFactory",
        "org.pitest.junit5.JUnit5TestPluginFactory",
        "org.pitest.util.Log",
    };

    private final CommandesAutorisees commandes;

    public MesureMutation(CommandesAutorisees commandes) {
        this.commandes = commandes;
    }

    public Resultat mesurer(String classeCible, List<String> tests, Path classesTests, ContexteProjet projet) {
        Path rapport = projet.travail().resolve("pit");
        List<String> cp = new ArrayList<>();
        cp.add(classesTests.toString());
        projet.classpath().forEach(p -> cp.add(p.toString()));
        for (String nom : CLASSES_PIT) {
            String jar = emplacementSiPresent(nom);
            if (jar != null && !cp.contains(jar)) {
                cp.add(jar);
            }
        }
        cp.addAll(dependancesPit());
        cp.add(ExecuteurTests.emplacement(org.junit.platform.launcher.core.LauncherFactory.class));
        List<String> cmd = List.of(CommandesAutorisees.java(), "-cp", String.join(File.pathSeparator, cp),
                "org.pitest.mutationtest.commandline.MutationCoverageReport",
                "--reportDir", rapport.toString(),
                "--targetClasses", classeCible,
                "--targetTests", String.join(",", tests),
                "--sourceDirs", projet.sources().toString(),
                "--outputFormats", "CSV",
                "--timestampedReports=false",
                "--threads", "2");
        CommandesAutorisees.Resultat r = commandes.executer(cmd, projet.travail(), 900);
        Path csv = rapport.resolve("mutations.csv");
        if (!Files.exists(csv)) {
            throw new IllegalStateException("PIT n'a pas produit de rapport :\n" + r.sortie());
        }
        return lireCsv(csv);
    }

    static Resultat lireCsv(Path csv) {
        try {
            int generes = 0, tues = 0, survivants = 0, sansCouverture = 0;
            List<String> survivantsDetail = new ArrayList<>();
            for (String ligne : Files.readAllLines(csv)) {
                String[] c = ligne.split(",");
                if (c.length < 6) {
                    continue;
                }
                generes++;
                switch (c[5]) {
                    case "KILLED", "TIMED_OUT", "MEMORY_ERROR", "RUN_ERROR" -> tues++;
                    case "SURVIVED" -> {
                        survivants++;
                        survivantsDetail.add(c[3] + " ligne " + c[4] + " : " + c[2].replace("org.pitest.mutationtest.engine.gregor.mutators.", ""));
                    }
                    case "NO_COVERAGE" -> sansCouverture++;
                    default -> { }
                }
            }
            return new Resultat(generes, tues, survivants, sansCouverture, survivantsDetail);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /** Dépendances de PIT (asm, jopt...) prises sur le classpath du lab. */
    private static List<String> dependancesPit() {
        List<String> jars = new ArrayList<>();
        for (String element : System.getProperty("java.class.path").split(File.pathSeparator)) {
            String nom = Path.of(element).getFileName() == null ? "" : Path.of(element).getFileName().toString();
            if (nom.startsWith("asm") || nom.startsWith("jopt-simple") || nom.startsWith("commons-text")
                    || nom.startsWith("commons-lang3") || nom.startsWith("pitest")) {
                jars.add(element);
            }
        }
        if (jars.isEmpty()) {
            Path lib = Path.of(ExecuteurTests.emplacement(MesureMutation.class)).resolveSibling("lib");
            if (Files.isDirectory(lib)) {
                try (var flux = Files.list(lib)) {
                    flux.map(Path::toString).filter(s -> s.contains("asm") || s.contains("jopt") || s.contains("pitest")
                            || s.contains("commons-text") || s.contains("commons-lang3")).forEach(jars::add);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            }
        }
        return jars;
    }

    private static String emplacementSiPresent(String classe) {
        try {
            return ExecuteurTests.emplacement(Class.forName(classe, false, MesureMutation.class.getClassLoader()));
        } catch (ClassNotFoundException | LinkageError e) {
            return null;
        }
    }
}
