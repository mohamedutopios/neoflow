package com.neosoft.neoflow.legacyia.traduction;

import java.nio.file.Path;

/** Lance les tests de parité legacy / TypeScript et rend leur verdict. */
public interface ExecuteurParite {

    /** Résultat : vert si le code de retour vaut 0 ; sortie tronquée pour le rapport. */
    record Resultat(boolean vert, int codeRetour, String sortie) {}

    Resultat executer(Path dossierFrontend);
}
