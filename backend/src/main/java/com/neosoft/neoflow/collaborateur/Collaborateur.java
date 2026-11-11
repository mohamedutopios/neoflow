package com.neosoft.neoflow.collaborateur;

import java.time.LocalDate;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Référentiel simplifié des collaborateurs (source de l'ancienneté et du département).
 */
@Entity
@Table(name = "collaborateur")
public class Collaborateur {

    @Id
    @Column(length = 50)
    private String login;

    @Column(nullable = false, length = 100)
    private String nom;

    @Column(nullable = false, length = 40)
    private String departement;

    @Column(name = "date_entree", nullable = false)
    private LocalDate dateEntree;

    protected Collaborateur() {
        // requis par JPA
    }

    public Collaborateur(String login, String nom, String departement, LocalDate dateEntree) {
        this.login = login;
        this.nom = nom;
        this.departement = departement;
        this.dateEntree = dateEntree;
    }

    public String getLogin() {
        return login;
    }

    public String getNom() {
        return nom;
    }

    public String getDepartement() {
        return departement;
    }

    public LocalDate getDateEntree() {
        return dateEntree;
    }
}
