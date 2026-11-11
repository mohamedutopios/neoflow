package com.neosoft.neoflow.legacyia.ia;

import com.neosoft.neoflow.legacyia.analyse.AnalyseurLegacy;
import com.neosoft.neoflow.legacyia.analyse.CodeSource;
import com.neosoft.neoflow.legacyia.analyse.ExportJson;
import com.neosoft.neoflow.legacyia.analyse.Faits;
import com.neosoft.neoflow.legacyia.analyse.Faits.Methode;
import com.neosoft.neoflow.legacyia.ia.Reponses.AnalyseImpact;
import com.neosoft.neoflow.legacyia.ia.Reponses.Citation;
import com.neosoft.neoflow.legacyia.ia.Reponses.Explication;
import com.neosoft.neoflow.legacyia.ia.Reponses.Risque;
import com.neosoft.neoflow.legacyia.ia.VerificateurCitations.AffirmationVerifiee;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/** Explication et analyse d'impact : faits déterministes en entrée, réponse structurée vérifiée en sortie. */
public final class Explicateur {

    static final String SYSTEME_EXPLIQUER = """
            Vous analysez un module Java legacy de l'application NeoFlow avant un refactoring qui ne doit changer \
            aucun comportement. Vous recevez des faits calculés par JavaParser (JSON) et le code numéroté.
            Règles :
            1. N'utilisez que les faits et le code fournis. N'inventez ni classe, ni méthode, ni ligne.
            2. Chaque affirmation et chaque risque citent au moins une ligne : chemin exact tel qu'il figure dans les \
            faits, numéro de ligne, extrait copié à l'identique depuis cette ligne.
            3. Statut VERIFIE uniquement pour ce qui se lit directement sur les lignes citées. Tout ce qui dépend des \
            valeurs réelles à l'exécution (données lues en base, fuseau, Locale, appelants) est une HYPOTHESE.
            4. Pour chaque affirmation, proposez le test de caractérisation qui la trancherait (entrées, sortie).
            5. Donnez au moins trois risques de modification : déclencheur réaliste, gravité métier, test qui détecte.
            Vos citations seront vérifiées automatiquement : une citation inexacte fait rejeter l'affirmation.""";

    static final String SYSTEME_IMPACT = """
            Vous évaluez l'impact d'un changement proposé dans un module Java legacy de l'application NeoFlow. \
            Vous recevez le changement, la partie déterministe de l'impact (appelants, endpoints, constats) et le \
            code numéroté.
            Règles :
            1. N'utilisez que ces éléments ; chaque conséquence cite au moins une ligne (chemin exact, numéro, \
            extrait copié à l'identique).
            2. nature = REFACTORING seulement si vous pouvez montrer qu'aucune sortie observable ne change pour les \
            entrées réelles ; CHANGEMENT_METIER si une sortie change ; INCERTAIN si les éléments ne suffisent pas.
            3. La recommandation précise le test à lancer avant le commit et la décision humaine éventuelle.
            Vos citations seront vérifiées automatiquement.""";

    private final ModeleLangage modele;
    private final VerificateurCitations verificateur;
    private final CodeSource code;

    public Explicateur(ModeleLangage modele, CodeSource code) {
        this.modele = modele;
        this.code = code;
        this.verificateur = new VerificateurCitations(code);
    }

    /** Résultat d'une explication, après vérification des citations. */
    public record RapportExplication(String modele, String resume, List<AffirmationVerifiee> affirmations,
                                     List<Risque> risquesRetenus, List<Risque> risquesRejetes) {
        public long nbRejetees() {
            return affirmations.stream().filter(a -> !a.retenue()).count();
        }
    }

    /** Résultat d'une analyse d'impact, après vérification. */
    public record RapportImpact(String modele, ImpactDeterministe deterministe, String nature, String resume,
                                List<AffirmationVerifiee> consequences, String recommandation) {}

    public RapportExplication expliquer(Faits faits) {
        String utilisateur = "Faits (JSON) :\n" + ExportJson.ecrire(faits) + "\n\nCode numéroté :\n"
                + code.numeroter(faits.fichiers().stream().map(Faits.FichierSource::chemin).toList());
        Explication explication = modele.generer(
                new Requete(Requete.Tache.EXPLIQUER, SYSTEME_EXPLIQUER, utilisateur, faits), Explication.class);
        List<Risque> retenus = new ArrayList<>();
        List<Risque> rejetes = new ArrayList<>();
        for (Risque risque : explication.risques() == null ? List.<Risque>of() : explication.risques()) {
            boolean valide = risque.citations() != null && !risque.citations().isEmpty()
                    && risque.citations().stream().allMatch(c -> verificateur.verifier(c).valide());
            (valide ? retenus : rejetes).add(risque);
        }
        return new RapportExplication(modele.nom(), explication.resume(), verificateur.filtrer(explication.affirmations()),
                retenus, rejetes);
    }

    /**
     * @param cible      {@code Fichier.java:ligne} (chemin complet ou nom de fichier)
     * @param changement changement proposé, en clair
     */
    public RapportImpact impact(Faits faits, String cible, String changement) {
        ImpactDeterministe deterministe = impactDeterministe(faits, cible, changement);
        String utilisateur = "Changement proposé : " + changement + "\nLigne visée : " + deterministe.cible()
                + "\n\nImpact déterministe (JSON) :\n" + ExportJson.ecrire(deterministe) + "\n\nCode numéroté :\n"
                + code.numeroter(faits.fichiers().stream().map(Faits.FichierSource::chemin).toList());
        AnalyseImpact analyse = modele.generer(
                new Requete(Requete.Tache.IMPACT, SYSTEME_IMPACT, utilisateur, deterministe), AnalyseImpact.class);
        return new RapportImpact(modele.nom(), deterministe, analyse.nature(), analyse.resume(),
                verificateur.filtrer(analyse.consequences()), analyse.recommandation());
    }

    /** Méthode qui contient la ligne, appelants transitifs, endpoints : sans modèle. */
    public ImpactDeterministe impactDeterministe(Faits faits, String cible, String changement) {
        int deuxPoints = cible.lastIndexOf(':');
        if (deuxPoints < 0) {
            throw new IllegalArgumentException("Cible attendue sous la forme Fichier.java:ligne, reçu : " + cible);
        }
        String fichier = code.resoudre(cible.substring(0, deuxPoints))
                .orElseThrow(() -> new IllegalArgumentException("Fichier inconnu : " + cible));
        int ligne = Integer.parseInt(cible.substring(deuxPoints + 1).strip());
        Methode methode = faits.methodes().stream()
                .filter(m -> m.fichier().equals(fichier) && m.ligneDebut() <= ligne && ligne <= m.ligneFin())
                .findFirst().orElseThrow(() -> new IllegalArgumentException("Aucune méthode ne contient " + cible));
        Set<String> appelants = AnalyseurLegacy.appelantsTransitifs(Set.of(methode.id()), faits.appels());
        Set<String> chaineIds = new java.util.HashSet<>(appelants);
        chaineIds.add(methode.id());
        List<Faits.Appel> chaine = faits.appels().stream()
                .filter(a -> chaineIds.contains(a.appele()) && appelants.contains(a.appelant())).toList();
        List<Faits.PointEntree> pointsEntree = faits.pointsEntree().stream()
                .filter(pe -> appelants.contains(pe.methode()) || pe.methode().equals(methode.id())).toList();
        Set<String> idsEndpoints = pointsEntree.stream().map(Faits.PointEntree::methode).collect(Collectors.toSet());
        return new ImpactDeterministe(fichier + ":" + ligne, changement, methode.id(), List.copyOf(appelants), chaine,
                pointsEntree, faits.methodes().stream().filter(m -> idsEndpoints.contains(m.id())).toList(),
                faits.constats().stream().filter(c -> c.fichier().equals(fichier) && c.ligne() == ligne).toList());
    }

    // ------------------------------------------------------------------ rapports Markdown

    public static String enMarkdown(RapportExplication r) {
        StringBuilder sb = new StringBuilder("# Explication du module legacy\n\n");
        sb.append("Modèle : `").append(r.modele()).append("`. Les affirmations retenues ont des citations exactes : ")
                .append("elles restent des **hypothèses** tant qu'un test de caractérisation ne les a pas tranchées.\n\n");
        sb.append("## Résumé\n\n").append(r.resume()).append("\n\n");
        sb.append("## Affirmations retenues (citations vérifiées)\n\n| Affirmation | Statut du modèle | Citations | Test à écrire |\n|---|---|---|---|\n");
        r.affirmations().stream().filter(AffirmationVerifiee::retenue).forEach(a -> sb.append("| ")
                .append(cellule(a.affirmation().texte())).append(" | ").append(a.affirmation().statut()).append(" | ")
                .append(citations(a.affirmation().citations())).append(" | ").append(cellule(a.affirmation().testPropose()))
                .append(" |\n"));
        sb.append("\n## Affirmations rejetées (citation invalide)\n\n");
        if (r.nbRejetees() == 0) {
            sb.append("Aucune.\n");
        } else {
            sb.append("| Affirmation | Motif du rejet |\n|---|---|\n");
            r.affirmations().stream().filter(a -> !a.retenue()).forEach(a -> sb.append("| ")
                    .append(cellule(a.affirmation().texte())).append(" | ").append(cellule(String.join(" ; ", a.motifs())))
                    .append(" |\n"));
        }
        sb.append("\n## Risques de modification\n\n| Risque | Déclencheur | Gravité | Test qui le détecte | Citations |\n|---|---|---|---|---|\n");
        r.risquesRetenus().forEach(x -> sb.append("| ").append(cellule(x.titre())).append(" | ").append(cellule(x.declencheur()))
                .append(" | ").append(cellule(x.gravite())).append(" | ").append(cellule(x.testQuiLeDetecte())).append(" | ")
                .append(citations(x.citations())).append(" |\n"));
        if (!r.risquesRejetes().isEmpty()) {
            sb.append("\nRisques rejetés (citation invalide) : ")
                    .append(r.risquesRejetes().stream().map(Risque::titre).collect(Collectors.joining(" ; "))).append('\n');
        }
        return sb.toString();
    }

    public static String enMarkdown(RapportImpact r) {
        StringBuilder sb = new StringBuilder("# Analyse d'impact\n\n");
        ImpactDeterministe d = r.deterministe();
        sb.append("Changement : ").append(d.changement()).append("  \nLigne : `").append(d.cible())
                .append("`  \nMéthode : `").append(d.methodeModifiee()).append("`\n\n## Partie déterministe (graphe d'appels)\n\n");
        sb.append("- Appelants transitifs : ").append(d.appelants().isEmpty() ? "aucun"
                : d.appelants().stream().map(a -> "`" + a + "`").collect(Collectors.joining(", "))).append('\n');
        sb.append("- Endpoints : ").append(d.pointsEntree().isEmpty() ? "aucun"
                : d.pointsEntree().stream().map(p -> "`" + p.verbe() + " " + p.chemin() + "`").collect(Collectors.joining(", "))).append('\n');
        sb.append("- Constats sur la ligne : ").append(d.constatsSurLaLigne().isEmpty() ? "aucun"
                : d.constatsSurLaLigne().stream().map(c -> c.type().name()).collect(Collectors.joining(", "))).append("\n\n");
        sb.append("## Analyse du modèle (`").append(r.modele()).append("`)\n\nNature : **").append(r.nature())
                .append("**\n\n").append(r.resume()).append("\n\n| Conséquence | Retenue | Citations ou motif |\n|---|---|---|\n");
        r.consequences().forEach(c -> sb.append("| ").append(cellule(c.affirmation().texte())).append(" | ")
                .append(c.retenue() ? "oui" : "**non**").append(" | ")
                .append(c.retenue() ? citations(c.affirmation().citations()) : cellule(String.join(" ; ", c.motifs())))
                .append(" |\n"));
        sb.append("\nRecommandation : ").append(r.recommandation()).append('\n');
        return sb.toString();
    }

    private static String citations(List<Citation> citations) {
        return citations == null ? "" : citations.stream()
                .map(c -> "`" + c.fichier().substring(c.fichier().lastIndexOf('/') + 1) + ":" + c.ligne() + "`")
                .collect(Collectors.joining(", "));
    }

    private static String cellule(String texte) {
        return texte == null ? "" : texte.replace("|", "\\|").replace("\n", " ");
    }
}
