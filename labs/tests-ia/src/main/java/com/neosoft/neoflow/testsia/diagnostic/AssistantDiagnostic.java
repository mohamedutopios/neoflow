package com.neosoft.neoflow.testsia.diagnostic;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.neosoft.neoflow.testsia.commun.Journal;
import com.neosoft.neoflow.testsia.modele.Consommation;
import com.neosoft.neoflow.testsia.modele.DemandeModele;
import com.neosoft.neoflow.testsia.modele.ModeleLangage;
import com.neosoft.neoflow.testsia.modele.ReponseModele;

/**
 * Assistant de diagnostic : lecture des artefacts, extraction déterministe, hypothèses structurées du modèle,
 * contrôle déterministe ; un second tour au plus si toutes les hypothèses ont été rejetées.
 */
public final class AssistantDiagnostic {

    private static final Pattern FRAME = Pattern.compile("at ([\\w.$]+)\\.([\\w$<>]+)\\(([\\w$]+\\.java):(\\d+)\\)");
    private static final int TOURS_MAX = 2;

    private final ModeleLangage modele;
    private final ExtracteurIndices extracteur;
    private final ControleHypotheses controle = new ControleHypotheses();
    private final PromptsDiagnostic prompts = new PromptsDiagnostic();
    private final Journal journal;
    private final String prefixeApplicatif;

    public AssistantDiagnostic(ModeleLangage modele, String prefixeApplicatif, Journal journal) {
        this.modele = modele;
        this.extracteur = new ExtracteurIndices(prefixeApplicatif);
        this.journal = journal;
        this.prefixeApplicatif = prefixeApplicatif;
    }

    /** @param sources répertoire src/main/java du projet (facultatif) pour joindre l'extrait de code */
    public RapportDiagnostic diagnostiquer(Path logs, Path trace, String traceId, Path sources) {
        List<EvenementLog> evenements = new LecteurLogsEcs().lire(logs);
        DossierIncident dossier = extracteur.extraire(evenements, new LecteurTraceJaeger().lire(trace), traceId);
        String extrait = sources == null ? null : extraitCode(evenements, dossier.traceId(), sources);
        journal.ecrire("tool_result", "extracteur", null, dossier.faits().size() + " faits", null, null);

        List<String> rejets = new ArrayList<>();
        List<String> tousRejets = new ArrayList<>();
        Consommation consommation = Consommation.NULLE;
        ControleHypotheses.Resultat resultat = new ControleHypotheses.Resultat(List.of(), List.of());
        List<String> inconnues = List.of();
        for (int tour = 1; tour <= TOURS_MAX; tour++) {
            DemandeModele demande = prompts.demande(dossier, extrait, rejets);
            ReponseModele<Hypotheses> reponse = modele.demander(demande, Hypotheses.class);
            consommation = consommation.plus(reponse.consommation());
            journal.ecrire("llm", PromptsDiagnostic.TACHE, demande.utilisateur(),
                    reponse.contenu().hypotheses().size() + " hypothèse(s)", reponse.consommation(), modele.nom());
            resultat = controle.controler(reponse.contenu(), dossier);
            inconnues = reponse.contenu().inconnues();
            tousRejets.addAll(resultat.rejets());
            if (!resultat.retenues().isEmpty()) {
                break;
            }
            rejets = resultat.rejets();
        }
        return new RapportDiagnostic(dossier, resultat.retenues(), tousRejets, inconnues, modele.nom(), consommation);
    }

    /** Lignes autour de la première frame applicative de l'exception (lecture seule du code). */
    String extraitCode(List<EvenementLog> evenements, String traceId, Path sources) {
        for (EvenementLog e : evenements) {
            if (!traceId.equals(e.traceId())) {
                continue;
            }
            for (String frame : e.pile()) {
                Matcher m = FRAME.matcher(frame);
                if (m.find() && m.group(1).startsWith(prefixeApplicatif)) {
                    String classe = m.group(1);
                    int ligne = Integer.parseInt(m.group(4));
                    Path fichier = sources.resolve(classe.substring(0, classe.lastIndexOf('.')).replace('.', '/'))
                            .resolve(m.group(3));
                    if (!Files.exists(fichier)) {
                        return null;
                    }
                    try {
                        List<String> lignes = Files.readAllLines(fichier);
                        StringBuilder sb = new StringBuilder(fichier.getFileName().toString()).append('\n');
                        for (int i = Math.max(1, ligne - 5); i <= Math.min(lignes.size(), ligne + 2); i++) {
                            sb.append(i == ligne ? ">> " : "   ").append(i).append(": ").append(lignes.get(i - 1)).append('\n');
                        }
                        return sb.toString();
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    }
                }
            }
        }
        return null;
    }
}
