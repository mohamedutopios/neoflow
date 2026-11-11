package com.neosoft.neoflow.regles;

import java.util.List;

import org.springframework.stereotype.Component;

import com.neosoft.neoflow.demande.Demande;
import com.neosoft.neoflow.demande.TypeDemande;

/**
 * Collecte toutes les règles {@link RegleMetierDemande} déclarées comme beans et les applique.
 */
@Component
public class RegleMetierRegistry {

    private final List<RegleMetierDemande> regles;

    public RegleMetierRegistry(List<RegleMetierDemande> regles) {
        this.regles = List.copyOf(regles);
    }

    /**
     * Applique les règles génériques puis celles du type de la demande.
     *
     * @return l'ensemble des erreurs, liste vide si la demande est conforme
     */
    public List<String> verifier(Demande d) {
        return reglesApplicables(d.getType()).stream()
                .flatMap(regle -> regle.verifier(d).stream())
                .toList();
    }

    /** Règles qui s'appliquent à un type : les génériques, puis celles du type. */
    public List<RegleMetierDemande> reglesApplicables(TypeDemande type) {
        return regles.stream()
                .filter(regle -> regle.type() == TypeDemande.GENERIQUE || regle.type() == type)
                .sorted((a, b) -> Boolean.compare(a.type() != TypeDemande.GENERIQUE, b.type() != TypeDemande.GENERIQUE))
                .toList();
    }
}
