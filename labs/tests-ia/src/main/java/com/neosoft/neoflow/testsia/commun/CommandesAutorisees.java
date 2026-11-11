package com.neosoft.neoflow.testsia.commun;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Garde-fou J2 appliqué dans le code : les outils ne lancent que des programmes de la liste blanche
 * (JVM courante, wrapper Maven du projet), avec un délai maximal, et journalisent chaque commande.
 */
public final class CommandesAutorisees {

    public record Resultat(int code, String sortie) {
        public boolean reussi() {
            return code == 0;
        }
    }

    private final Journal journal;

    public CommandesAutorisees(Journal journal) {
        this.journal = journal;
    }

    public static String java() {
        return Path.of(System.getProperty("java.home"), "bin", "java").toString();
    }

    public Resultat executer(List<String> commande, Path repertoire, long delaiSecondes) {
        String programme = commande.get(0);
        boolean autorise = programme.equals(java()) || programme.endsWith("/mvnw") || programme.equals("./mvnw");
        if (!autorise) {
            throw new SecurityException("Commande hors liste blanche : " + programme);
        }
        journal.ecrire("tool_call", "commande", String.join(" ", commande), null, null, null);
        try {
            Process p = new ProcessBuilder(commande).directory(repertoire.toFile()).redirectErrorStream(true).start();
            byte[] sortie = p.getInputStream().readAllBytes();
            if (!p.waitFor(delaiSecondes, TimeUnit.SECONDS)) {
                p.destroyForcibly();
                return new Resultat(-1, "Délai dépassé (" + delaiSecondes + " s)");
            }
            String texte = new String(sortie, StandardCharsets.UTF_8);
            journal.ecrire("tool_result", "commande", null, "code=" + p.exitValue(), null, null);
            return new Resultat(p.exitValue(), texte);
        } catch (IOException e) {
            return new Resultat(-1, e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return new Resultat(-1, "Interrompu");
        }
    }
}
