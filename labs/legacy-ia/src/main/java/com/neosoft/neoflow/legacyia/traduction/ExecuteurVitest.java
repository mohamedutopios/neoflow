package com.neosoft.neoflow.legacyia.traduction;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Exécute {@code npx vitest run <fichier de parité>} dans le dossier du frontend. Commande fixe
 * (allowlist du J2) : aucun argument ne vient du modèle.
 */
public final class ExecuteurVitest implements ExecuteurParite {

    static final String TEST_PARITE = "src/utils/utils.parite.test.ts";
    private static final int LIMITE_SORTIE = 6_000;

    private final String fuseau;

    /** @param fuseau valeur de {@code NEOFLOW_TEST_TZ} (ex. {@code Europe/Paris}), ou {@code null} */
    public ExecuteurVitest(String fuseau) {
        this.fuseau = fuseau;
    }

    @Override
    public Resultat executer(Path dossierFrontend) {
        boolean windows = System.getProperty("os.name").toLowerCase().contains("win");
        ProcessBuilder pb = new ProcessBuilder(List.of(windows ? "npx.cmd" : "npx", "vitest", "run", TEST_PARITE))
                .directory(dossierFrontend.toFile())
                .redirectErrorStream(true);
        if (fuseau != null) {
            pb.environment().put("NEOFLOW_TEST_TZ", fuseau);
        }
        try {
            Process processus = pb.start();
            byte[] sortie = processus.getInputStream().readAllBytes();
            if (!processus.waitFor(10, TimeUnit.MINUTES)) {
                processus.destroyForcibly();
                return new Resultat(false, -1, "délai dépassé");
            }
            String texte = new String(sortie, StandardCharsets.UTF_8);
            if (texte.length() > LIMITE_SORTIE) {
                texte = texte.substring(0, LIMITE_SORTIE) + "\n[... sortie tronquée ...]";
            }
            return new Resultat(processus.exitValue() == 0, processus.exitValue(), texte);
        } catch (IOException e) {
            throw new UncheckedIOException("npx introuvable ? Node 20 requis dans " + dossierFrontend, e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return new Resultat(false, -1, "interrompu");
        }
    }
}
