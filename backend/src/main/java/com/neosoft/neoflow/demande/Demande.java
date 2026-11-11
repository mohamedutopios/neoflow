package com.neosoft.neoflow.demande;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

import com.neosoft.neoflow.common.TransitionInvalideException;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "demande")
public class Demande {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private TypeDemande type;

    @Column(nullable = false, length = 120)
    private String titre;

    @Column(length = 4000)
    private String description;

    /** Login du demandeur. */
    @Column(nullable = false, length = 50)
    private String demandeur;

    /** Montant en euros, facultatif selon le type de demande. */
    @Column(precision = 12, scale = 2)
    private BigDecimal montant;

    @Column(name = "date_debut", nullable = false)
    private LocalDate dateDebut;

    @Column(name = "date_fin")
    private LocalDate dateFin;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private StatutDemande statut;

    /** Niveau du circuit de validation (1 à 3), calculé à la soumission. */
    @Column(name = "niveau_validation")
    private Integer niveauValidation;

    @Column(length = 40)
    private String departement;

    @Column(nullable = false)
    private boolean urgent;

    @Column(name = "date_creation", nullable = false)
    private LocalDateTime dateCreation;

    @Column(name = "date_maj", nullable = false)
    private LocalDateTime dateMaj;

    @Column(name = "motif_refus", length = 500)
    private String motifRefus;

    /**
     * Fait passer la demande dans le statut cible si la transition est autorisée.
     *
     * @throws TransitionInvalideException si la transition est interdite
     */
    public void changerStatut(StatutDemande cible) {
        if (statut == null || !statut.peutPasserA(cible)) {
            throw new TransitionInvalideException(id, statut, cible);
        }
        this.statut = cible;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public TypeDemande getType() {
        return type;
    }

    public void setType(TypeDemande type) {
        this.type = type;
    }

    public String getTitre() {
        return titre;
    }

    public void setTitre(String titre) {
        this.titre = titre;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public String getDemandeur() {
        return demandeur;
    }

    public void setDemandeur(String demandeur) {
        this.demandeur = demandeur;
    }

    public BigDecimal getMontant() {
        return montant;
    }

    public void setMontant(BigDecimal montant) {
        this.montant = montant;
    }

    public LocalDate getDateDebut() {
        return dateDebut;
    }

    public void setDateDebut(LocalDate dateDebut) {
        this.dateDebut = dateDebut;
    }

    public LocalDate getDateFin() {
        return dateFin;
    }

    public void setDateFin(LocalDate dateFin) {
        this.dateFin = dateFin;
    }

    public StatutDemande getStatut() {
        return statut;
    }

    public void setStatut(StatutDemande statut) {
        this.statut = statut;
    }

    public Integer getNiveauValidation() {
        return niveauValidation;
    }

    public void setNiveauValidation(Integer niveauValidation) {
        this.niveauValidation = niveauValidation;
    }

    public String getDepartement() {
        return departement;
    }

    public void setDepartement(String departement) {
        this.departement = departement;
    }

    public boolean isUrgent() {
        return urgent;
    }

    public void setUrgent(boolean urgent) {
        this.urgent = urgent;
    }

    public LocalDateTime getDateCreation() {
        return dateCreation;
    }

    public void setDateCreation(LocalDateTime dateCreation) {
        this.dateCreation = dateCreation;
    }

    public LocalDateTime getDateMaj() {
        return dateMaj;
    }

    public void setDateMaj(LocalDateTime dateMaj) {
        this.dateMaj = dateMaj;
    }

    public String getMotifRefus() {
        return motifRefus;
    }

    public void setMotifRefus(String motifRefus) {
        this.motifRefus = motifRefus;
    }
}
