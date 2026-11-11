package com.neosoft.neoflow.demande;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.jpa.domain.Specification;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

import jakarta.persistence.criteria.Predicate;

public interface DemandeRepository extends JpaRepository<Demande, Long>, JpaSpecificationExecutor<Demande> {

    /**
     * Filtre facultatif par statut et par type (un critère {@code null} est ignoré).
     */
    static Specification<Demande> avecFiltres(StatutDemande statut, TypeDemande type) {
        return (root, query, cb) -> {
            List<Predicate> criteres = new ArrayList<>();
            if (statut != null) {
                criteres.add(cb.equal(root.get("statut"), statut));
            }
            if (type != null) {
                criteres.add(cb.equal(root.get("type"), type));
            }
            return cb.and(criteres.toArray(Predicate[]::new));
        };
    }
}
