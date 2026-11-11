package com.neosoft.neoflow.legacyia;

import com.neosoft.neoflow.legacyia.analyse.AnalyseurLegacy;
import com.neosoft.neoflow.legacyia.analyse.ExportJson;
import com.neosoft.neoflow.legacyia.analyse.ExportMermaid;
import com.neosoft.neoflow.legacyia.analyse.Faits;
import com.neosoft.neoflow.legacyia.doc.GenerateurDocumentation;
import com.neosoft.neoflow.legacyia.ia.ContexteTraduction;
import com.neosoft.neoflow.legacyia.ia.Explicateur;
import com.neosoft.neoflow.legacyia.ia.Journal;
import com.neosoft.neoflow.legacyia.ia.ModeleClaude;
import com.neosoft.neoflow.legacyia.ia.ModeleLangage;
import com.neosoft.neoflow.legacyia.ia.ModeleSimule;
import com.neosoft.neoflow.legacyia.traduction.ExecuteurVitest;
import com.neosoft.neoflow.legacyia.traduction.TraducteurJsTs;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

/**
 * Point d'entrée du lab J08.
 *
 * <pre>
 * analyser                                   faits JSON + graphes Mermaid (déterministe, sans modèle)
 * expliquer  [--offline]                     explication et risques, citations vérifiées
 * impact     --cible Fichier.java:ligne --changement "..." [--offline]
 * documenter [--offline]                     README technique + JavaDoc proposées, noms vérifiés
 * traduire   [--offline] [--variante naive|fidele] [--reponse-simulee f.ts] [--conserver] [--fuseau Europe/Paris]
 * Options communes : --racine DOSSIER_NEOFLOW, --paquet com.neosoft.neoflow.legacy, --sortie target/legacy-ia,
 *                    --modele claude-sonnet-5-5, --sans-repli
 * </pre>
 */
public final class Main {

    private Main() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length == 0 || args[0].equals("--help")) {
            System.out.println(aide());
            return;
        }
        String commande = args[0];
        Map<String, String> options = options(args);
        Path racine = options.containsKey("racine") ? Path.of(options.get("racine"))
                : Projet.localiser(Path.of("")).orElseThrow(() -> new IllegalStateException(
                "Dépôt NeoFlow introuvable : lancez depuis labs/legacy-ia ou définissez NEOFLOW_RACINE"));
        Path sortie = Path.of(options.getOrDefault("sortie", "target/legacy-ia"));
        Files.createDirectories(sortie);
        Journal journal = new Journal(sortie.resolve("journal.jsonl"));

        AnalyseurLegacy analyseur = new AnalyseurLegacy(racine.resolve(Projet.SOURCES),
                options.getOrDefault("paquet", "com.neosoft.neoflow.legacy"));
        Faits faits = analyseur.analyser();
        ModeleLangage modele = options.containsKey("offline")
                ? new ModeleSimule(analyseur.code(), journal)
                : new ModeleClaude(options.getOrDefault("modele", ModeleClaude.MODELE_PAR_DEFAUT),
                !options.containsKey("sans-repli"), journal);

        switch (commande) {
            case "analyser" -> {
                ecrire(sortie.resolve("faits.json"), ExportJson.ecrire(faits));
                ecrire(sortie.resolve("graphe-appels.mmd"), ExportMermaid.grapheAppels(faits));
                ecrire(sortie.resolve("dependances.mmd"), ExportMermaid.dependances(faits));
                System.out.printf("%d méthode(s), %d appel(s), %d constat(s), %d endpoint(s) -> %s%n",
                        faits.methodes().size(), faits.appels().size(), faits.constats().size(),
                        faits.pointsEntree().size(), sortie.toAbsolutePath());
                faits.constats().forEach(c -> System.out.printf("  %-28s %s:%d  %s%n", c.type(),
                        c.fichier().substring(c.fichier().lastIndexOf('/') + 1), c.ligne(), c.extrait()));
            }
            case "expliquer" -> {
                Explicateur.RapportExplication rapport = new Explicateur(modele, analyseur.code()).expliquer(faits);
                ecrire(sortie.resolve("explication.md"), Explicateur.enMarkdown(rapport));
                ecrire(sortie.resolve("explication.json"), ExportJson.ecrire(rapport));
                System.out.printf("%d affirmation(s), %d rejetée(s) par la vérification des citations, %d risque(s) -> %s%n",
                        rapport.affirmations().size(), rapport.nbRejetees(), rapport.risquesRetenus().size(),
                        sortie.resolve("explication.md").toAbsolutePath());
            }
            case "impact" -> {
                Explicateur.RapportImpact rapport = new Explicateur(modele, analyseur.code())
                        .impact(faits, requis(options, "cible"), requis(options, "changement"));
                ecrire(sortie.resolve("impact.md"), Explicateur.enMarkdown(rapport));
                System.out.printf("Nature : %s ; %d appelant(s) ; %d endpoint(s) -> %s%n", rapport.nature(),
                        rapport.deterministe().appelants().size(), rapport.deterministe().pointsEntree().size(),
                        sortie.resolve("impact.md").toAbsolutePath());
            }
            case "documenter" -> {
                GenerateurDocumentation.DocumentationVerifiee doc = new GenerateurDocumentation(modele, analyseur.code())
                        .generer(faits);
                ecrire(sortie.resolve("README_TECHNIQUE.genere.md"), GenerateurDocumentation.readme(faits, doc));
                ecrire(sortie.resolve("javadoc.genere.md"), GenerateurDocumentation.javadocs(doc));
                System.out.printf("%d JavaDoc et %d section(s) retenues, %d rejet(s) -> %s%n", doc.javadocs().size(),
                        doc.sections().size(), doc.rejets().size(), sortie.resolve("README_TECHNIQUE.genere.md").toAbsolutePath());
                doc.rejets().forEach(r -> System.out.println("  rejet : " + r));
            }
            case "traduire" -> {
                ContexteTraduction contexte = new ContexteTraduction(options.getOrDefault("variante", "naive"),
                        options.containsKey("reponse-simulee") ? Path.of(options.get("reponse-simulee")) : null);
                TraducteurJsTs.Resultat resultat = new TraducteurJsTs(modele,
                        new ExecuteurVitest(options.getOrDefault("fuseau", "Europe/Paris")))
                        .traduire(racine.resolve("frontend"), sortie, options.containsKey("conserver"), contexte);
                System.out.println(resultat.sortieTests());
                System.out.printf("Parité : %s ; candidate %s ; copie : %s%n", resultat.pariteVerte() ? "VERTE" : "ROUGE",
                        resultat.conservee() ? "conservée dans frontend/src/utils/utils.ts" : "non conservée (original restauré)",
                        resultat.copieCandidate().toAbsolutePath());
                if (!resultat.pariteVerte()) {
                    System.exit(1);
                }
            }
            default -> throw new IllegalArgumentException("Commande inconnue : " + commande + "\n" + aide());
        }
    }

    static Map<String, String> options(String[] args) {
        Map<String, String> options = new HashMap<>();
        for (int i = 1; i < args.length; i++) {
            if (!args[i].startsWith("--")) {
                throw new IllegalArgumentException("Argument inattendu : " + args[i]);
            }
            String cle = args[i].substring(2);
            boolean avecValeur = i + 1 < args.length && !args[i + 1].startsWith("--");
            options.put(cle, avecValeur ? args[++i] : "true");
        }
        return options;
    }

    private static String requis(Map<String, String> options, String cle) {
        String valeur = options.get(cle);
        if (valeur == null) {
            throw new IllegalArgumentException("Option --" + cle + " obligatoire");
        }
        return valeur;
    }

    private static void ecrire(Path fichier, String contenu) throws IOException {
        Files.writeString(fichier, contenu, StandardCharsets.UTF_8);
    }

    private static String aide() {
        return """
                Usage : ./mvnw -q compile exec:java -Dexec.args="<commande> [options]"
                  analyser                faits JSON + graphes Mermaid (sans modèle)
                  expliquer  [--offline]  explication et risques, citations vérifiées
                  impact     --cible RegleValidationLegacy.java:56 --changement "remplacer == par equals" [--offline]
                  documenter [--offline]  README technique + JavaDoc proposées, noms vérifiés
                  traduire   [--offline] [--variante naive|fidele] [--reponse-simulee f.ts] [--conserver]
                Options : --racine, --paquet, --sortie, --modele (défaut claude-sonnet-5-5), --sans-repli, --fuseau
                Clé : ANTHROPIC_API_KEY (inutile avec --offline).""";
    }
}
