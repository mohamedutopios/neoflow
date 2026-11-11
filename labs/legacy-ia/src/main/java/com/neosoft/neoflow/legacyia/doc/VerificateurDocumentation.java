package com.neosoft.neoflow.legacyia.doc;

import com.neosoft.neoflow.legacyia.analyse.CodeSource;
import com.neosoft.neoflow.legacyia.analyse.Faits;
import com.neosoft.neoflow.legacyia.ia.Reponses.JavadocProposee;

import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Vérifie qu'une documentation générée ne parle que de code qui existe :
 * <ul>
 *   <li>chaque JavaDoc vise une signature réelle (classe et signature recopiées des faits) ;</li>
 *   <li>chaque nom écrit entre accents graves existe dans le code analysé ; une référence
 *       {@code Classe.membre} désigne un membre réel de cette classe.</li>
 * </ul>
 */
public final class VerificateurDocumentation {

    private static final Pattern CODE_EN_LIGNE = Pattern.compile("`([^`]+)`");
    private static final Pattern IDENTIFIANT = Pattern.compile("[A-Za-z_][A-Za-z0-9_]*");
    private static final Pattern REFERENCE_QUALIFIEE = Pattern.compile("([A-Z][A-Za-z0-9_]*)\\.([a-zA-Z_][A-Za-z0-9_]*)");
    /** Vocabulaire du langage toléré dans la documentation. */
    private static final Set<String> VOCABULAIRE = Set.of("String", "int", "long", "double", "boolean", "void",
            "null", "true", "false", "new", "return", "if", "else", "static", "final", "public", "private",
            "Double", "Integer", "Long", "Boolean", "Object", "List", "Map", "Optional", "BigDecimal", "Clock",
            "Calendar", "Locale", "ROOT", "Math", "round", "equals", "toUpperCase", "toLowerCase", "getInstance",
            "Instant", "ZonedDateTime", "LocalDate", "LocalDateTime", "ZoneId", "System", "NullPointerException");

    private final Faits faits;
    private final Set<String> identifiantsDuCode = new HashSet<>();

    public VerificateurDocumentation(Faits faits, CodeSource code) {
        this.faits = faits;
        for (List<String> lignes : code.fichiers().values()) {
            for (String ligne : lignes) {
                Matcher m = IDENTIFIANT.matcher(ligne);
                while (m.find()) {
                    identifiantsDuCode.add(m.group());
                }
            }
        }
    }

    /** Motif de rejet d'une JavaDoc, vide si elle est acceptable. */
    public Optional<String> verifier(JavadocProposee javadoc) {
        boolean existe = faits.methodes().stream().anyMatch(m -> m.classe().equals(javadoc.classe())
                && normaliser(m.signature()).equals(normaliser(javadoc.signature())));
        if (!existe) {
            return Optional.of("signature inexistante : " + javadoc.classe() + "." + javadoc.signature());
        }
        Set<String> inconnus = nomsInconnus(javadoc.javadoc());
        return inconnus.isEmpty() ? Optional.empty() : Optional.of("nom(s) inconnu(s) : " + String.join(", ", inconnus));
    }

    /**
     * Noms cités entre accents graves qui n'existent pas dans le code analysé, ou références
     * {@code Classe.membre} dont le membre n'appartient pas à la classe.
     */
    public Set<String> nomsInconnus(String texte) {
        Set<String> inconnus = new LinkedHashSet<>();
        // TODO TP5 : pour chaque fragment entre accents graves (CODE_EN_LIGNE) :
        //   - chaque référence Classe.membre (REFERENCE_QUALIFIEE) dont la classe est analysée
        //     (estClasseAnalysee) mais dont le membre n'existe pas (estMembre) est inconnue ;
        //   - chaque identifiant (IDENTIFIANT) absent de identifiantsDuCode et de VOCABULAIRE est inconnu.
        // Tests : GenerateurDocumentationTest (calculerNiveauDsi, TauxTvaService doivent être rejetés).
        return inconnus;
    }

    private boolean estClasseAnalysee(String classe) {
        return faits.methodes().stream().anyMatch(m -> m.classe().equals(classe));
    }

    private boolean estMembre(String classe, String membre) {
        return faits.methodes().stream().anyMatch(m -> m.classe().equals(classe) && m.nom().equals(membre))
                || faits.champs().stream().anyMatch(c -> c.classe().equals(classe) && c.nom().equals(membre));
    }

    static String normaliser(String signature) {
        return signature == null ? "" : signature.replaceAll("\\s+", " ").replace("( ", "(").replace(" )", ")").strip();
    }
}
