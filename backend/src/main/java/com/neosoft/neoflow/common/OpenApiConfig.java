package com.neosoft.neoflow.common;

import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

/**
 * Documentation OpenAPI : /v3/api-docs et /swagger-ui.html (bouton « Authorize » en HTTP Basic).
 */
@Configuration
@OpenAPIDefinition(
        info = @Info(title = "NeoFlow API", version = "0.1.0",
                description = "Gestion des demandes internes : création, soumission, circuit de validation, clôture."),
        security = @SecurityRequirement(name = "basic"))
@SecurityScheme(name = "basic", type = SecuritySchemeType.HTTP, scheme = "basic")
public class OpenApiConfig {
}
