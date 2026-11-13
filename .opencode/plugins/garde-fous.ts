// Plugin garde-fous NeoFlow (J02), format OpenCode 2.x : contrôles déterministes avant chaque appel d'outil.
// - bloque la lecture des secrets (.env, clés, identifiants), y compris via shell, grep, glob et MCP ;
// - bloque les commandes destructives, l'exfiltration réseau (shell, execute) et la modification de la
//   chaîne de contrôle ;
// - vide les variables sensibles de l'environnement des commandes lancées par OpenCode ;
// - journalise chaque blocage dans .opencode/journal/garde-fous.jsonl (fichier ignoré par Git).
// Lever une erreur dans le hook « execute.before » annule l'appel : le message est renvoyé au modèle.
// Règles pures et testées : ../lib/regles-garde-fous.ts. Aucune dépendance npm (types : ../lib/opencode-v2.ts).
import { appendFile, mkdir } from "node:fs/promises"
import { existsSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import type { PluginV2 } from "../lib/opencode-v2"
import {
  cheminArgument,
  cheminsEdites,
  masquer,
  variablesSensibles,
  verifierCode,
  verifierCommande,
  verifierEcriture,
  verifierLecture,
  verifierMotifRecherche,
  verifierUrl,
  type Verdict,
} from "../lib/regles-garde-fous"

// Outils intégrés d'OpenCode 2.x ; tout autre nom (serveur MCP, outils opencode_*) passe par le contrôle générique.
const OUTILS_INTEGRES = new Set(["read", "edit", "write", "apply_patch", "shell", "grep", "glob", "subagent", "skill", "question", "todowrite", "execute", "webfetch", "websearch"])

// Racine du dépôt : ce fichier est dans <racine>/.opencode/plugins/ (indépendant du dossier du service OpenCode).
const RACINE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..")
const JOURNAL = path.join(RACINE, ".opencode", "journal", "garde-fous.jsonl")

const relatif = (chemin: string) => {
  const absolu = path.isAbsolute(chemin) ? chemin : path.resolve(RACINE, chemin)
  return path.relative(RACINE, absolu).replaceAll("\\", "/")
}

const tracer = async (entree: Record<string, unknown>) => {
  try {
    await mkdir(path.dirname(JOURNAL), { recursive: true })
    await appendFile(JOURNAL, JSON.stringify({ horodatage: new Date().toISOString(), ...entree }) + "\n")
  } catch {
    // la journalisation ne doit jamais casser la session
  }
}

const appliquer = async (verdict: Verdict, outil: string, sessionID: string, args: unknown) => {
  if (!verdict.bloque) return
  await tracer({ sessionID, outil, regle: verdict.regle, args: masquer(JSON.stringify(args)) })
  throw new Error(`[garde-fous:${verdict.regle}] ${verdict.message}`)
}

const plugin: PluginV2 = {
  id: "neoflow.garde-fous",
  setup: async (contexte) => {
    await contexte.tool.hook("execute.before", async (e) => {
      const args = (e.input ?? {}) as Record<string, unknown>
      const { tool, sessionID } = e

      switch (tool) {
        case "read":
          return appliquer(verifierLecture(cheminArgument(args)), tool, sessionID, args)
        case "grep":
        case "glob": {
          if (typeof args.path === "string") await appliquer(verifierLecture(args.path), tool, sessionID, args)
          const motif = tool === "grep" ? args.include : args.pattern
          if (typeof motif === "string") await appliquer(verifierMotifRecherche(motif), tool, sessionID, args)
          return
        }
        case "edit":
        case "write":
        case "apply_patch": {
          for (const chemin of cheminsEdites(tool, args)) {
            const absolu = path.isAbsolute(chemin) ? chemin : path.resolve(RACINE, chemin)
            await appliquer(verifierEcriture(relatif(chemin), existsSync(absolu)), tool, sessionID, args)
          }
          return
        }
        case "shell":
          return appliquer(verifierCommande(String(args.command ?? "")), tool, sessionID, args)
        case "execute":
          return appliquer(verifierCode(String(args.code ?? "")), tool, sessionID, args)
        case "webfetch":
          return appliquer(verifierUrl(String(args.url ?? "")), tool, sessionID, args)
        default: {
          // Outils MCP et opencode_* : on refuse tout argument qui désigne un fichier secret.
          if (OUTILS_INTEGRES.has(tool)) return
          for (const valeur of Object.values(args)) {
            if (typeof valeur === "string") await appliquer(verifierLecture(valeur), tool, sessionID, args)
          }
        }
      }
    })

    // Les commandes lancées par OpenCode ne voient pas les clés : ANTHROPIC_API_KEY, GITHUB_TOKEN...
    await contexte.shell.hook("create.before", (e) => {
      for (const nom of new Set([...variablesSensibles(process.env), ...variablesSensibles(e.env)])) e.env[nom] = ""
    })

    // Journal des demandes de permission et des erreurs de session (lecture seule du flux d'événements).
    void (async () => {
      for await (const evenement of contexte.event.subscribe()) {
        if (evenement.type === "permission.asked" || evenement.type === "session.execution.failed")
          await tracer({ evenement: evenement.type, details: masquer(JSON.stringify(evenement.data ?? {})) })
      }
    })().catch(() => undefined)
  },
}

export default plugin
