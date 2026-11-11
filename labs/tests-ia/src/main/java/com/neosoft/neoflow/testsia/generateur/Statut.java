package com.neosoft.neoflow.testsia.generateur;

/** Verdict du vérificateur sur un test proposé. */
public enum Statut {
    /** Compile, passe, n'est pas tautologique : conservé (après relecture humaine). */
    ACCEPTE,
    /** Compile mais échoue sur le code actuel : défaut réel OU oracle faux. Décision humaine, jamais renvoyé au modèle. */
    ROUGE_A_ARBITRER,
    /** Ne vérifie rien (assertion absente ou constante, exception avalée, classe cible mockée, oracle recalculé...). */
    REJETE_TAUTOLOGIE,
    /** Ne compile pas. */
    REJETE_COMPILATION,
    /** Classe mal formée (package, nom, aucune méthode @Test). */
    REJETE_STRUCTURE
}
