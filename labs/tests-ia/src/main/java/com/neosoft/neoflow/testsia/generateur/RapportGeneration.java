package com.neosoft.neoflow.testsia.generateur;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

import com.neosoft.neoflow.testsia.modele.Consommation;

/** Bilan d'une génération : verdicts par tour, score de mutation, consommation. */
public record RapportGeneration(String classeCible, String modele, int tours, List<VerdictTest> verdicts,
        MesureMutation.Resultat mutation, List<String> questions, Consommation consommation) {

    public List<VerdictTest> acceptes() {
        return verdicts.stream().filter(v -> v.statut() == Statut.ACCEPTE).toList();
    }

    public List<VerdictTest> aArbitrer() {
        return verdicts.stream().filter(v -> v.statut() == Statut.ROUGE_A_ARBITRER).toList();
    }

    public List<VerdictTest> rejetes() {
        return verdicts.stream().filter(VerdictTest::rejete).toList();
    }

    public String versMarkdown() {
        StringBuilder sb = new StringBuilder();
        sb.append("# Génération de tests vérifiée — ").append(classeCible).append("\n\n");
        sb.append("Modèle : ").append(modele).append(" · tours : ").append(tours)
                .append(" · tokens entrée/sortie/lus en cache : ").append(consommation.entree()).append(" / ")
                .append(consommation.sortie()).append(" / ").append(consommation.lectureCache()).append("\n\n");
        sb.append("| Tour | Classe | Verdict | Exigence | Motifs |\n|---|---|---|---|---|\n");
        for (VerdictTest v : verdicts) {
            sb.append("| ").append(v.tour()).append(" | ").append(v.test().nomClasse()).append(" | ").append(v.statut())
                    .append(" | ").append(echapper(v.test().exigence())).append(" | ")
                    .append(echapper(String.join(" ; ", v.motifs()))).append(" |\n");
        }
        if (mutation != null) {
            sb.append(String.format(Locale.FRANCE, "%nMutation (PIT) sur les tests acceptés : %d mutants, %d tués, %d survivants, "
                    + "%d sans couverture, force = %.0f %%%n", mutation.generes(), mutation.tues(), mutation.survivants(),
                    mutation.sansCouverture(), mutation.score() * 100));
            mutation.mutantsSurvivants().forEach(m -> sb.append("- survivant : ").append(m).append('\n'));
        }
        if (!aArbitrer().isEmpty()) {
            sb.append("\n**À arbitrer par un humain** : ces tests échouent sur le code actuel. Défaut réel (test de reproduction)")
                    .append(" ou oracle faux ? Relire l'exigence citée avant toute décision.\n");
        }
        if (!questions.isEmpty()) {
            sb.append("\n## Questions du modèle (comportements non spécifiés)\n");
            questions.forEach(q -> sb.append("- ").append(q).append('\n'));
        }
        return sb.toString();
    }

    /** Écrit le rapport et les sources des tests acceptés et à arbitrer (jamais dans src/test du projet). */
    public void ecrire(Path repertoire, String paquet) {
        try {
            Files.createDirectories(repertoire);
            Files.writeString(repertoire.resolve("rapport-generation.md"), versMarkdown());
            for (VerdictTest v : verdicts) {
                if (v.statut() == Statut.ACCEPTE || v.statut() == Statut.ROUGE_A_ARBITRER) {
                    Path dossier = repertoire.resolve(v.statut() == Statut.ACCEPTE ? "acceptes" : "a-arbitrer")
                            .resolve(paquet.replace('.', '/'));
                    Files.createDirectories(dossier);
                    Files.writeString(dossier.resolve(v.test().nomClasse() + ".java"), v.test().source());
                }
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static String echapper(String texte) {
        return texte == null ? "" : texte.replace('|', '/').replace('\n', ' ');
    }
}
