# Périodicité des sources — relevé du 14 septembre 2026

Relevé fait à l'API GitHub (dépôts, commits par fichier, workflows, exécutions, releases), à la fois
pour savoir **quand** nos chiffres changent et pour savoir **quand** regarder.

## 1. MieuxVoter/presidentielle2027 — la source des chiffres

| | |
|---|---|
| Créé le | 2025-10-18 |
| Licence | MIT · 6 ⭐ · 491 Ko · 297 fichiers · non archivé |
| Dernier push | 2026-09-14 (le jour du relevé) |
| Activité | ~100 commits sur 30 jours · **médiane 1 jour** entre deux commits |

Trois automatisations comptent :

- **`Check for New Presidential Polls`** — cron `0 9 * * *`, donc **chaque jour à 09:00 UTC (11:00 à Paris)** :
  le dépôt cherche les nouveaux sondages publiés.
- **`Weekly Release - Sondages`** — cron `0 9 * * 0`, **le dimanche à 11:00 à Paris** : publication d'une
  release hebdomadaire (tags `semaine-2026-09-06`, publiées depuis le 30/08/2026).
- **`Validate polls and merge`** — à chaque push : validation puis fusion automatique.

Le fichier de données (`presidentielle2027.json`, 894 Ko) a été mis à jour 46 fois en trois semaines, par
grappes : trois fois le 12/09, puis les 11/09, 07/09 (×2), 06/09, 02/09, 31/08, 28/08. Autrement dit :
**un contrôle quotidien, deux à quatre mises à jour de données par semaine**, et un battement hebdomadaire
le dimanche.

Signal à surveiller : le dépôt développe un **pipeline d'extraction par LLM** (« feat(sondage mining) »,
« fix(mining): réponses tronquées ») pour lire les sondages dans la presse, avec fusion automatique après
validation. La source va donc capter plus vite — et se tromper parfois plus vite aussi. Nos garde-fous
(seuil de deux sondages pour publier un candidat, amplitude affichée à côté de la moyenne) sont ce qui nous
protège de ses erreurs d'extraction.

## 2. whyalwaysrose/presidentielle-2027 — la prévision bayésienne citée

| | |
|---|---|
| Créé le | 2026-09-07 (huit jours au moment du relevé) |
| Licence | MIT · 0 ⭐ · 554 Ko · 75 fichiers |
| Dernier push | 2026-09-13 |
| Activité | 11 commits, **médiane 1 jour** |

- **`Daily forecast`** — cron `20 5 * * *`, donc **chaque jour à 05:20 UTC (07:20 à Paris)**.
- **`Deploy site`** — à chaque push.

Le fichier publié (`site/data/forecast.json`) a été mis à jour **une fois par jour, sept jours d'affilée**
(07/09 → 13/09). La prévision est donc quotidienne — mais elle bouge peu : son `as_of` est le 2026-09-10,
c'est-à-dire la date du dernier terrain disponible. Une exécution quotidienne sur des sondages qui ne
bougent pas ne change pas le résultat ; nous affichons donc sa date `as_of` plutôt que sa date de calcul.

Deux de ses rétro-tests sont publiés : `as_of 2021-09-01` (**J−221**) et `as_of 2022-03-11` (**J−30**).

## 3. Ce que cette cadence nous dit de la nôtre

| | Source | Nous |
|---|---|---|
| Contrôle | quotidien 11:00 (Paris) | cron quotidien **08:20** |
| Données | 2 à 4 mises à jour/semaine | cache 12 h, réévalué chaque matin |
| Battement | hebdomadaire (dimanche) | mouvements sur 7 et 28 jours |
| Prévision comparée | quotidienne 07:20 | cache 6 h |

Trois conséquences :

1. **Nous passons 2 h 45 avant le contrôle quotidien de la source.** Un sondage validé aujourd'hui à 11:00
   n'entre chez nous que demain à 08:20 : jusqu'à 21 heures de retard sur la donnée du jour. Décaler notre
   passage vers 11:30 ramènerait ce retard à une demi-heure. Le rythme resterait quotidien : rien d'autre à
   changer.
2. **La prévision comparée est rafraîchie avant nous** (07:20 contre 08:20) : notre comparaison affiche bien
   la version du jour, et son cache de 6 h ne fait rien perdre.
3. **Le rythme réel des sondages suit l'agenda politique, pas notre cron.** Par semaine de terrain :
   23 sondages la semaine du 24/08, 15 celle du 31/08, 8 celle du 07/09 — et **aucun** les semaines du 03/08
   et du 10/08. Une page quotidienne sur une source qui s'arrête trois semaines en août doit le dire :
   d'où la fenêtre de 90 jours et les compteurs de périmètre affichés en haut de la page d'agrégation.

## 4. Le point de licence, mis au jour par ce relevé

Pour rétro-tester à J−30, il faut des sondages 2022 couvrant janvier à avril. Cette compilation existe :
`nsppolls/nsppolls` — **aucune licence**, dernier push le 24 mai 2022, 4,3 Mo — et
`flavienganter/polls-2027-election` — **aucune licence**, actif, 482 Mo.

`whyalwaysrose` en a mis une copie dans son propre dépôt (2,5 Mo de données `nsppolls` plus ses rapports)
et atteint J−30 grâce à elle. C'est exactement ce que nous nous interdisons : notre rétro-test s'arrête à
**J−132** faute d'une compilation libre sur cette période. Un dépôt sous licence MIT ne peut pas licencier
des données tierces qui n'ont pas de licence ; c'est la limite connue de l'autre source, et la raison
documentée de la nôtre.

Un autre de ses commits mérite d'être noté : *« reject weighting institutes by accuracy »* — il a testé puis
écarté la correction des instituts, quand nous avons mesuré que la nôtre ne rapportait que 0,04 point. Même
conclusion atteinte de deux côtés, par deux méthodes différentes.

---

*Relevé reproductible : API GitHub (`/repos`, `/commits?path=`, `/actions/workflows`, `/releases`),
14/09/2026.*
