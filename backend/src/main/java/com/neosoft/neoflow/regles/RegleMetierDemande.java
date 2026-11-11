package com.neosoft.neoflow.regles;

import java.util.List;

import com.neosoft.neoflow.demande.Demande;
import com.neosoft.neoflow.demande.TypeDemande;

/**
 * Point d'extension des variantes : une règle métier attachée à un type de demande.
 * <p>
 * Toute implémentation déclarée comme bean Spring est collectée par {@link RegleMetierRegistry}.
 * Une règle dont {@link #type()} vaut {@link TypeDemande#GENERIQUE} s'applique à toutes les demandes ;
 * sinon elle ne s'applique qu'aux demandes de son type.
 * <p>
 * Le registre est appelé à la création et à la modification (demande au statut {@code BROUILLON}) et à la
 * soumission (demande déjà passée au statut {@code SOUMISE}, niveau de validation calculé, pas encore
 * enregistrée). Une règle peut donc distinguer ces deux moments avec {@code d.getStatut()}.
 */
public interface RegleMetierDemande {

    /** Type de demande concerné ({@code GENERIQUE} pour une règle commune). */
    TypeDemande type();

    /**
     * Vérifie la demande.
     *
     * @return les messages d'erreur, liste vide si la demande est conforme
     */
    List<String> verifier(Demande d);
}
