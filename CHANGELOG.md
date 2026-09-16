# Journal des mises à jour — Observatoire des sondages · présidentielle 2027

Ce fichier et `content/observatoire.json` portent le même journal. Le JSON est la source affichée sur
le site (page d'accueil : les trois dernières ; page Agrégation, section « Citer un chiffre » : tout) ;
ce fichier est la version lisible dans le dépôt.

**Règle : aucun chiffre ne change sans une ligne ici.** Un chiffre qui bouge sans explication est un
chiffre qu'on ne peut plus citer.

---

## 16 septembre 2026

**Correction — Veille législative : la page dit maintenant pourquoi elle s'arrête au 21 juillet.**
La page affichait « période couverte : 20/11/2024 → 21/07/2026 » sans un mot d'explication. Un lecteur
de septembre pouvait y voir une veille en panne. Vérification faite le 16/09 : le fichier des scrutins
publié par l'Assemblée nationale a été réédité le matin même, et il est identique, octet pour octet, à
celui de la veille — la source n'a rien de plus récent à offrir. Le Parlement ne siège pas : la session
ordinaire 2025-2026 s'est achevée le 21 juillet 2026, le gouvernement a renoncé à convoquer une session
extraordinaire en septembre, et la session ordinaire 2026-2027 ouvre le 1er octobre 2026
(*Le Monde*, 3 septembre 2026). La page porte désormais un bandeau d'état qui affiche la date du dernier
scrutin publié, le nombre de jours écoulés et cette explication, avec sa source. Le bandeau se met à
jour tout seul, et disparaîtra quand les scrutins reprendront. Les commissions peuvent siéger hors
session, mais leurs travaux ne donnent pas lieu à des scrutins publics : la page le précise, pour que
l'absence de scrutin ne se confonde pas avec une absence de travail parlementaire.

**Correction — La veille législative ne se publiait plus depuis la migration du site vers le VPS B.**
La tâche hebdomadaire ne lançait que le générateur. Depuis que le site statique et son conteneur vivent
sur le VPS B, générer ne publie plus rien : la page se régénérait ici et n'atteignait le serveur que si
le cron quotidien passait derrière. La tâche exécute maintenant un script dédié
(`veille_legislative_hebdo.sh`) qui génère, publie vers le VPS B et vérifie l'URL publique — l'état de
la page se contrôle sur ce que voit le lecteur, plus sur un port local.

## 15 septembre 2026

**Sources — Relevé des sources : aucun nouveau sondage depuis le 10 septembre.**
Les deux sources ont été vérifiées le 15/09, dans leurs dépôts et dans leurs fichiers de workflow. La
compilation des sondages compte toujours 233 enquêtes, la plus récente datant du 10/09 (OpinionWay) :
cinq jours sans nouveau terrain, et la semaine du 14/09 n'a encore rien produit. L'automatisation
quotidienne de la source a bien tourné et n'a rien trouvé. Sa prévision bayésienne est recalculée
chaque jour, mais son terrain s'arrête au 10/09 : elle ne bouge donc pas. La page n'est pas figée par
une panne, elle l'est par le calendrier politique. Le relevé complet — déclencheurs, cadence, licence —
est dans `docs/sources-et-periodicite.md`.

**Nouveauté — Page « Veille législative » : ce que le Parlement vote.**
Une nouvelle page suit les textes de loi du périmètre technopolitique — numérique, intelligence
artificielle, données, surveillance, cybersécurité, médias — dans la législature en cours. Les scrutins
publics de l'Assemblée nationale sont regroupés par texte de loi, avec leur vote final et le détail de
chaque scrutin. 6 textes et 99 scrutins retenus, dont 92 tenus en 2026 ; les textes de la législature
précédente (loi SREN, majorité numérique) restent listés en référence.

**Chiffres — Vote par groupe politique sur chaque texte, chaque député compté.**
Chaque texte porte la ventilation du vote par groupe : position, voix pour, contre, abstentions,
non-votants et absents — la somme égale l'effectif du groupe, vérifié sur les 72 lignes publiées. La
barre de répartition est tracée sur l'effectif et non sur les seuls votants : sur le vote du 21 juillet
2026, le Rassemblement national compte 17 participants sur 122 membres et 105 absents, ce que la barre
rend visible. Noms et couleurs des groupes : référentiel officiel de l'Assemblée.

**Correction — Position des groupes recalculée : le champ de l'Assemblée contredit ses propres décomptes.**
Le champ « position majoritaire » publié par l'Assemblée donne le groupe Écologiste et Social « contre »
avec 19 voix pour, 7 contre et 7 abstentions, là où sa propre page affiche « Pour » ; le Rassemblement
national y est donné « contre » avec 2 contre pour 14 abstentions. La position affichée est donc
recalculée à partir des voix exprimées de chaque groupe, et le motif est écrit sur la page.

**Nouveauté — Compte à rebours du premier tour, thème clair/sombre.**
La page d'accueil affiche un chrono en temps réel jusqu'au 18 avril 2027 à 20 h (fermeture des
bureaux), la page Agrégation un rappel compact « J−n ». Dates du scrutin au format français
(jj/mm/aaaa) partout.

**Correction — Prévision bayésienne : cache conservé en cas d'indisponibilité de la source.**
La fonction de téléchargement (`_get_json`) avait disparu du générateur, ce qui affichait
« indisponible » en permanence. Rétablie, et si la source externe ne répond plus, la page garde les
dernières données avec leur date de mise à jour, au lieu de disparaître.

**Présentation — Textes élargis à la pleine largeur des cartes.**
Les phrases introductives de section (comparaison bayésienne, méthode, journal, rétro-test) ne sont
plus contraintes à 36 caractères par ligne : elles occupent la carte, les notes techniques et les
légendes restent étroites.

**Présentation — Schéma du workflow zoomable.**
Sur la page Workflow, un clic sur le schéma l'ouvre en plein écran : molette pour zoomer, glisser
pour se déplacer, Échap pour fermer.

**Données — Blocs politiques alignés sur la nomenclature officielle.**
Les candidats sont classés selon les nuances politiques du ministère de l'Intérieur (extrême gauche,
gauche, centre, droite, extrême droite). La France insoumise passe à l'extrême gauche, les écologistes
rejoignent la gauche, les souverainistes sont répartis entre extrême droite et divers.

**Nouveauté — Page « Workflow » : comment le site se fabrique.**
Un schéma d'architecture, ses légendes et les réglages du rétro-test, intégrés au design du site
(thème clair/sombre, navigation commune). La page est générée par `workflow.py` (versionné),
le schéma utilise la palette de couleurs du site et bascule avec le thème.

---

## 14 septembre 2026

**Chiffres — Fenêtre de sélection portée à 90 jours, effets de maison corrigés.**
Deux réglages mesurés sur la campagne 2022 et retenus parce qu'ils réduisent l'erreur : la fenêtre
passe de 60 à 90 jours (elle supprime l'échéance de septembre 2021 où la page ne publiait rien) et
chaque institut est corrigé de son écart moyen au consensus des autres. Erreur moyenne sur six
échéances : 3,19 → 3,11 point. À J−132 seule, elle reste de 3,8 points — le gain est réel mais faible,
et le dire fait partie du résultat.

**Chiffres — Dates du scrutin fixées et vérifiées.**
Premier tour le dimanche 18 avril 2027, second tour le dimanche 2 mai 2027 (Conseil des ministres du
1er juillet 2026). La page affiche l'échéance et se suspend automatiquement la veille et le jour du
vote, conformément à l'article 11 de la loi du 19 juillet 1977.

**Nouveauté — Page « Les candidats » et section « Qui sera sur le bulletin ? ».**
Trente-huit personnes recensées, chaque ligne portant sa source et sa date de vérification ; un retrait
reste affiché, barré. S'y ajoute une mesure, et non un modèle : la part des questionnaires publiés qui
testent réellement chaque nom. Résultat vérifiable — une seule paire de noms se partage un même siège
sans jamais se croiser, Marine Le Pen et Jordan Bardella, avec une bascule complète entre mars et
septembre 2026.

**Texte — Vocabulaire de source clarifié.**
Les colonnes qui attribuaient les chiffres à « notre agrégation » disent maintenant d'où vient la
matière : « MieuxVoter » pour la compilation des sondages, « Estimation MieuxVoter » et « Prévision
bayésienne » dans le rétro-test. La compilation est leur, la moyenne pondérée est calculée ici.

**Texte — Section « À lire avant de citer un chiffre ».**
Ce qui peut être cité, sous quelle forme, et ce qui serait faux. Une moyenne de sondages n'est pas un
sondage, et une probabilité de second tour n'est pas une intention de vote.

**Présentation — Thème clair et sombre, lecture sur téléphone et tablette.**
Les quatre pages adoptent le thème du site, avec mémorisation du choix. Contrastes vérifiés dans les
deux thèmes : aucun texte sous le seuil AA. Sur téléphone, l'en-tête tient sur une ligne, les tableaux
se transforment en fiches et la mesure de lecture passe de 88 à 70 signes par ligne.

---

## Comment écrire une entrée

1. **Un fait par entrée.** Titre au fait (« Fenêtre portée à 90 jours »), pas d'intention
   (« amélioration de la méthode »). Le texte dit ce qui change, de combien, et à quelle condition.
2. **Le chiffre avant l'adjectif.** « 3,19 → 3,11 point », pas « nettement meilleur ».
3. **Ce qui n'a pas marché se date aussi.** Un réglage écarté, une optimisation sans gain, une source
   écartée faute de licence : c'est une information, pas un aveu.
4. **Deux endroits, une seule rédaction.** Écrire l'entrée dans `content/observatoire.json`, puis la
   recopier ici. La page se régénère seule (`python3 generate.py`) ; ce fichier, non.
5. **Nature de l'entrée** : `chiffres`, `texte`, `présentation`, `nouveauté` — la pastille affichée sur
   le site en dérive.
