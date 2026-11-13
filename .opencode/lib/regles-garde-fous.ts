// Règles déterministes du plugin garde-fous (J02), pour OpenCode 2.x.
// Module pur : aucun effet de bord, testable hors d'OpenCode (voir .opencode/tests/).
// Ce fichier n'est PAS dans plugins/ : OpenCode charge comme plugin chaque fichier de plugins/.
// Outils OpenCode 2.x : read, edit, write, grep, glob, shell (ex-bash), subagent (ex-task), skill,
// question, execute (JavaScript « Code Mode » avec fetch), opencode_* (worktree, session, MCP).

export type Verdict =
  | { bloque: false }
  | { bloque: true; regle: string; message: string }

const OK: Verdict = { bloque: false }
const bloquer = (regle: string, message: string): Verdict => ({ bloque: true, regle, message })

/** Fichiers dont le contenu ne doit jamais entrer dans le contexte du modèle. */
const FICHIERS_SECRETS: Array<[RegExp, string]> = [
  [/(^|\/)\.env(\.(?!example$)[^/]+)?$/i, "fichier .env"],
  [/(^|\/)\.envrc$/i, "fichier .envrc"],
  [/(^|\/)(secrets?|credentials?)\//i, "dossier de secrets"],
  [/\.(pem|key|p12|pfx|jks|keystore|kdbx)$/i, "clé privée ou magasin de certificats"],
  [/(^|\/)id_(rsa|dsa|ecdsa|ed25519)$/i, "clé SSH privée"],
  [/(^|\/)\.(git-credentials|netrc|npmrc|pgpass)$/i, "fichier d'identifiants"],
  [/(^|\/)\.(aws|ssh|kube|gnupg|docker)\//i, "répertoire d'identifiants"],
  [/(^|\/)opencode\/auth\.json$/i, "identifiants OpenCode"],
]

/** Chemins (relatifs à la racine du dépôt) que l'agent ne modifie jamais : la chaîne qui le contrôle. */
const CHEMINS_PROTEGES: Array<[RegExp, string]> = [
  [/^opencode\.jsonc?$/, "configuration OpenCode (permissions)"],
  [/^\.opencode\/(plugins?|lib|tests)\//, "plugins garde-fous"],
  [/^\.github\/(workflows|actions)\//, "pipeline CI"],
  [/^\.github\/CODEOWNERS$/, "CODEOWNERS"],
  [/^(\.gitleaks\.toml|\.trivyignore(\.yaml)?|\.semgrepignore)$/, "configuration des scanners"],
  [/^\.semgrep\//, "règles Semgrep"],
  [/(^|\/)mvnw(\.cmd)?$|(^|\/)\.mvn\/wrapper\//, "wrapper Maven"],
  [/(^|\/)package-lock\.json$/, "lockfile npm (le modifier via npm install, jamais à la main)"],
]

const MIGRATION_FLYWAY = /^backend\/src\/main\/resources\/db\/migration\/V\d+__.+\.sql$/

/** Indique si un chemin désigne un fichier secret. */
export function estFichierSecret(chemin: string): string | undefined {
  const normalise = chemin.replaceAll("\\", "/")
  for (const [motif, libelle] of FICHIERS_SECRETS) if (motif.test(normalise)) return libelle
  return undefined
}

/** Lecture (read, grep, glob, list) d'un fichier secret. */
export function verifierLecture(chemin: string | undefined): Verdict {
  if (!chemin) return OK
  const libelle = estFichierSecret(chemin)
  if (!libelle) return OK
  return bloquer(
    "lecture-secret",
    `Lecture bloquée (${libelle}) par la politique NeoFlow. Les secrets ne doivent pas entrer dans le contexte. ` +
      `Pour connaître les variables attendues, lire .env.example.`,
  )
}

/** Motif de recherche (grep include, glob pattern) qui viserait des fichiers secrets : "*.env", "**\/.env*"... */
export function verifierMotifRecherche(motif: string | undefined): Verdict {
  if (!motif) return OK
  for (const partie of motif.replace(/[*?{}[\]]/g, "").split(",")) {
    const verdict = verifierLecture(partie.trim())
    if (verdict.bloque) return verdict
  }
  return OK
}

/** Écriture (edit, write, apply_patch). `relatif` est le chemin relatif à la racine du dépôt. */
export function verifierEcriture(relatif: string, existeDeja: boolean): Verdict {
  const chemin = relatif.replaceAll("\\", "/")
  const secret = estFichierSecret(chemin)
  if (secret) return bloquer("ecriture-secret", `Écriture bloquée (${secret}). Les secrets sont gérés hors agent.`)
  for (const [motif, libelle] of CHEMINS_PROTEGES) {
    if (motif.test(chemin))
      return bloquer(
        "fichier-protege",
        `Modification de ${chemin} bloquée (${libelle}). Ces fichiers évoluent par une PR humaine relue (CODEOWNERS).`,
      )
  }
  if (existeDeja && MIGRATION_FLYWAY.test(chemin))
    return bloquer(
      "migration-livree",
      `La migration ${chemin} est déjà livrée : Flyway refusera un checksum modifié. Créer une nouvelle migration V<n+1>__....sql.`,
    )
  return OK
}

/** Découpe une ligne de commande en sous-commandes (;, &&, ||, |, retour ligne, $( ), backticks). */
export function sousCommandes(commande: string): string[] {
  return commande
    .split(/\r?\n|;|&&|\|\||\||\$\(|`|\)/)
    .map((s) => s.trim())
    .filter(Boolean)
}

/** Jetons d'une sous-commande, sans les préfixes d'environnement (VAR=x) ni sudo/env/command. */
function jetons(sousCommande: string): string[] {
  const brut = sousCommande.match(/"[^"]*"|'[^']*'|[^\s<>]+/g) ?? []
  const nettoye = brut.map((j) => j.replace(/^["']|["']$/g, ""))
  while (nettoye.length && (/^[A-Za-z_][A-Za-z0-9_]*=/.test(nettoye[0]) || ["sudo", "command", "nohup", "time"].includes(nettoye[0])))
    nettoye.shift()
  return nettoye
}

function estRmRecursifForce(args: string[]): boolean {
  const options = args.filter((a) => a.startsWith("-"))
  const recursif = options.some((o) => o === "--recursive" || /^-[a-zA-Z]*[rR]/.test(o))
  const force = options.some((o) => o === "--force" || /^-[a-zA-Z]*f/.test(o))
  return recursif && force
}

const RE_UPLOAD = /\s(-d|--data(-binary|-raw|-urlencode|-ascii)?|-F|--form|-T|--upload-file|--post-file|--body-file)(=|\s|@)/
const RE_RESEAU = /^(curl|wget|http|https|xh|nc|ncat|netcat|socat|telnet|scp|sftp|rsync|ssh|ftp)$/

/** Commande shell (outil shell, ex-bash). Renvoie le premier motif bloquant trouvé. */
export function verifierCommande(commande: string): Verdict {
  const complete = commande.replace(/\s+/g, " ")

  if (/(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b/.test(complete))
    return bloquer("pipe-vers-shell", "Exécution d'un script téléchargé (curl | sh) interdite.")
  if (/\/dev\/(tcp|udp)\//.test(complete))
    return bloquer("socket-brut", "Connexion réseau brute (/dev/tcp) interdite.")
  if (/\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+(TABLE\s+)?\w)/i.test(complete))
    return bloquer("sql-destructif", "Instruction SQL destructive interdite depuis l'agent. Passer par une migration relue.")
  if (/:\(\)\s*\{\s*:\|:&\s*\};:/.test(complete) || /\bmkfs(\.\w+)?\b|\bdd\s+if=/.test(complete))
    return bloquer("systeme-destructif", "Commande système destructive interdite.")

  for (const sc of sousCommandes(commande)) {
    const [bin = "", ...args] = jetons(sc)
    const nom = bin.split("/").pop() ?? bin

    // 1. Secrets : tout jeton qui désigne un fichier secret (cat .env, cp .env, source .env, < .env...)
    // « @.env » (curl), « --data-binary=@.env », « file=.env » : on teste aussi la partie après @ ou =
    for (const j of [bin, ...args].flatMap((x) => [x, x.replace(/^.*[@=]/, "")])) {
      const libelle = estFichierSecret(j)
      if (libelle)
        return bloquer("shell-secret", `Accès shell à un ${libelle} bloqué (${j}). Lire .env.example si besoin.`)
    }
    // 2. Affichage de l'environnement (contient les clés API)
    if ((nom === "env" && args.every((a) => a.startsWith("-"))) || nom === "printenv" || nom === "export" && args.length === 0)
      return bloquer("affichage-environnement", "Affichage des variables d'environnement bloqué : il expose les clés API.")
    if (nom === "echo" && args.some((a) => /\$\{?[A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD|PASSWD)/.test(a)))
      return bloquer("affichage-secret", "Affichage d'une variable sensible bloqué.")
    // 3. Suppressions massives
    if (nom === "rm" && estRmRecursifForce(args))
      return bloquer("rm-recursif-force", "Suppression récursive forcée bloquée. Pour nettoyer le build : ./mvnw clean ou npm run clean.")
    if (nom === "find" && args.some((a) => a === "-delete" || a === "-exec" && args.includes("rm")))
      return bloquer("find-delete", "Suppression par find bloquée.")
    // 4. Git : perte de travail, réécriture d'historique, contournement des hooks
    if (nom === "git") {
      const sub = args.find((a) => !a.startsWith("-")) ?? ""
      if (sub === "push" && args.some((a) => /^(-f|--force|--force-with-lease|--mirror|--delete|-d)$/.test(a) || a.startsWith("+")))
        return bloquer("git-push-force", "Push forcé ou suppression de branche distante bloqué.")
      if (sub === "reset" && args.includes("--hard"))
        return bloquer("git-reset-hard", "git reset --hard bloqué : il détruit le travail non commité. Utiliser /undo ou git stash.")
      if (sub === "clean" && args.some((a) => /^-[a-zA-Z]*f/.test(a)))
        return bloquer("git-clean", "git clean -f bloqué : suppression de fichiers non suivis.")
      if (sub === "checkout" && args.includes("--") && args.includes("."))
        return bloquer("git-checkout-point", "git checkout -- . bloqué : il annule toutes les modifications locales.")
      if (args.includes("--no-verify") || args.includes("-n") && sub === "commit")
        return bloquer("git-no-verify", "Contournement des hooks Git (--no-verify) bloqué.")
      if (sub === "filter-branch" || sub === "filter-repo" || (sub === "branch" && args.includes("-D")))
        return bloquer("git-reecriture", "Réécriture d'historique ou suppression forcée de branche bloquée.")
    }
    // 5. Exfiltration : envoi de données vers le réseau
    if (RE_RESEAU.test(nom) && (RE_UPLOAD.test(` ${args.join(" ")} `) || ["scp", "sftp", "rsync", "nc", "ncat", "netcat", "socat"].includes(nom)))
      return bloquer("exfiltration", `Envoi de données vers le réseau bloqué (${nom}). Aucun appel sortant depuis l'agent.`)
    // 6. Permissions et conteneurs
    if (nom === "chmod" && args.some((a) => /^0?777$/.test(a)))
      return bloquer("chmod-777", "chmod 777 bloqué.")
    if (nom === "docker" && /\b(system prune|volume rm|compose down\b.*\s-v\b|rm -f)/.test(args.join(" ")))
      return bloquer("docker-destructif", "Suppression de conteneurs ou de volumes Docker bloquée.")
  }
  return OK
}

/** Domaines autorisés pour un accès web (fetch dans execute, webfetch selon version) ; refusé par défaut. */
export const DOMAINES_DOC = ["docs.spring.io", "react.dev", "developer.mozilla.org", "opencode.ai", "owasp.org", "semgrep.dev"]

export function verifierUrl(url: string | undefined): Verdict {
  if (!url) return OK
  let u: URL
  try {
    u = new URL(url)
  } catch {
    return bloquer("url-invalide", "URL invalide.")
  }
  const autorise = DOMAINES_DOC.some((d) => u.hostname === d || u.hostname.endsWith(`.${d}`))
  if (!autorise) return bloquer("domaine-non-autorise", `Domaine ${u.hostname} hors liste blanche documentation.`)
  if (u.search.length > 200 || /[A-Za-z0-9+/=_-]{60,}/.test(u.search))
    return bloquer("donnees-dans-url", "URL contenant un paramètre long : exfiltration possible, bloquée.")
  return OK
}

/** Accès réseau ou évasion dans le code de l'outil execute (Code Mode : fetch disponible, pas de fichiers). */
const RE_CODE_EVASION = /\b(globalThis|eval|Function|import|XMLHttpRequest|WebSocket|EventSource|navigator)\b/
const RE_URL = /https?:\/\/[^\s'"`)]+/g

/**
 * Code JavaScript envoyé à l'outil execute. Le projet refuse execute par permission ; cette règle est la
 * défense en profondeur si un agent le réactive : fetch seulement vers la liste blanche, URL littérale
 * obligatoire, pas d'accès indirect (globalThis["fe"+"tch"], eval…).
 */
export function verifierCode(code: string | undefined): Verdict {
  if (!code) return OK
  if (RE_CODE_EVASION.test(code))
    return bloquer("execute-evasion", "Code execute refusé : accès indirect (globalThis, eval, import…) interdit.")
  if (/\bfetch\b/.test(code)) {
    const urls = code.match(RE_URL) ?? []
    if (urls.length === 0)
      return bloquer("execute-reseau", "fetch sans URL littérale refusé : impossible de vérifier la destination.")
    for (const url of urls) {
      const verdict = verifierUrl(url)
      if (verdict.bloque) return { ...verdict, regle: `execute-${verdict.regle}` }
    }
  }
  return OK
}

/** Masque les valeurs ressemblant à des secrets avant journalisation. */
export function masquer(texte: string): string {
  return texte
    .replace(/(sk-ant-[A-Za-z0-9_-]{4})[A-Za-z0-9_-]+/g, "$1***")
    .replace(/((?:key|token|secret|password)\s*[=:]\s*)\S+/gi, "$1***")
    .slice(0, 300)
}

/** Variables d'environnement à vider pour les commandes lancées par l'agent. */
export function variablesSensibles(env: Record<string, string | undefined>): string[] {
  return Object.keys(env).filter((nom) =>
    /(^|_)(API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?)$/i.test(nom) || /^(AWS_|AZURE_CLIENT_|GOOGLE_APPLICATION_CREDENTIALS)/.test(nom),
  )
}

/** Chemin d'un appel d'outil fichier : `path` en OpenCode 2.x (`filePath` en 1.x, accepté par prudence). */
export function cheminArgument(args: Record<string, unknown>): string | undefined {
  const valeur = args.path ?? args.filePath
  return typeof valeur === "string" ? valeur : undefined
}

/** Chemins touchés par un appel d'outil d'édition (edit, write ; apply_patch : en-têtes du patch). */
export function cheminsEdites(outil: string, args: Record<string, unknown>): string[] {
  if (outil === "apply_patch" && typeof args.patchText === "string")
    return [...args.patchText.matchAll(/^\*\*\* (?:Add|Update|Delete) File: (.+)$/gm)].map((m) => m[1].trim())
  const chemin = cheminArgument(args)
  return chemin ? [chemin] : []
}
