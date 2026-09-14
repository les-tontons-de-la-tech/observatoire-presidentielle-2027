# Présidentielle 2027 — observatoire des sondages

Trois pages statiques publiées sous **https://dileviathan.fr/observatoire** (et testées sur
`dileviathan.fr/observatoire` (public depuis le 14/09/2026 ; aussi servi sur
`dileviathan.fr/observatoire` ; une copie de relecture reste servie sur
`dev.dileviathan.fr/observatoire`, derrière mot de passe et en `noindex`).
Aucune n'est marquée `noindex` : elles sont destinées à l'indexation. Les deux premières sont
régénérées **chaque jour
à 08:20** par cron ; la troisième est le rétro-test 2022, recalculable à volonté.

| URL | Contenu | Fichier généré |
|---|---|---|
| `/observatoire` | **Landing** : promesse, mouvements 7 j, évolution 8 semaines, tendance toutes listes, comparaison bayésienne, validation, principes, méthode, données, limites | `site/index.html` |
| `/observatoire/sondages/` | **Agrégation** : tête de course, KPI, tableau par candidat, évolution hebdo, comparaison bayésienne, validation, méthode détaillée, limites | `site/sondages/index.html` |
| `/observatoire/backtest/` | **Rétro-test 2022** : la méthode rejouée sur la campagne 2022, erreur par échéance, détail candidat par candidat, sensibilité au réglage | `site/backtest/index.html` |

## Dépôt, licence et régénération

Code publié sous **licence MIT** (voir `LICENSE`), sources tierces citées à la fin de ce fichier.
Les données téléchargées (~900 Ko chez MieuxVoter) et les pages générées ne sont **pas** versionnées :
elles se rechargent. Pour tout reproduire :

```bash
python3 generate.py        # télécharge la source si le cache a plus de 12 h, agrège, écrit site/
python3 backtest2022.py    # rejoue la campagne 2022, écrit data/backtest2022.json + site/backtest/
python3 candidats.py       # page des candidats + section « qui sera sur le bulletin »
python3 digest.py          # le message du cron (aperçu)
```

Aucune dépendance : ni `pip install`, ni build. Les textes rédigés vivent dans
`content/observatoire.json` (journal des mises à jour inclus) ; les chiffres ne sont jamais saisis
à la main — voir `CHANGELOG.md` pour la règle.

**Pages publiées** : <https://dileviathan.fr/observatoire/>

## Sourcing : une source pour les chiffres, des couches séparées pour le reste

**Règle** : les intentions de vote viennent d'**une seule** compilation licite — mélanger deux jeux de
sondages reviendrait à compter deux fois les mêmes enquêtes. Les autres sources sont des **couches
séparées et étiquetées**, jamais additionnées.

| Source | Nature | Licence | Usage |
|---|---|---|---|
| [MieuxVoter/presidentielle2027](https://github.com/MieuxVoter/presidentielle2027) | compilation de sondages (CSV + JSON), 233 enquêtes | **MIT** | source unique des intentions 2027 |
| [whyalwaysrose/presidentielle-2027](https://github.com/whyalwaysrose/presidentielle-2027) | **prévision bayésienne** (80 000 simulations, même source de sondages) | MIT | section « Comparaison » : probabilités, intervalles, duels — jamais fusionnée avec nos chiffres |
| [Bkolenc/sondages_presidentielle2022_ebra](https://github.com/Bkolenc/sondages_presidentielle2022_ebra) | sondages de la campagne 2022 (264 hypothèses de 1er tour, notices liées à la Commission des sondages) | MIT | **rétro-test** de notre méthode |
| [Résultats officiels du 1er tour 2022 — ministère de l'Intérieur](https://www.archives-resultats-elections.interieur.gouv.fr/resultats/presidentielle-2022/FE.php) | 12 candidats, 35 132 947 suffrages exprimés (France entière) | source publique officielle | référence du rétro-test : 12/12 scores vérifiés le 14/09/2026, recoupés avec Wikipédia FR (CC BY-SA) |
| [nsppolls/nsppolls](https://github.com/nsppolls/nsppolls) | référence académique des sondages FR | **aucune licence** | **non utilisée** : accord écrit nécessaire |
| [Commission des sondages](https://www.commission-des-sondages.fr/notices/) | notices officielles de chaque sondage publié | source publique | contrôle d'exhaustivité (manuel) |
| data.gouv.fr | recherche « sondages politiques » | — | **aucun jeu de données trouvé** (API, 14/09/2026) |

> **Retiré le 14/09/2026** : le panneau « marchés de prédiction » (Polymarket) a été supprimé des deux
> pages sur décision de l'auteur. Le générateur qui le produisait est conservé dans
> `archive/generate_avec_polymarket.py` ; le cache `data/markets.json` a été supprimé.

## Ce que ce n'est pas

- **Pas un modèle de prévision** : aucune probabilité de victoire calculée, aucun report de voix,
  aucune participation, aucune dynamique de campagne.
- Les **effets de maison ne sont pas corrigés** (chaque institut garde sa tendance).
- Les sondages testant **d'autres listes de candidats** ne sont pas comptés dans le tableau principal.
- L'intervalle publié est celui de la **moyenne** (plancheré à ±1 point), **pas un intervalle de
  prévision** : le rétro-test 2022 le confirme (voir plus bas).

## Méthode

```
poids w = exp(−ln2 × âge_jours / 30) × √(échantillon / 1000)
moyenne = Σ(w·x) / Σw
IC 95 % = max( 1,96 × σ_pondéré / √n_eff , 1 point )        n_eff = (Σw)² / Σw²
```

- **Sélection du scénario** : fenêtre de **90 jours** (mesurée sur 2022 : couverture complète des
  échéances, erreur moyenne 3,11 pt contre 3,19 pt à 60 jours) ; **agrégation** : 180 jours du même
  scénario ; **publication** : au moins 3 sondages.
- **Correction des effets de maison** (`HOUSE_CORRECTION = True`) : l'écart moyen de chaque institut au
  consensus des autres est estimé par itérations, contracté vers zéro selon le nombre d'enquêtes, puis
  retranché avant agrégation. Gain mesuré : 0,04 pt à fenêtre égale — réel mais faible, parce que les
  plus grosses erreurs de 2022 étaient *partagées par tous les instituts* (Mélenchon −13,8).
- `weight_mode` rejoue la méthode à poids égaux ou avec la dernière enquête seule (rétro-test) ;
  `min_polls`, `scenario_window` et `house_correction` sont paramétrables.
- **Évolution hebdomadaire** : série **rétro-calculée** (J−56 → J−0), scénario verrouillé, coupe
  stricte à chaque point.
- **Tendance toutes listes** : moyenne par candidat sur tous les sondages de premier tour —
  indicateur de **direction** uniquement, niveaux non comparables au tableau principal.
- **Archive quotidienne** : `data/history.jsonl`, une ligne par jour.
- **Comparaison bayésienne** : sortie de `whyalwaysrose/presidentielle-2027` (MIT) affichée en regard
  (médiane 1<sup>er</sup> tour, 90 %, P(2<sup>e</sup> tour), P(victoire), duels).

## Rétro-test 2022 — ce qu'il dit (14/09/2026)

Sondages 2022 (MIT) rejoués avec notre méthode, comparés au résultat officiel du 10 avril 2022.
La compilation s'arrête au **29/11/2021 (J−132)** : nous mesurons donc l'erreur à notre horizon actuel
(≈ J−215 pour 2027), pas dans la dernière ligne droite.

| Échéance | J− | Notre méthode | Poids égaux | Dernière enquête | Top 2 |
|---|---|---|---|---|---|
| 2021-07-01 | 283 | 2,81 | 2,81 | 2,64 | Le Pen / Macron |
| 2021-08-01 | 252 | 2,82 | 2,81 | 2,92 | Le Pen / Macron |
| 2021-09-01 | 221 | *couvert depuis* | — | 2,11 | *couvert depuis la fenêtre 90 j* |
| 2021-10-01 | 191 | 2,84 | 2,79 | 2,98 | Macron / Le Pen |
| 2021-11-01 | 160 | 3,81 | 3,76 | 3,98 | Macron / Le Pen |
| 2021-11-29 | 132 | **3,82** | 3,79 | 3,73 | Macron / Le Pen |

**Deux réglages mesurés et adoptés** (grilles complètes sur `/observatoire/backtest/`) :

| Fenêtre de sélection | Erreur moyenne | Couverture |
|---|---|---|
| 30 jours | 3,49 | 4/6 |
| 60 jours | 3,19 | 5/6 (trou en septembre 2021) |
| **90 jours (adopté)** | **3,11** | **6/6** |
| 120 jours | 3,10 | 6/6 |

| Effets de maison (fenêtre 90 j) | Erreur moyenne |
|---|---|
| sans correction | 3,15 |
| **avec correction (adoptée)** | **3,11** |

**Enseignements retenus :**

1. **Les deux finalistes étaient identifiés dès octobre 2021**, dans le bon ordre.
2. **La pondération par fraîcheur n'apporte rien** : 3,82 avec notre calcul, 3,79 à poids égaux,
   **3,73 avec la dernière enquête seule**. La demi-vie ne change presque rien (3,77–3,84). La valeur
   ajoutée de la page est la lisibilité, le scénario explicite et l'intervalle publié — pas le calcul.
3. **Les biais sont structurels** : à J−132, Mélenchon sous-estimé de **−13,8 points**, Zemmour
   surestimé de **+8,3**, Pécresse de **+5,1**, Hidalgo de **+3,8**. Un agrégateur de sondages ne
   corrige pas ces biais.
4. **Le champ de candidats est le premier facteur d'erreur** : les non-candidats (Bertrand,
   Montebourg, Philippot…) pesaient jusqu'à ~18 points du tableau en 2021, 2,2 au dernier point.
5. **Fragilité corrigée** : au 01/09/2021, aucun scénario n'atteignait trois enquêtes avec une
   fenêtre de 60 jours. La fenêtre de 90 jours couvre désormais les six échéances testées. C'est le seul
   réglage qui ait réellement amélioré la méthode.

### Comparaison bayésienne — après réglage

Depuis le passage à 90 jours, les deux lectures se rejoignent : Le Pen 34,0 % (nous) contre 33,8 %
(eux), Philippe 18,6 % contre 16,1 %, Mélenchon 15,5 % contre 15,7 %, Retailleau 8,3 % contre 8,3 %,
aucun écart supérieur à 0,3 point en dessous du quatrième. Notre décalage venait de notre réglage, pas
de leur modèle. Nos intervalles restent 11 fois plus étroits (2,0 points contre 22,9) : c'est la
différence qui subsiste.

## Fichiers

| Fichier | Rôle |
|---|---|
| `generate.py` | collecte, agrégation, série hebdo, comparaison bayésienne, rendu des deux pages |
| `backtest2022.py` | rétro-test 2022 : données, métriques, page dédiée |
| `digest.py` | message quotidien du cron |
| `data/polls.json` (12 h), `data/forecast_bayes.json` (6 h) | caches des sources externes |
| `data/summary.json`, `data/movements.json`, `data/backtest2022.json` | résultats machine |
| `data/history.jsonl` | archive quotidienne |
| `site/index.html`, `site/sondages/index.html`, `site/backtest/index.html` | pages générées |
| `nginx/default.conf` | conf nginx du conteneur (`absolute_redirect off`) |
| `archive/generate_avec_polymarket.py` | version du générateur avec le panneau marchés (retiré) |

## Périodicité des sources

Quand nos chiffres bougent dépend de quand bougent les sources. Relevé daté, à l'API GitHub :
[`docs/sources-et-periodicite.md`](docs/sources-et-periodicite.md) — cadence des dépôts, crons des
automatisations, rythme d'arrivée des sondages, rétro-tests publiés en face, et le point de licence qui
explique notre horizon.

En bref, au 14/09/2026 : la source des sondages contrôle les nouvelles enquêtes **chaque jour à 11:00**
(Paris) et publie une release **le dimanche** ; la prévision bayésienne citée se recalcule **chaque jour à
07:20**. Nos pages sont régénérées le matin, avec un cache de 12 heures sur la source.

## Déploiement — comment ces pages sont servies

Le générateur écrit des fichiers statiques : aucune base de données, aucun serveur applicatif. Le
dossier `site/` est monté dans un conteneur nginx (`nginx:alpine`), lui-même placé derrière un
reverse proxy qui **conserve** le préfixe `/observatoire`.

```bash
# reproduire ce qui est publié, en local
python3 generate.py && python3 candidats.py && python3 backtest2022.py
docker run -d --name observatoire -p 127.0.0.1:8090:80 \
  -v "$PWD/site:/usr/share/nginx/html/observatoire:ro" \
  -v "$PWD/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine
# puis http://127.0.0.1:8090/observatoire/
```

Deux réglages nginx ne sont pas cosmétiques : `absolute_redirect off` (sans quoi une redirection de
dossier perd le préfixe `/observatoire` et renvoie un 404) et `Cache-Control: no-cache` (les pages
changent tous les jours ; un lecteur bloqué sur la veille croit à un bug).

**Automatisation** : un cron quotidien régénère les trois séries de pages, puis vérifie que la page
locale répond 200. Sortie vide = silence, code de retour ≠ 0 = alerte. Le même passage envoie un
message de synthèse : dernières valeurs, mouvements sur 7 et 28 jours, état de la source.

**Publication** : au-delà de la QA ci-dessous, la page se **suspend d'elle-même** la veille et le jour
d'un scrutin — l'article 11 de la loi du 19 juillet 1977 interdit alors toute publication, diffusion
ou commentaire de sondage, et un avis remplace le contenu. La suspension se teste en simulant une date
de scrutin, sans attendre 2027.

## Vérifications faites (14/09/2026)

- Routes : `/observatoire/`, `/observatoire/sondages/`, `/observatoire/candidats/`,
  `/observatoire/backtest/` → 200 ; `/observatoire/inexistant` → 404 ; l'ancien chemin `/simulation`
  → 301 permanent vers `/observatoire`.
- Pages publiques : `robots: index, follow`, aucun `X-Robots-Tag` en production, les quatre URL
  déclarées dans le sitemap du site.
- Thème clair et sombre : contrastes mesurés dans les deux thèmes, **aucun texte sous le seuil AA**
  sur les quatre pages.
- Lisibilité multi-format : débordement horizontal nul à 390, 768 et 1180 px.
- Texte : aucun chiffre saisi à la main, aucun jeton non remplacé dans le HTML servi.
- Copie de relecture : 401 (mot de passe) et `noindex, nofollow` — elle ne peut pas être indexée.

## Suite envisagée

- **étendre le rétro-test à la dernière ligne droite** (J−30, J−10) : nécessite une compilation 2022
  plus complète qu'une source sous licence ne fournit pas aujourd'hui ;
- correction des effets de maison (ce que fait la prévision bayésienne) ;
- moyenne glissante publiée jour par jour ; export CSV/JSON publics ;
- **Cadre légal** (traité le 14/09/2026, à relire avant chaque mise en ligne) :
  - **art. 2 de la loi n° 77-808 du 19 juillet 1977** : la première publication d'un sondage est
    accompagnée du nom de l'organisme, du commanditaire et de l'acheteur, du nombre de personnes
    interrogées, des dates d'interrogation et de la mention des marges d'erreur. Satisfait par le
    tableau « Sources, traçabilité et mentions légales » de la page Agrégation.
  - **art. 3** : les instituts déposent une notice auprès de la Commission des sondages (questions
    posées, méthode d'échantillonnage, taux de non-réponse), publiée sur son site. Nous ne la
    reproduisons pas et le disons explicitement.
  - **loi organique n° 2021-335 du 29 mars 2021** : pour la prochaine présidentielle, toute
    publication de sondage doit être accompagnée des marges d'erreur des résultats publiés.
  - **art. 11** : interdiction de publier, diffuser ou commenter un sondage électoral la veille et le
    jour du scrutin ; pour la présidentielle, à compter du samedi précédant le scrutin à 0 h jusqu'à la
    fermeture du dernier bureau de vote. **Mécanisme en place** : `SCRUTINS` (dates des tours, à
    renseigner dès leur fixation par décret) — `main()` remplace alors les pages par un avis de
    suspension et n'écrit aucun chiffre (testé).
  - **art. 12** : amende de 75 000 €, notamment pour usage impropre du mot « sondage » — d'où la
    règle de rédaction : la page parle de « moyenne de sondages », jamais de « notre sondage », et ne
    se présente jamais comme une simulation de vote.
  - **communiqué de la Commission des sondages du 14 septembre 2026** : à compter du 15/09/2026, les
    enquêtes d'opinion liées au débat présidentiel 2027 — hors intentions de vote — entrent dans le
    champ de la loi, les médias qui les publient devant en respecter les articles 2 et 3.

## Sources et licences

- **Sondages** : compilation [MieuxVoter/presidentielle2027](https://github.com/MieuxVoter/presidentielle2027),
  licence MIT. Les enquêtes appartiennent à leurs instituts et commanditaires ; ce dépôt ne les
  redistribue pas, il en recalcule des agrégats à partir de la compilation publique.
- **Résultats officiels de 2022** : ministère de l'Intérieur (données publiques), recoupés avec
  Wikipédia (CC BY-SA) pour contrôle — seuls les résultats officiels sont publiés.
- **Candidatures** : recensement de La Chaîne parlementaire, complété ligne par ligne par la source de
  première main citée dans `data/candidats2027.json`.
- **Liste officielle des candidats** : Conseil constitutionnel, publiée au *Journal officiel* — seul
  document qui fait foi.
- **Prévision bayésienne citée pour comparaison** : [whyalwaysrose/presidentielle-2027](https://github.com/whyalwaysrose/presidentielle-2027),
  licence MIT.

Le code de ce dépôt est sous licence MIT (`LICENSE`).
