package com.neosoft.neoflow.testsia.generateur;

import java.io.File;
import java.net.URISyntaxException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.platform.launcher.core.LauncherFactory;

import com.neosoft.neoflow.testsia.commun.CommandesAutorisees;

/**
 * Exécute des classes de test compilées dans une JVM fille : le classpath du projet (sa version de JUnit,
 * de Spring, de Mockito) reste isolé de celui du lab.
 */
public final class ExecuteurTests {

    public record Resultat(boolean reussi, int nbTests, String message) {
    }

    private final CommandesAutorisees commandes;

    public ExecuteurTests(CommandesAutorisees commandes) {
        this.commandes = commandes;
    }

    public Map<String, Resultat> executer(List<String> classes, Path classesTests, ContexteProjet projet) {
        List<String> cmd = new ArrayList<>(List.of(CommandesAutorisees.java(), "-cp", classpath(classesTests, projet),
                LanceurJUnit.class.getName()));
        cmd.addAll(classes);
        CommandesAutorisees.Resultat r = commandes.executer(cmd, projet.travail(), 300);
        Map<String, Resultat> resultats = new LinkedHashMap<>();
        for (String ligne : r.sortie().split("\\R")) {
            if (ligne.startsWith("RESULTAT|")) {
                String[] p = ligne.split("\\|", 5);
                resultats.put(p[1], new Resultat("REUSSI".equals(p[2]), Integer.parseInt(p[3]), p.length > 4 ? p[4] : ""));
            }
        }
        for (String classe : classes) {
            resultats.putIfAbsent(classe, new Resultat(false, 0, "exécution impossible : " + dernieresLignes(r.sortie())));
        }
        return resultats;
    }

    /** Projet d'abord (sa version de JUnit prime), puis le lanceur du lab en repli. */
    static String classpath(Path classesTests, ContexteProjet projet) {
        List<String> cp = new ArrayList<>();
        cp.add(classesTests.toString());
        projet.classpath().forEach(p -> cp.add(p.toString()));
        cp.add(emplacement(LanceurJUnit.class));
        cp.add(emplacement(LauncherFactory.class));
        return String.join(File.pathSeparator, cp);
    }

    static String emplacement(Class<?> classe) {
        try {
            return Path.of(classe.getProtectionDomain().getCodeSource().getLocation().toURI()).toString();
        } catch (URISyntaxException e) {
            throw new IllegalStateException(e);
        }
    }

    private static String dernieresLignes(String sortie) {
        String[] lignes = sortie.strip().split("\\R");
        return String.join(" / ", java.util.Arrays.copyOfRange(lignes, Math.max(0, lignes.length - 3), lignes.length));
    }
}
