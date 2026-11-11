package com.neosoft.neoflow.legacyia.ia;

import com.fasterxml.jackson.annotation.JsonPropertyDescription;

import java.util.List;

/**
 * Formats de sortie structurée demandés au modèle. Le schéma JSON est dérivé de ces records par le SDK
 * ({@code outputConfig(Classe.class)}) : le modèle ne peut pas répondre hors de ce format.
 */
public final class Reponses {

    private Reponses() {
    }

    /** Référence vérifiable à une ligne de code. */
    public record Citation(
            @JsonPropertyDescription("Chemin du fichier, tel qu'il apparaît dans les faits (ex. com/neosoft/neoflow/legacy/RegleValidationLegacy.java)")
            String fichier,
            @JsonPropertyDescription("Numéro de la ligne citée, tel qu'il apparaît dans le code numéroté")
            int ligne,
            @JsonPropertyDescription("Extrait copié à l'identique depuis cette ligne (au moins 4 caractères)")
            String extrait) {}

    /** Affirmation sur le comportement du code. */
    public record Affirmation(
            @JsonPropertyDescription("Affirmation courte, factuelle, en français")
            String texte,
            @JsonPropertyDescription("VERIFIE si l'affirmation se lit directement sur les lignes citées, HYPOTHESE sinon")
            String statut,
            @JsonPropertyDescription("Au moins une citation de ligne qui fonde l'affirmation")
            List<Citation> citations,
            @JsonPropertyDescription("Test de caractérisation qui confirmerait ou infirmerait l'affirmation : entrées et sortie attendue")
            String testPropose) {}

    /** Risque de modification. */
    public record Risque(
            String titre,
            @JsonPropertyDescription("Modification réaliste qui déclencherait le risque")
            String declencheur,
            @JsonPropertyDescription("FAIBLE, MOYENNE ou ELEVEE, avec la conséquence métier")
            String gravite,
            @JsonPropertyDescription("Test qui détecterait le changement de comportement")
            String testQuiLeDetecte,
            List<Citation> citations) {}

    /** Réponse de la tâche EXPLIQUER. */
    public record Explication(
            @JsonPropertyDescription("Rôle du module en trois phrases au plus")
            String resume,
            List<Affirmation> affirmations,
            @JsonPropertyDescription("Au moins trois risques de modification")
            List<Risque> risques) {}

    /** Réponse de la tâche IMPACT. */
    public record AnalyseImpact(
            String resume,
            @JsonPropertyDescription("Conséquences du changement, chacune citée")
            List<Affirmation> consequences,
            @JsonPropertyDescription("REFACTORING si aucune sortie observable ne change, CHANGEMENT_METIER sinon, INCERTAIN si les faits ne permettent pas de trancher")
            String nature,
            String recommandation) {}

    /** JavaDoc proposée pour une méthode existante. */
    public record JavadocProposee(
            @JsonPropertyDescription("Nom simple de la classe")
            String classe,
            @JsonPropertyDescription("Signature exacte, recopiée depuis les faits (ex. determinerNiveau(String type, Double montant, ...))")
            String signature,
            @JsonPropertyDescription("Texte de la JavaDoc sans les délimiteurs /** */ ; noms de code entre accents graves")
            String javadoc) {}

    /** Section rédigée du README technique. */
    public record SectionReadme(String titre,
                                @JsonPropertyDescription("Markdown ; noms de code entre accents graves")
                                String contenu) {}

    /** Réponse de la tâche DOCUMENTER. */
    public record Documentation(List<JavadocProposee> javadocs, List<SectionReadme> sections) {}

    /** Réponse de la tâche TRADUIRE. */
    public record TraductionTs(
            @JsonPropertyDescription("Contenu complet du fichier TypeScript")
            String codeTypeScript,
            @JsonPropertyDescription("Comportements hérités conservés et points à faire relire")
            List<String> remarques) {}
}
