# Option Java — serveur MCP « tickets » en lecture seule (SDK MCP Java)

Même contrat que `labs/mcp/tickets_server.py` pour la lecture (`list_tickets`, `get_ticket`, ressource
`tickets://{ticket_id}`), écrit avec le SDK MCP Java officiel (`io.modelcontextprotocol.sdk:mcp:2.0.1`,
transport stdio). **Aucun outil d'écriture** : la version Java illustre la lecture seule par construction.

```bash
cd labs/mcp/java/tickets-server
./mvnw -q package                                   # compile, 4 tests JUnit, jar exécutable
cd ../../../..                                      # racine du dépôt NeoFlow
uv run --project labs/mcp python labs/mcp/mcp_cli.py autre tools \
  --cmd "java -jar labs/mcp/java/tickets-server/target/neoflow-mcp-tickets.jar"
uv run --project labs/mcp python labs/mcp/mcp_cli.py autre call get_ticket '{"ticket_id": "NEO-142"}' \
  --cmd "java -jar labs/mcp/java/tickets-server/target/neoflow-mcp-tickets.jar"
```

Brancher sur l'agent : dans `labs/mcp/configs/mcp_client.json`, passer `"actif": true` sur `tickets-java`.
Les outils apparaissent sous les noms `tickets_java_list_tickets` et `tickets_java_get_ticket`.
Test d'intégration Python : `labs/mcp/tests/test_java_tickets.py` (ignoré tant que le jar n'est pas construit).

## Points à remarquer

| Sujet | Python (FastMCP 4.1) | Java (SDK MCP 2.0.1) |
|---|---|---|
| Déclaration d'un outil | décorateur `@mcp.tool`, schéma déduit des annotations de type | `Tool.builder()...inputSchema(Map)`, schéma écrit à la main |
| Validation des arguments | Pydantic, erreur renvoyée en `isError` | `ToolInputValidator` du SDK (JSON Schema), erreur en `isError` |
| Journaux | `logging` / rich sur stderr | SLF4J (`slf4j-simple`) sur stderr ; **stdout réservé au protocole** |
| Annotations | `annotations={"readOnlyHint": True, ...}` | `ToolAnnotations.builder().readOnlyHint(true)...` |
| Ressource paramétrée | `@mcp.resource("tickets://{ticket_id}")` | `SyncResourceTemplateSpecification` |

Le journal du SDK affiche la négociation : `Client initialize request - Protocol: 2025-11-25,
Capabilities: ClientCapabilities[... roots=null ...]` — notre client Python n'annonce pas `roots`.

En Spring Boot (application NeoFlow), le starter Spring AI MCP Server expose des méthodes `@Tool` du contexte
Spring par le même protocole ; à évaluer si le serveur doit partager les services et la sécurité de l'application.
