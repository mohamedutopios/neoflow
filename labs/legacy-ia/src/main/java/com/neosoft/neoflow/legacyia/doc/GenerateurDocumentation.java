package com.neosoft.neoflow.legacyia.doc;

import com.neosoft.neoflow.legacyia.analyse.CodeSource;
import com.neosoft.neoflow.legacyia.analyse.ExportJson;
import com.neosoft.neoflow.legacyia.analyse.ExportMermaid;
import com.neosoft.neoflow.legacyia.analyse.Faits;
import com.neosoft.neoflow.legacyia.analyse.Faits.Methode;
import com.neosoft.neoflow.legacyia.ia.ModeleLangage;
import com.neosoft.neoflow.legacyia.ia.Reponses.Documentation;
import com.neosoft.neoflow.legacyia.ia.Reponses.JavadocProposee;
import com.neosoft.neoflow.legacyia.ia.Reponses.SectionReadme;
import com.neosoft.neoflow.legacyia.ia.Requete;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * Documentation vivante : les parties factuelles (endpoints, méthodes, complexité, constats, graphe Mermaid)
 * sont calculées ; la prose (JavaDoc, sections du README) est rédigée par le modèle puis vérifiée.
 * Rien n'est écrit dans les sources : l'humain relit et applique.
 */
public final class GenerateurDocumentation {

    static final String SYSTEME = """
            Vous rédigez la documentation technique d'un module Java legacy de l'application NeoFlow. Vous recevez \
            des faits calculés par JavaParser (JSON) et le code numéroté.
            Produisez :
            1. Une JavaDoc pour chaque méthode publique du module cible : classe et signature recopiées exactement \
            depuis les faits ; contrat (entrées, sortie, exceptions), ordre des règles quand il compte, comportements \
            hérités conservés. Pas de paraphrase ligne à ligne.
            2. Des sections de README technique : Rôle, Points d'entrée, Règles et comportements hérités, \
            Dépendances cachées, Risques de modification.
            Règles : noms de code entre accents graves, uniquement des noms présents dans les faits ou le code ; \
            aucune intention présentée comme un comportement ; toute interprétation est suivie de « à vérifier par \
            un test ». Les noms et signatures cités seront vérifiés automatiquement.""";

    private final ModeleLangage modele;
    private final CodeSource code;

    public GenerateurDocumentation(ModeleLangage modele, CodeSource code) {
        this.modele = modele;
        this.code = code;
    }

    /** Documentation retenue et éléments rejetés (avec motif). */
    public record DocumentationVerifiee(String modele, List<JavadocProposee> javadocs, List<SectionReadme> sections,
                                        List<String> rejets) {}

    public DocumentationVerifiee generer(Faits faits) {
        String utilisateur = "Faits (JSON) :\n" + ExportJson.ecrire(faits) + "\n\nCode numéroté :\n"
                + code.numeroter(faits.fichiers().stream().map(Faits.FichierSource::chemin).toList());
        Documentation doc = modele.generer(new Requete(Requete.Tache.DOCUMENTER, SYSTEME, utilisateur, faits),
                Documentation.class);
        VerificateurDocumentation verificateur = new VerificateurDocumentation(faits, code);
        List<JavadocProposee> javadocs = new ArrayList<>();
        List<SectionReadme> sections = new ArrayList<>();
        List<String> rejets = new ArrayList<>();
        for (JavadocProposee javadoc : doc.javadocs() == null ? List.<JavadocProposee>of() : doc.javadocs()) {
            Optional<String> motif = verificateur.verifier(javadoc);
            if (motif.isPresent()) {
                rejets.add("JavaDoc " + javadoc.classe() + "." + javadoc.signature() + " : " + motif.get());
            } else {
                javadocs.add(javadoc);
            }
        }
        for (SectionReadme section : doc.sections() == null ? List.<SectionReadme>of() : doc.sections()) {
            Set<String> inconnus = verificateur.nomsInconnus(section.contenu());
            if (inconnus.isEmpty()) {
                sections.add(section);
            } else {
                rejets.add("Section « " + section.titre() + " » : nom(s) inconnu(s) " + String.join(", ", inconnus));
            }
        }
        return new DocumentationVerifiee(modele.nom(), javadocs, sections, rejets);
    }

    /** README technique : sections vérifiées + parties calculées + rejets à relire. */
    public static String readme(Faits faits, DocumentationVerifiee doc) {
        StringBuilder sb = new StringBuilder("# Module `").append(faits.paquetCible()).append("` — README technique (brouillon)\n\n");
        sb.append("> Généré par `labs/legacy-ia` (modèle `").append(doc.modele())
                .append("`). Parties calculées par JavaParser ; sections rédigées vérifiées (noms existants). ")
                .append("À relire : chaque règle doit citer le test de caractérisation qui la prouve.\n\n");
        doc.sections().forEach(s -> sb.append("## ").append(s.titre()).append("\n\n").append(s.contenu()).append("\n\n"));
        sb.append("## Points d'entrée (calculé)\n\n| Verbe | Chemin | Méthode |\n|---|---|---|\n");
        faits.pointsEntree().forEach(p -> sb.append("| ").append(p.verbe()).append(" | `").append(p.chemin())
                .append("` | `").append(p.methode()).append("` |\n"));
        sb.append("\n## Méthodes et complexité (calculé)\n\n| Méthode | Fichier:lignes | CCN |\n|---|---|---|\n");
        for (Methode m : faits.methodes()) {
            sb.append("| `").append(m.classe()).append('.').append(m.signature()).append("` | ")
                    .append(m.fichier().substring(m.fichier().lastIndexOf('/') + 1)).append(':').append(m.ligneDebut())
                    .append('-').append(m.ligneFin()).append(" | ").append(m.complexite()).append(" |\n");
        }
        sb.append("\n## Constats (calculé)\n\n| Type | Ligne | Extrait | Détail |\n|---|---|---|---|\n");
        faits.constats().forEach(c -> sb.append("| ").append(c.type()).append(" | ")
                .append(c.fichier().substring(c.fichier().lastIndexOf('/') + 1)).append(':').append(c.ligne())
                .append(" | `").append(c.extrait().replace("|", "\\|")).append("` | ").append(c.detail()).append(" |\n"));
        sb.append("\n## Graphe d'appels (calculé)\n\n```mermaid\n").append(ExportMermaid.grapheAppels(faits)).append("```\n");
        sb.append("\n## Éléments rejetés par la vérification\n\n");
        if (doc.rejets().isEmpty()) {
            sb.append("Aucun.\n");
        } else {
            doc.rejets().forEach(r -> sb.append("- ").append(r).append('\n'));
        }
        return sb.toString();
    }

    /** Propositions de JavaDoc, une par méthode, prêtes à relire puis à coller. */
    public static String javadocs(DocumentationVerifiee doc) {
        StringBuilder sb = new StringBuilder("# Propositions de JavaDoc (à relire avant application)\n\n");
        for (JavadocProposee j : doc.javadocs()) {
            sb.append("## `").append(j.classe()).append('.').append(j.signature()).append("`\n\n```java\n/**\n");
            j.javadoc().lines().forEach(l -> sb.append(" * ").append(l).append('\n'));
            sb.append(" */\n```\n\n");
        }
        return sb.toString();
    }
}
