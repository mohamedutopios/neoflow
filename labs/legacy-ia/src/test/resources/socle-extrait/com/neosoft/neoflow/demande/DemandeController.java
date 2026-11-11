package com.neosoft.neoflow.demande;

import java.net.URI;
import java.util.List;

import org.springframework.data.web.PagedModel;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.neosoft.neoflow.demande.dto.DemandeRequest;
import com.neosoft.neoflow.demande.dto.DemandeResponse;
import com.neosoft.neoflow.demande.dto.EvenementResponse;
import com.neosoft.neoflow.demande.dto.RefusRequest;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

@RestController
@RequestMapping("/api/demandes")
@Tag(name = "Demandes", description = "Création, circuit de validation et historique des demandes")
public class DemandeController {

    private final DemandeService service;

    public DemandeController(DemandeService service) {
        this.service = service;
    }

    @GetMapping
    @Operation(summary = "Liste paginée des demandes (page 0-based), filtres facultatifs statut et type")
    public PagedModel<DemandeResponse> lister(
            @RequestParam(required = false) StatutDemande statut,
            @RequestParam(required = false) TypeDemande type,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return new PagedModel<>(service.lister(statut, type, page, size));
    }

    @GetMapping("/{id}")
    @Operation(summary = "Détail d'une demande")
    public DemandeResponse obtenir(@PathVariable Long id) {
        return service.obtenir(id);
    }

    @PostMapping
    @Operation(summary = "Crée une demande au statut BROUILLON (rôle DEMANDEUR)")
    public ResponseEntity<DemandeResponse> creer(@Valid @RequestBody DemandeRequest requete, Authentication auth) {
        DemandeResponse creee = service.creer(requete, auth.getName());
        return ResponseEntity.created(URI.create("/api/demandes/" + creee.id())).body(creee);
    }

    @PutMapping("/{id}")
    @Operation(summary = "Modifie une demande au statut BROUILLON (rôle DEMANDEUR, auteur de la demande)")
    public DemandeResponse modifier(@PathVariable Long id, @Valid @RequestBody DemandeRequest requete,
            Authentication auth) {
        return service.modifier(id, requete, auth.getName());
    }

    @PostMapping("/{id}/soumettre")
    @Operation(summary = "Soumet la demande et calcule son niveau de validation (rôle DEMANDEUR)")
    public DemandeResponse soumettre(@PathVariable Long id, Authentication auth) {
        return service.soumettre(id, auth.getName());
    }

    @PostMapping("/{id}/valider")
    @Operation(summary = "Valide une demande soumise (rôle VALIDEUR)")
    public DemandeResponse valider(@PathVariable Long id, Authentication auth) {
        return service.valider(id, auth.getName());
    }

    @PostMapping("/{id}/refuser")
    @Operation(summary = "Refuse une demande soumise avec un motif (rôle VALIDEUR)")
    public DemandeResponse refuser(@PathVariable Long id, @Valid @RequestBody RefusRequest requete,
            Authentication auth) {
        return service.refuser(id, requete.motif(), auth.getName());
    }

    @PostMapping("/{id}/cloturer")
    @Operation(summary = "Clôture une demande validée (rôle ADMIN)")
    public DemandeResponse cloturer(@PathVariable Long id, Authentication auth) {
        return service.cloturer(id, auth.getName());
    }

    @GetMapping("/{id}/evenements")
    @Operation(summary = "Historique (journal d'audit) de la demande")
    public List<EvenementResponse> evenements(@PathVariable Long id) {
        return service.evenements(id);
    }
}
