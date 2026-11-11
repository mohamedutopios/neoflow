package com.neosoft.neoflow.legacyia.ia;

import com.neosoft.neoflow.legacyia.analyse.CodeSource;
import com.neosoft.neoflow.legacyia.analyse.Faits;
import com.neosoft.neoflow.legacyia.analyse.Faits.Constat;
import com.neosoft.neoflow.legacyia.analyse.Faits.Methode;
import com.neosoft.neoflow.legacyia.analyse.Faits.TypeConstat;
import com.neosoft.neoflow.legacyia.ia.Reponses.Affirmation;
import com.neosoft.neoflow.legacyia.ia.Reponses.AnalyseImpact;
import com.neosoft.neoflow.legacyia.ia.Reponses.Citation;
import com.neosoft.neoflow.legacyia.ia.Reponses.Documentation;
import com.neosoft.neoflow.legacyia.ia.Reponses.Explication;
import com.neosoft.neoflow.legacyia.ia.Reponses.JavadocProposee;
import com.neosoft.neoflow.legacyia.ia.Reponses.Risque;
import com.neosoft.neoflow.legacyia.ia.Reponses.SectionReadme;
import com.neosoft.neoflow.legacyia.ia.Reponses.TraductionTs;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Modèle simulé, déterministe, pour le mode {@code --offline} : tests, préparation et plan B.
 *
 * <p>Il construit ses réponses à partir des faits (jamais au hasard) et commet volontairement les erreurs
 * typiques d'un vrai modèle, pour que les vérifications aient quelque chose à rejeter :
 * <ul>
 *   <li>une citation de ligne inexistante et une citation dont l'extrait n'est pas sur la ligne (rejetées) ;</li>
 *   <li>une interprétation plausible mais fausse en production, avec des citations exactes (retenue par la
 *       vérification mécanique : seul un test de caractérisation peut la réfuter) ;</li>
 *   <li>une JavaDoc sur une signature inventée et un nom de méthode inventé (rejetés).</li>
 * </ul>
 */
public final class ModeleSimule implements ModeleLangage {

    private final CodeSource code;
    private final Journal journal;

    public ModeleSimule(CodeSource code, Journal journal) {
        this.code = code;
        this.journal = journal;
    }

    @Override
    public String nom() {
        return "simule";
    }

    @Override
    public <T> T generer(Requete requete, Class<T> typeReponse) {
        Object reponse = switch (requete.tache()) {
            case EXPLIQUER -> expliquer((Faits) requete.contexte());
            case IMPACT -> impact((ImpactDeterministe) requete.contexte());
            case DOCUMENTER -> documenter((Faits) requete.contexte());
            case TRADUIRE -> traduire((ContexteTraduction) requete.contexte());
        };
        if (journal != null) {
            journal.consigner(requete.tache().name(), nom(), 0, 0, 0, "simule");
        }
        return typeReponse.cast(reponse);
    }

    // ------------------------------------------------------------------ EXPLIQUER

    private Explication expliquer(Faits faits) {
        List<Affirmation> affirmations = new ArrayList<>();
        List<Risque> risques = new ArrayList<>();
        for (Constat c : faits.constats()) {
            Citation citation = new Citation(c.fichier(), c.ligne(), c.extrait());
            switch (c.type()) {
                case COMPARAISON_REFERENCE_STRING -> {
                    affirmations.add(new Affirmation("`" + c.extrait() + "` compare des références de chaînes, pas leur contenu.",
                            "VERIFIE", List.of(citation),
                            "Appeler " + c.methode() + " avec un littéral \"DSI\" puis avec new String(\"DSI\") : comparer les niveaux."));
                    // Interprétation plausible, citations exactes, mais fausse pour des valeurs lues en base
                    affirmations.add(new Affirmation("Pour MATERIEL_IT, un demandeur de la DSI obtient toujours le niveau 1.",
                            "VERIFIE", List.of(citation, citationLigne(c.fichier(), c.ligne() + 1)),
                            "MATERIEL_IT, 3000 €, département « DSI » : niveau attendu 1."));
                    risques.add(new Risque("Corriger `==` en `equals` change le niveau de demandes réelles",
                            "Revue de code ou inspection de l'IDE qui « corrige » la comparaison",
                            "ELEVEE : baisse du niveau de contrôle pour le matériel de la DSI",
                            "Golden master enregistré avec des départements lus comme en base", List.of(citation)));
                }
                case HORLOGE_CACHEE -> {
                    affirmations.add(new Affirmation("Le résultat dépend de l'horloge et du fuseau de la JVM.", "VERIFIE",
                            List.of(citation), "Même demande, horloge figée un mercredi puis un vendredi 15 h, fuseaux Paris et UTC."));
                    risques.add(new Risque("Tests non déterministes et comportement dépendant du serveur",
                            "Test sans horloge figée ; conteneur en UTC", "MOYENNE : règle appliquée à la mauvaise heure",
                            "Contrat avec horloges figées et test « même instant, deux fuseaux »", List.of(citation)));
                    // Ligne inexistante : le fichier est plus court
                    int horsFichier = code.lignes(code.resoudre(c.fichier()).orElse(c.fichier())).size() + 64;
                    affirmations.add(new Affirmation("La règle du vendredi est appliquée avant le plafonnement du niveau.",
                            "VERIFIE", List.of(new Citation(c.fichier(), horsFichier, "if (niveau > NIVEAU_MAX)")),
                            "NIVEAU_MAX = 1 un vendredi 15 h : niveau attendu 1."));
                }
                case ETAT_STATIQUE_MUTABLE -> affirmations.add(new Affirmation(
                        "`" + c.extrait() + "` est un état global modifiable par n'importe quel appelant.", "VERIFIE",
                        List.of(citation), "Modifier la valeur dans un test, vérifier l'effet sur un autre test, restaurer."));
                case DIVISION_ENTIERE -> {
                    affirmations.add(new Affirmation("Le montant remboursable est tronqué à l'euro.", "HYPOTHESE",
                            List.of(citation), "REPAS 30 € : 25,0 attendu par le legacy, 25,50 attendu par le métier."));
                    // Extrait inventé : il n'est pas sur la ligne citée
                    affirmations.add(new Affirmation("Le montant remboursable est arrondi au centime supérieur.", "VERIFIE",
                            List.of(new Citation(c.fichier(), c.ligne(), "setScale(2, RoundingMode.HALF_UP)")),
                            "REPAS 25,555 € : 25,56 attendu."));
                    risques.add(new Risque("Corriger l'arrondi pendant un refactoring",
                            "Migration double vers BigDecimal présentée comme technique",
                            "ELEVEE : montants versés modifiés sans accord du métier",
                            "Golden master du remboursement", List.of(citation)));
                }
                default -> { }
            }
        }
        String resume = "Le module " + faits.paquetCible() + " compte "
                + faits.methodes().stream().filter(Methode::cible).count() + " méthode(s) ; "
                + faits.pointsEntree().size() + " endpoint(s) l'atteignent par "
                + faits.methodes().stream().filter(m -> !m.cible()).count() + " appelant(s).";
        return new Explication(resume, affirmations, risques);
    }

    // ------------------------------------------------------------------ IMPACT

    private AnalyseImpact impact(ImpactDeterministe impact) {
        List<Affirmation> consequences = new ArrayList<>();
        for (int i = 0; i < impact.chaine().size(); i++) {
            Faits.Appel appel = impact.chaine().get(i);
            consequences.add(new Affirmation("`" + appel.appelant() + "` atteint la ligne modifiée.", "VERIFIE",
                    List.of(citationLigne(appel.fichier(), appel.ligne())),
                    "Rejouer le contrat et le golden master du module."));
        }
        for (Methode endpoint : impact.methodesPointsEntree()) {
            impact.pointsEntree().stream().filter(pe -> pe.methode().equals(endpoint.id())).findFirst().ifPresent(pe ->
                    consequences.add(new Affirmation("Le changement est observable par " + pe.verbe() + " " + pe.chemin() + ".",
                            "HYPOTHESE", List.of(citationLigne(endpoint.fichier(), endpoint.ligneDebut())),
                            "Test d'intégration de l'endpoint, montant au-dessus du seuil concerné.")));
        }
        boolean metier = impact.changement().toLowerCase().contains("equals");
        return new AnalyseImpact(
                "La méthode " + impact.methodeModifiee() + " a " + impact.appelants().size() + " appelant(s) transitif(s).",
                consequences, metier ? "CHANGEMENT_METIER" : "INCERTAIN",
                metier ? "Ne pas committer comme refactoring : mesurer l'écart avec le golden master, puis décision métier et ADR."
                        : "Rejouer le contrat et le golden master avant tout commit.");
    }

    // ------------------------------------------------------------------ DOCUMENTER

    private Documentation documenter(Faits faits) {
        List<JavadocProposee> javadocs = new ArrayList<>();
        for (Methode m : faits.methodes()) {
            if (m.cible() && m.publique()) {
                String constats = faits.constats().stream().filter(c -> m.nom().equals(c.methode()) && c.fichier().equals(m.fichier()))
                        .map(c -> c.type().name().toLowerCase().replace('_', ' ')).distinct()
                        .reduce((a, b) -> a + ", " + b).orElse("aucun");
                javadocs.add(new JavadocProposee(m.classe(), m.signature(),
                        "Comportement historique de `" + m.classe() + "." + m.nom() + "`, conservé à l'identique.\n"
                                + "Points d'attention relevés par l'analyse : " + constats + ".\n"
                                + "Complexité cyclomatique : " + m.complexite() + "."));
            }
        }
        Optional<Methode> premiere = faits.methodes().stream().filter(m -> m.cible() && m.publique()).findFirst();
        premiere.ifPresent(m -> {
            javadocs.add(new JavadocProposee(m.classe(), m.nom() + "(String type, double montant)",
                    "Surcharge simplifiée."));                                               // signature inventée
            javadocs.add(new JavadocProposee(m.classe(), m.signature(),
                    "Délègue le cas de la DSI à `" + m.classe() + ".calculerNiveauDsi()`.")); // nom inventé
        });
        List<SectionReadme> sections = new ArrayList<>();
        sections.add(new SectionReadme("Rôle", "Le module `" + faits.paquetCible().substring(faits.paquetCible().lastIndexOf('.') + 1)
                + "` est atteint par " + faits.pointsEntree().size() + " endpoint(s). Méthodes publiques : "
                + faits.methodes().stream().filter(m -> m.cible() && m.publique()).map(m -> "`" + m.nom() + "`")
                .reduce((a, b) -> a + ", " + b).orElse("aucune") + "."));
        sections.add(new SectionReadme("Dépendances cachées", faits.constats().stream()
                .filter(c -> c.type() == TypeConstat.HORLOGE_CACHEE || c.type() == TypeConstat.LOCALE_IMPLICITE
                        || c.type() == TypeConstat.ETAT_STATIQUE_MUTABLE)
                .map(c -> "- `" + c.extrait() + "` (ligne " + c.ligne() + ") : " + c.detail())
                .reduce((a, b) -> a + "\n" + b).orElse("Aucune.")));
        sections.add(new SectionReadme("Taux de TVA", "Le taux est fourni par `TauxTvaService`."));      // nom inventé
        return new Documentation(javadocs, sections);
    }

    // ------------------------------------------------------------------ TRADUIRE

    private TraductionTs traduire(ContexteTraduction contexte) {
        String codeTs;
        if (contexte.reponseSimulee() != null) {
            try {
                codeTs = Files.readString(contexte.reponseSimulee(), StandardCharsets.UTF_8);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        } else {
            String ressource = "/simule/utils-" + contexte.variante() + ".ts";
            try (InputStream in = ModeleSimule.class.getResourceAsStream(ressource)) {
                if (in == null) {
                    throw new IllegalArgumentException("Réponse simulée absente : " + ressource
                            + " (utilisez --reponse-simulee <fichier.ts>)");
                }
                codeTs = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }
        return new TraductionTs(codeTs, List.of("Réponse simulée (variante " + contexte.variante() + ")"));
    }

    private Citation citationLigne(String fichier, int ligne) {
        List<String> lignes = code.lignes(code.resoudre(fichier).orElse(fichier));
        String texte = ligne >= 1 && ligne <= lignes.size() ? lignes.get(ligne - 1).strip() : "";
        return new Citation(fichier, ligne, texte);
    }
}
