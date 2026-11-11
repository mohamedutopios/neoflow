package com.neosoft.neoflow.testsia;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Map;

import com.neosoft.neoflow.testsia.commun.CommandesAutorisees;
import com.neosoft.neoflow.testsia.commun.Journal;
import com.neosoft.neoflow.testsia.diagnostic.AssistantDiagnostic;
import com.neosoft.neoflow.testsia.diagnostic.RapportDiagnostic;
import com.neosoft.neoflow.testsia.generateur.CibleGeneration;
import com.neosoft.neoflow.testsia.generateur.ContexteProjet;
import com.neosoft.neoflow.testsia.generateur.ExecuteurTests;
import com.neosoft.neoflow.testsia.generateur.GenerateurVerifie;
import com.neosoft.neoflow.testsia.generateur.MesureMutation;
import com.neosoft.neoflow.testsia.generateur.RapportGeneration;
import com.neosoft.neoflow.testsia.generateur.Verificateur;
import com.neosoft.neoflow.testsia.modele.ModeleClaude;
import com.neosoft.neoflow.testsia.modele.ModeleLangage;
import com.neosoft.neoflow.testsia.modele.ModeleSimule;
import com.anthropic.client.okhttp.AnthropicOkHttpClient;
import com.anthropic.models.messages.OutputConfig;

/**
 * Point d'entrée du lab J07.
 * <pre>
 * ./tests-ia generer --projet ../../backend --classe com.neosoft.neoflow.validation.CircuitValidationService \
 *                    --spec specs/circuit-validation.md [--offline] [--tours 3] [--seuil 0.6] [--sans-mutation]
 * ./tests-ia diagnostiquer --logs incident/backend.log --trace incident/trace.json [--sources ../../backend/src/main/java] [--offline]
 * ./tests-ia analyser --test MonTest.java --cible ClasseTestee.java      (revue d'un test existant, sans modèle)
 * </pre>
 * Options communes : --modele (défaut claude-sonnet-5-5), --reponses fichier.json (réponses simulées),
 * --sortie répertoire, --journal fichier.jsonl, --sans-repli (désactive le repli serveur en cas de refus).
 */
public final class Application {

    private Application() {
    }

    public static void main(String[] args) {
        if (args.length == 0 || !java.util.Set.of("generer", "diagnostiquer", "analyser").contains(args[0])) {
            System.err.println("Usage : tests-ia generer|diagnostiquer|analyser [options]  (voir README.md)");
            System.exit(2);
        }
        if (args[0].equals("analyser")) {
            System.exit(analyser(options(args)));
        }
        Map<String, String> o = options(args);
        String session = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"));
        Path sortie = Path.of(o.getOrDefault("sortie", "target/tests-ia")).toAbsolutePath();
        Journal journal = new Journal(Path.of(o.getOrDefault("journal", sortie.resolve("journal.jsonl").toString())), session);
        int code = args[0].equals("generer") ? generer(o, sortie, journal) : diagnostiquer(o, sortie, journal);
        System.exit(code);
    }

    static int generer(Map<String, String> o, Path sortie, Journal journal) {
        CommandesAutorisees commandes = new CommandesAutorisees(journal);
        String classe = exiger(o, "classe");
        ContexteProjet projet = ContexteProjet.depuisProjetMaven(Path.of(exiger(o, "projet")).toAbsolutePath(),
                sortie.resolve("travail"), commandes);
        CibleGeneration cible = CibleGeneration.lire(projet, classe, Path.of(exiger(o, "spec")));
        ModeleLangage modele = modele(o, "offline/generation-" + cible.nomSimple() + ".json");
        MesureMutation mutation = o.containsKey("sans-mutation") ? null : new MesureMutation(commandes);
        GenerateurVerifie generateur = new GenerateurVerifie(modele, new Verificateur(new ExecuteurTests(commandes)), mutation, journal);
        RapportGeneration rapport = generateur.generer(cible, projet,
                Integer.parseInt(o.getOrDefault("tours", "3")), Double.parseDouble(o.getOrDefault("seuil", "0.6")));
        rapport.ecrire(sortie, cible.paquet());
        System.out.println(rapport.versMarkdown());
        System.out.println("Rapport et tests proposés : " + sortie + " (à relire avant de copier dans src/test)");
        return 0;
    }

    static int diagnostiquer(Map<String, String> o, Path sortie, Journal journal) {
        ModeleLangage modele = modele(o, "offline/diagnostic.json");
        AssistantDiagnostic assistant = new AssistantDiagnostic(modele, o.getOrDefault("prefixe", "com.neosoft"), journal);
        RapportDiagnostic rapport = assistant.diagnostiquer(Path.of(exiger(o, "logs")), Path.of(exiger(o, "trace")),
                o.get("trace-id"), o.containsKey("sources") ? Path.of(o.get("sources")) : null);
        try {
            Files.createDirectories(sortie);
            Files.writeString(sortie.resolve("rapport-diagnostic.md"), rapport.versMarkdown());
        } catch (java.io.IOException e) {
            throw new java.io.UncheckedIOException(e);
        }
        System.out.println(rapport.versMarkdown());
        return rapport.hypotheses().isEmpty() ? 1 : 0;
    }

    /** Applique l'analyseur anti-tautologie à une classe de test existante (aucun appel au modèle). */
    static int analyser(Map<String, String> o) {
        try {
            String test = Files.readString(Path.of(exiger(o, "test")));
            String cible = Files.readString(Path.of(exiger(o, "cible")));
            String nomCible = Path.of(o.get("cible")).getFileName().toString().replace(".java", "");
            var motifs = new com.neosoft.neoflow.testsia.generateur.AnalyseurTautologies()
                    .analyser(test, nomCible, com.neosoft.neoflow.testsia.generateur.AnalyseurTautologies.methodesPubliques(cible));
            motifs.forEach(m -> System.out.println("TAUTOLOGIE  " + m));
            System.out.println(motifs.isEmpty() ? "Aucune tautologie détectée (la mutation reste le juge)." : motifs.size() + " motif(s).");
            return motifs.isEmpty() ? 0 : 1;
        } catch (java.io.IOException e) {
            throw new java.io.UncheckedIOException(e);
        }
    }

    static ModeleLangage modele(Map<String, String> o, String reponsesParDefaut) {
        if (o.containsKey("offline")) {
            return o.containsKey("reponses") ? ModeleSimule.depuisFichier(Path.of(o.get("reponses")))
                    : ModeleSimule.depuisRessource(reponsesParDefaut);
        }
        return new ModeleClaude(AnthropicOkHttpClient.fromEnv(), o.getOrDefault("modele", ModeleClaude.MODELE_PAR_DEFAUT),
                OutputConfig.Effort.of(o.getOrDefault("effort", "medium")), !o.containsKey("sans-repli"));
    }

    static Map<String, String> options(String[] args) {
        Map<String, String> o = new HashMap<>();
        for (int i = 1; i < args.length; i++) {
            if (!args[i].startsWith("--")) {
                throw new IllegalArgumentException("Option inattendue : " + args[i]);
            }
            String cle = args[i].substring(2);
            if (i + 1 < args.length && !args[i + 1].startsWith("--")) {
                o.put(cle, args[++i]);
            } else {
                o.put(cle, "true");
            }
        }
        return o;
    }

    private static String exiger(Map<String, String> o, String cle) {
        String v = o.get(cle);
        if (v == null) {
            throw new IllegalArgumentException("Option obligatoire : --" + cle);
        }
        return v;
    }
}
