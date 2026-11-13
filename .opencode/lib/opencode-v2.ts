// Types minimaux de l'API plugin d'OpenCode 2.x, limités à ce qu'utilise la toolbox NeoFlow.
// Relevés sur OpenCode 2.2.0 (paquet @opencode-ai/plugin, canal « next », forme promise) : un plugin est
// un objet exporté par défaut { id, setup(contexte) } ; les hooks s'enregistrent dans setup.
// Fichier de types uniquement (aucun code exécuté) : les plugins n'ont ainsi aucune dépendance npm.

export interface Inscription {
  readonly dispose: () => Promise<void>
}

/** Hook « execute.before » : lever une erreur annule l'appel, le message est renvoyé au modèle. */
export interface AvantOutil {
  readonly tool: string
  readonly sessionID: string
  readonly agent: string
  input: unknown
}

export interface Resultat {
  readonly output?: unknown
  readonly content?: string | ReadonlyArray<{ type: string; text?: string }>
  readonly metadata?: Record<string, unknown>
}

/** Hook « execute.after » : `result` peut être remplacé (ce que lit le modèle). */
export type ApresOutil = {
  readonly tool: string
  readonly sessionID: string
  readonly agent: string
  readonly input: unknown
} & ({ readonly status: "completed"; result: Resultat } | { readonly status: "error"; error: { message?: string } })

/** Hook shell « create.before » : chaque commande lancée par OpenCode (outil shell, injections !`…`). */
export interface AvantShell {
  command: string
  cwd: string
  timeout: number
  shell: string
  env: Record<string, string | undefined>
}

export interface Evenement {
  readonly type: string
  readonly data?: Record<string, unknown>
}

export interface Contexte {
  readonly app: { readonly name: string; readonly version: string }
  readonly tool: {
    hook(nom: "execute.before", rappel: (e: AvantOutil) => Promise<void> | void): Promise<Inscription>
    hook(nom: "execute.after", rappel: (e: ApresOutil) => Promise<void> | void): Promise<Inscription>
  }
  readonly shell: {
    hook(nom: "create.before", rappel: (e: AvantShell) => Promise<void> | void): Promise<Inscription>
  }
  readonly event: { subscribe(): AsyncIterable<Evenement> }
}

export interface PluginV2 {
  readonly id: string
  readonly setup: (contexte: Contexte) => Promise<void | (() => Promise<void> | void)>
}
