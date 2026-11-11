package com.neosoft.neoflow;

import java.time.Clock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@SpringBootApplication
@ConfigurationPropertiesScan
@EnableSpringDataWebSupport(pageSerializationMode = EnableSpringDataWebSupport.PageSerializationMode.VIA_DTO)
public class NeoflowApplication {

    public static void main(String[] args) {
        SpringApplication.run(NeoflowApplication.class, args);
    }

    /**
     * Horloge de l'application, injectable pour rendre les dates testables.
     */
    @Bean
    Clock horloge() {
        return Clock.systemDefaultZone();
    }
}
