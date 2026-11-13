# Format du rapport de revue (skill revue-pr)

```markdown
## Revue IA — <titre de la PR ou branche>

**Périmètre** : <n> commits, <n> fichiers (base `main`) · **Revue** : complète | partielle
**Recommandation** : Changements demandés | Approbation possible sous réserve de la décision humaine

### Synthèse
<3 phrases maximum : ce que fait la PR, principal risque, état des tests et des scans>

### Constats
| # | Sévérité | Fichier:ligne | Constat | Correction proposée |
|---|---|---|---|---|
| 1 | BLOQUANT | backend/.../X.java:42 | ... | ... |

### Scans CI
| Outil | Alertes | Avis de la revue |
|---|---|---|
| Semgrep | n | confirmé / faux positif (raison) |
| Gitleaks | n | ... |
| Trivy | n critiques | ... |

### Questions pour l'auteur
- ...

### Hors périmètre relu
- <fichiers non relus, si revue partielle>

> Rapport généré par l'agent reviewer (lecture seule). Il ne vaut pas approbation :
> la décision de fusion appartient au relecteur humain.
```
