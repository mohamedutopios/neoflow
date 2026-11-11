package com.neosoft.neoflow.demande;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface EvenementDemandeRepository extends JpaRepository<EvenementDemande, Long> {

    List<EvenementDemande> findByDemandeIdOrderByHorodatageAscIdAsc(Long demandeId);
}
