package com.neosoft.neoflow.demande;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.neosoft.neoflow.demande.dto.DemandeResponse;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@RestController
@RequestMapping("/api/demandes")
@Tag(name = "Demandes")
public class DemandeRechercheController {

    private static final int MAX_RESULTATS = 50;

    @PersistenceContext
    private EntityManager entityManager;

    private final DemandeMapper mapper;

    public DemandeRechercheController(DemandeMapper mapper) {
        this.mapper = mapper;
    }

    @GetMapping("/recherche")
    @Operation(summary = "Recherche des demandes dont le titre contient le texte saisi")
    @SuppressWarnings("unchecked")
    public List<DemandeResponse> rechercher(@RequestParam String q) {
        List<Demande> demandes = entityManager
                .createNativeQuery("SELECT * FROM demande WHERE titre LIKE '%" + q + "%'", Demande.class)
                .setMaxResults(MAX_RESULTATS)
                .getResultList();
        return demandes.stream().map(mapper::versResponse).toList();
    }
}
