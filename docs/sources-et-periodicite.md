# Périodicité des sources — relevé du 15 septembre 2026

Relevé fait à l'API GitHub (dépôts, commits par fichier, workflows, exécutions, releases) **et dans les
fichiers de workflow eux-mêmes**, à la fois pour savoir **quand** nos chiffres changent et pour savoir
**quand** regarder.

Ce relevé remplace celui du 14/09/2026. Trois choses ont changé depuis (elles sont signalées par ⚠️) :
le pipeline d'extraction de la source n'est **pas** planifié et il est **relu par une personne** ; une
exécution planifiée a été servie avec plus de cinq heures de retard ; et la prévision comparée a gagné
un candidat.

## 1. MieuxVoter/presidentielle2027 — la source des chiffres

| | |
|---|---|
| Créé le | 2025-10-18 |
| Licence | MIT · 491 Ko · 297 fichiers · non archivé |
| Dernier push | 2026-09-15 |
| Activité | ~100 commits sur 30 jours · **médiane 1 jour** entre deux commits |
| Sondages compilés | **233**, le plus récent **2026-09-10** (OpinionWay) |

**Aucun sondage nouveau depuis le 10/09.** Au 15/09, cela fait cinq jours, et la semaine du 14/09 n'a
encore rien produit. La compilation n'a pas bougé entre les deux relevés : même nombre d'enquêtes,
même enquête la plus récente. Vérification faite en comparant l'empreinte (institut + dates +
échantillon) des 233 entrées : **zéro sondage présent en amont et absent de notre cache**.

Huit automatisations actives :

| Automatisation | Déclencheur | Rôle |
|---|---|---|
| `Check for New Presidential Polls` | cron `0 9 * * *` (**09:00 UTC**, 11:00 Paris) | cherche les nouveaux sondages |
| `Weekly Release - Sondages` | cron `0 9 * * 0` (**dimanche** 09:00 UTC) | release hebdomadaire |
| `Validate polls and merge` | à chaque push | valide puis fusionne |
| `LLM mining` | **issues / commentaires / manuel — pas de cron** ⚠️ | dépouille une issue en PR brouillon |
| `Auto-merge on push` | à chaque push | fusion automatique |
| `is your code linted with black?` | à chaque push | formatage |
| `Copilot`, `Copilot cloud agent` | dynamiques | revue de PR |

⚠️ **Correction du relevé précédent, sur le point le plus important.** Le 14/09, la présence de commits
« feat(sondage mining) » laissait craindre une source qui capterait plus vite *et se tromperait plus
vite*. La lecture du fichier `llm-mining.yml` impose une lecture plus calme : **le pipeline n'a aucun
cron**, il s'enclenche sur l'ouverture d'une issue ou un commentaire, et son propre en-tête pose la
règle — *« Une personne doit toujours relire la PR avant de la rendre prête à fusionner. »* Une
extraction automatique ne devient donc jamais une donnée publiée sans relecture humaine. C'est une
garantie, et elle est écrite par la source elle-même.

⚠️ **Délai d'exécution observé.** Le 15/09, l'exécution planifiée de 09:00 UTC a été servie à
**14:16 UTC** (soit 16:16 Paris), et elle s'est terminée en `success` sans nouveau sondage. Le retard
est réel mais sans conséquence pour nous : **14:16 < 18:00**, notre régénération passe toujours après
le contrôle de la source. La marge est en revanche plus mince que ce que le cron laissait croire.

Dernières releases : `semaine-2026-09-06` (publiée le 13/09), `semaine-2026-08-30`, `semaine-2026-08-23`.
Prochaine attendue **dimanche 20/09** — le battement reste hebdomadaire.

## 2. whyalwaysrose/presidentielle-2027 — la prévision bayésienne citée

| | |
|---|---|
| Créé le | 2026-09-07 · MIT · 554 Ko · 75 fichiers |
| Dernier push | 2026-09-15 |
| Champ publié | **28 candidats** ⚠️ (Karim Bouamrane ajouté le 15/09) |
| `as_of` | **2026-09-10** — inchangé, parce que le terrain n'a pas bougé |
| `generated_at` | recalculé **chaque jour** |

Deux automatisations : `daily.yml` (« Daily forecast », cron `20 5 * * *` — **05:20 UTC**, 07:20 Paris)
et `pages.yml` (« Deploy site »).

Le choix de 05:20 UTC est expliqué dans leur propre fichier : *« Les instituts publient au fil de la
journée et les notices de la Commission des sondages suivent ; la source compilée se reconstruit à son
propre rythme. Tourner à 05:20 UTC récupère tout ce qui a été déposé la veille. »* Bonne raison, et
elle vaut pour nous aussi.

⚠️ **Piège technique qu'ils documentent et que nous n'avions pas noté** : un commit poussé par
`GITHUB_TOKEN` **ne déclenche aucun autre workflow** (protection anti-boucle de GitHub). C'est
pourquoi `daily.yml` déploie lui-même le résultat qu'il vient de produire, et pourquoi `pages.yml`
couvre tout le reste. À retenir pour nos propres automatisations.

Leur activité du 15/09 est du logiciel, pas de la donnée — et deux de leurs commits recoupent
directement nos propres mesures :

- *« Test the survey-weight exponent: **it does not matter** »* — ils testent la pondération par
  fraîcheur et concluent qu'elle ne change rien. **Notre rétro-test 2022 dit exactement la même chose**
  (3,83 pondéré contre 3,73 pour la dernière enquête seule). Même conclusion, deux méthodes.
- *« stop a narrowed field publishing silently »* — ils corrigent un cas où un champ de candidats
  restreint pouvait être publié sans que cela se voie. Chez nous, c'est le rôle des compteurs de
  périmètre affichés en haut de la page d'agrégation.

La prévision en cache porte le **même `generated_at` que la version amont** : notre comparaison est
donc, à la seconde près, sur la version du jour.

## 3. Ce que cette cadence nous dit de la nôtre

| | Source | Nous |
|---|---|---|
| Contrôle | quotidien, planifié 11:00 (Paris) — servi à 16:16 le 15/09 ⚠️ | cron quotidien **18:00** (après le contrôle source) |
| Données | 2 à 4 mises à jour/semaine | cache 12 h, réévalué chaque soir |
| Battement | hebdomadaire (dimanche) | mouvements sur 7 et 28 jours |
| Prévision comparée | quotidienne 07:20 | cache 6 h |

Trois conséquences :

1. **Nous passons après le contrôle quotidien de la source**, mais avec 1 h 44 de marge seulement le
   15/09 au lieu des 7 heures prévues. Un sondage validé aujourd'hui à 16:16 est publié le jour même
   à 18:00. Si GitHub sert un jour la planification après 18:00, la donnée du jour glisse au
   lendemain — sans erreur, mais avec un jour de retard.
2. **La prévision comparée est rafraîchie 11 h avant nous** (07:20 contre 18:00) : notre comparaison
   est toujours basée sur la version du jour, et son cache de 6 h ne fait rien perdre.
3. **Le rythme réel des sondages suit l'agenda politique, pas notre cron.** Par semaine de terrain :
   23 sondages la semaine du 24/08, 15 celle du 31/08, 8 celle du 07/09 — **aucun** les semaines du
   03/08 et du 10/08, et **aucun** pour l'instant la semaine du 14/09. Une page quotidienne sur une
   source qui s'arrête plusieurs semaines doit le dire : d'où la fenêtre de 90 jours et les compteurs
   de périmètre affichés en haut de la page d'agrégation.

## 4. Le point de licence, mis au jour par ce relevé

Pour rétro-tester à J−30, il faut des sondages 2022 couvrant janvier à avril. Cette compilation existe :
`nsppolls/nsppolls` — **aucune licence**, dernier push le 24 mai 2022, 4,3 Mo — et
`flavienganter/polls-2027-election` — **aucune licence**, actif, 482 Mo.

`whyalwaysrose` en a mis une copie dans son propre dépôt (2,5 Mo de données `nsppolls` plus ses rapports)
et atteint J−30 grâce à elle. C'est exactement ce que nous nous interdisons : notre rétro-test s'arrête à
**J−132** faute d'une compilation libre sur cette période. Un dépôt sous licence MIT ne peut pas licencier
des données tierces qui n'ont pas de licence ; c'est la limite connue de l'autre source, et la raison
documentée de la nôtre.

---

*Relevé reproductible : API GitHub (`/repos`, `/commits?path=`, `/actions/runs`, `/actions/workflows`,
`/releases`, `/contents/.github/workflows`) et lecture directe des fichiers de workflow, 15/09/2026.*
