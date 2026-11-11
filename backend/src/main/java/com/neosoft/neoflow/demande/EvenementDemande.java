package com.neosoft.neoflow.demande;

import java.time.LocalDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

/**
 * Entrée du journal d'audit d'une demande (création, soumission, validation, refus, clôture).
 */
@Entity
@Table(name = "evenement_demande")
public class EvenementDemande {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "demande_id", nullable = false)
    private Demande demande;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private TypeEvenement type;

    /** Login de l'utilisateur à l'origine de l'événement. */
    @Column(nullable = false, length = 50)
    private String auteur;

    @Column(nullable = false)
    private LocalDateTime horodatage;

    @Column(length = 500)
    private String commentaire;

    protected EvenementDemande() {
        // requis par JPA
    }

    public EvenementDemande(Demande demande, TypeEvenement type, String auteur, LocalDateTime horodatage,
            String commentaire) {
        this.demande = demande;
        this.type = type;
        this.auteur = auteur;
        this.horodatage = horodatage;
        this.commentaire = commentaire;
    }

    public Long getId() {
        return id;
    }

    public Demande getDemande() {
        return demande;
    }

    public TypeEvenement getType() {
        return type;
    }

    public String getAuteur() {
        return auteur;
    }

    public LocalDateTime getHorodatage() {
        return horodatage;
    }

    public String getCommentaire() {
        return commentaire;
    }
}
