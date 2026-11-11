# Bibliothèque interne NeoUtils (frontend)

`NeoUtils` est la bibliothèque d'affichage reprise de l'ancien intranet (2015). Elle est importée par les
pages React de NeoFlow pour garder les mêmes formats que les autres applications internes.

Fichier : `frontend/src/legacy/utils-legacy.js` (module ES5 exporté par défaut).

```js
import NeoUtils from '../legacy/utils-legacy';

NeoUtils.formatMontant(1234.5);                    // "1 234,50 €"
NeoUtils.formatMontant(null);                      // "-"
NeoUtils.formatDate('2026-03-02T10:00:00');        // "02/03/2026"
NeoUtils.joursOuvres('2026-03-02', '2026-03-06');  // 5
```

## Fonctions

| Fonction | Entrée | Sortie |
|---|---|---|
| `formatMontant(m)` | nombre, `null` ou chaîne vide | montant à deux décimales, séparateur de milliers espace, virgule décimale, suffixe ` €` ; `-` si vide |
| `formatDate(d)` | date, chaîne ISO ou horodatage | `jj/mm/aaaa` dans le fuseau du navigateur ; chaîne vide si absent |
| `joursOuvres(debut, fin)` | deux dates, bornes incluses | nombre de jours du lundi au vendredi |

## Règles d'usage

- Ne pas dupliquer ces formats dans les composants : appeler `NeoUtils`.
- Toute évolution de format doit être validée avec l'équipe des applications internes, car d'autres
  écrans en dépendent.
- Une réécriture en TypeScript est prévue ; elle devra conserver les sorties ci-dessus.
