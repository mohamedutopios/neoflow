package com.neosoft.neoflow.mcp.tickets;

import io.modelcontextprotocol.json.McpJsonMapper;
import io.modelcontextprotocol.json.jackson3.JacksonMcpJsonMapper;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DepotTicketsTest {

    private static DepotTickets depot;

    @BeforeAll
    static void charger() throws Exception {
        McpJsonMapper json = new JacksonMcpJsonMapper(JsonMapper.builder().build());
        depot = new DepotTickets(json, Path.of("../../data/tickets.json"));   // labs/mcp/data
    }

    @Test
    void listeLesTicketsOuvertsSansDescription() {
        List<Map<String, Object>> ouverts = depot.lister("OUVERT", 50);
        assertEquals(5, ouverts.size());
        assertTrue(ouverts.stream().noneMatch(t -> t.containsKey("description")));
    }

    @Test
    void refuseUnIdentifiantInvalide() {
        assertThrows(IllegalArgumentException.class, () -> depot.lire("../etc/passwd"));
        assertThrows(IllegalArgumentException.class, () -> depot.lister("SUPPRIME", 10));
    }

    @Test
    void signaleLInjectionDuTicketNeo142() {
        Map<String, Object> ticket = depot.lire("NEO-142").orElseThrow();
        Map<String, Object> enveloppe = DepotTickets.envelopper("test", String.valueOf(ticket), Map.of("ticket", ticket));
        assertEquals("untrusted", enveloppe.get("trust"));
        @SuppressWarnings("unchecked")
        List<String> drapeaux = (List<String>) enveloppe.get("injection_flags");
        assertTrue(drapeaux.containsAll(List.of("commentaire_cache_pour_ia", "demande_de_secret", "dissimulation")),
            drapeaux.toString());
    }

    @Test
    void ticketSainSansDrapeau() {
        Map<String, Object> ticket = depot.lire("NEO-131").orElseThrow();
        Map<String, Object> enveloppe = DepotTickets.envelopper("test", String.valueOf(ticket), Map.of());
        assertEquals(List.of(), enveloppe.get("injection_flags"));
    }
}
