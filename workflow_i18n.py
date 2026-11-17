"""Traduction anglaise de la page Workflow.

La page workflow est une pièce monolithique : un schéma SVG de 235 lignes et un
gabarit unique, où le français est soudé au balisage. Il n'y a pas de gabarit à
paramétrer, donc on ne peut pas suivre la méthode des autres pages (m(fr, en) à
chaque phrase). On traduit à la source quand même — mais au niveau du texte, pas
du document : les fragments ci-dessous sont remplacés dans les nœuds de texte
uniquement, jamais dans les balises ni dans les attributs, pour qu'une chaîne
française ne puisse pas se retrouver dans une URL, une classe ou un identifiant.

Règle de tenue : chaque fragment doit être une chaîne complète et reconnaissable.
Le contrôle `restes()` à la fin de la génération liste ce qui reste en français ;
tout ce qui n'est pas un nom propre doit être traduit, pas whitelisté.
"""

# Libellés du schéma et textes de la page. L'ordre n'importe pas : `traduire`
# applique les fragments du plus long au plus court pour qu'une phrase ne soit
# pas cassée par un fragment plus court qu'elle contient.

FRAGMENTS = [
    # ── schéma : bandeau et couches ──────────────────────────────────────────
    ("CYCLE QUOTIDIEN · 18:00 PARIS", "DAILY CYCLE · 18:00 PARIS"),
    ("génération ~10 s · cache 12 h", "build ~10 s · 12 h cache"),
    ("COUCHES EXTERNES", "EXTERNAL LAYERS"),
    ("DATA · CACHE", "DATA · CACHE"),
    ("GÉNÉRATEURS", "GENERATORS"),
    ("Source externe", "External source"),
    ("Cache / données", "Cache / data"),
    ("Générateur Python", "Python generator"),
    ("Page statique", "Static page"),
    ("Orchestration", "Orchestration"),
    ("Publication", "Publication"),
    ("Suspension légale — article 11", "Legal blackout — article 11"),

    # ── schéma : sources externes ────────────────────────────────────────────
    ("233 enquêtes · JSON", "233 polls · JSON"),
    ("contrôle quotidien à 11:00", "daily check at 11:00"),
    ("licence MIT · release le dimanche", "MIT licence · Sunday release"),
    ("prévision bayésienne · 80 000 tirages", "Bayesian forecast · 80,000 draws"),
    ("recalcul quotidien à 07:20", "daily recompute at 07:20"),
    ("licence MIT · même source de sondages", "MIT licence · same poll source"),
    ("Bkolenc · campagne 2022", "Bkolenc · 2022 campaign"),
    ("264 hypothèses de 1er tour", "264 first-round scenarios"),
    ("notices de la Commission des sondages", "poll commission notices"),
    ("licence MIT · résultat officiel vérifié", "MIT licence · official result verified"),
    ("Rédactionnel", "Editorial"),
    ("journal des mises à jour", "update log"),
    ("chaque ligne : source + date de vérification", "every line: source + check date"),

    # ── schéma : données ─────────────────────────────────────────────────────
    ("sondages 2027 · cache 12 h", "2027 polls · 12 h cache"),
    ("prévision · cache 6 h", "forecast · 6 h cache"),
    ("2022 · stable", "2022 · stable"),
    ("archive · une ligne par jour", "archive · one line per day"),

    # ── schéma : générateurs ─────────────────────────────────────────────────
    ("un seul scénario de candidatures retenu", "a single candidate scenario kept"),
    ("poids = demi-vie 30 j × √(n/1000)", "weight = 30 d half-life × √(n/1000)"),
    ("correction des effets de maison", "house-effect correction"),
    ("IC 95 % · série hebdo · page Agrégation", "95% CI · weekly series · Aggregation page"),
    ("38 personnes recensées", "38 people listed"),
    ("17 déclarés · 12 sous condition", "17 declared · 12 conditional"),
    ("« Qui sera sur le bulletin ? »", "“Who will be on the ballot?”"),
    ("une mesure, pas un modèle", "a measurement, not a model"),
    ("rejoue la campagne 2022", "replays the 2022 campaign"),
    ("erreur par échéance", "error by horizon"),
    ("grilles de sensibilité", "sensitivity grids"),
    ("hors cron : à la demande", "outside cron: on demand"),
    ("contenu éditorial", "editorial content"),

    # ── schéma : pages publiées ──────────────────────────────────────────────
    ("Accueil · mouvements 7 j", "Home · 7-day moves"),
    ("évolution 8 semaines · comparaison", "8-week trend · comparison"),
    ("méthode · limites", "method · limits"),
    ("Agrégation · tête de course", "Aggregation · the field"),
    ("KPI · tableau par candidat", "KPIs · table by candidate"),
    ("marges légales article 2", "legal information, article 2"),
    ("Rétro-test 2022", "2022 backtest"),
    ("erreur 3,11 pt · sensibilité", "error 3.11 pt · sensitivity"),
    ("la décision et ses motifs", "the choice and its grounds"),
    ("Les candidats", "Candidates"),
    ("familles · statuts · sources", "families · statuses · sources"),
    ("présence sur le bulletin", "ballot presence"),

    # ── schéma : orchestration ───────────────────────────────────────────────
    ("résultats machine", "machine results"),
    ("alimente le digest", "feeds the digest"),
    ("nginx:alpine — simulation-poc", "nginx:alpine — simulation-poc"),
    ("127.0.0.1:8090 · fichiers statiques", "127.0.0.1:8090 · static files"),
    ("monte site/ en lecture seule", "mounts site/ read-only"),
    ("Dépôt public GitHub", "Public GitHub repository"),
    ("observatoire-presidentielle-2027", "observatoire-presidentielle-2027"),
    ("licence MIT · données dérivées", "MIT licence · derived data"),
    ("et contenu éditorial seulement", "and editorial content only"),
    ("commit automatique du jour", "automatic daily commit"),
    ("Caddy — reverse proxy", "Caddy — reverse proxy"),
    ("handle /observatoire*", "handle /observatoire*"),
    ("préfixe conservé (pas de strip)", "prefix kept (no strip)"),
    ("/simulation* → 301 vers /observatoire", "/simulation* → 301 to /observatoire"),
    ("le reste → Next.js :3000", "the rest → Next.js :3000"),
    ("Cron · 0 18 * * *", "Cron · 0 18 * * *"),
    ("sans agent : la sortie est le message", "no agent: the output is the message"),
    ("code de retour ≠ 0 → alerte", "exit code ≠ 0 → alert"),
    ("régénère puis contrôle le HTTP 200", "rebuilds then checks HTTP 200"),
    ("lit movements.json", "reads movements.json"),
    ("mouvements sur 7 et 28 jours", "7- and 28-day moves"),
    ("état de la source", "source status"),
    ("dernières valeurs publiées", "latest published values"),
    ("Message Telegram", "Telegram message"),
    ("synthèse quotidienne", "daily summary"),
    ("jour normal : le digest", "normal day: the digest"),
    ("incident : l'alerte", "incident: the alert"),
    ("silence si tout va bien", "silence when all is well"),
    ("loi du 19 juillet 1977", "law of 19 July 1977"),
    ("veille et jour de chaque tour :", "eve and day of each round:"),
    ("avis de suspension, aucun chiffre", "blackout notice, no figures"),
    ("1er tour 18/04/2027 · 2d tour 02/05/2027", "round 1 18/04/2027 · round 2 02/05/2027"),

    ("PAGES STATIQUES", "STATIC PAGES"),

    # ── page : tête ──────────────────────────────────────────────────────────
    ("· workflow", "· workflow"),
    ("Annexe technique", "Technical annex"),
    ("Comment ce site se fabrique", "How this site is built"),

    # ── page : chapeau ───────────────────────────────────────────────────────
    ("Un observatoire de sondages ne vaut que si l'on peut vérifier d'où viennent ses chiffres et comment ils sont calculés. Cette page montre la chaîne complète, du dépôt public au HTML servi, avec les caches, les licences et les points de contrôle.",
     "A poll monitor is worth only as much as the reader's ability to check where its figures come from and how they are computed. This page shows the whole chain, from the public repository to the served HTML, with its caches, licences and checkpoints."),
    ("Le cycle, de la source à la page publiée", "The cycle, from source to published page"),
    ("Six étapes, une seule source de chiffres (MieuxVoter, licence MIT) et des couches complémentaires toujours étiquetées séparément. Une intention de vote n'est pas un vote ; une prévision n'est pas un résultat.",
     "Six steps, a single source of figures (MieuxVoter, MIT licence) and complementary layers always labelled apart. A voting intention is not a vote; a forecast is not a result."),
    ("↔ le schéma défile horizontalement · cliquez pour zoomer",
     "↔ the diagram scrolls horizontally · click to zoom"),
    ("Molette pour zoomer · glisser pour se déplacer · Échap pour fermer",
     "Wheel to zoom · drag to pan · Escape to close"),

    # ── page : méthode ───────────────────────────────────────────────────────
    ("La méthode, publiée", "The method, published"),
    ("Poids", "Weight"),
    (". Intervalle à 95 % sur la moyenne, plancheré à ±1 point — un intervalle de moyenne, pas de prévision. Scénario de candidatures unique, fenêtre de 90 jours, effets de maison corrigés.",
     ". A 95% interval on the mean, floored at ±1 point — an interval on a mean, not a forecast. A single candidate scenario, a 90-day window, house effects corrected."),
    ("Le rythme", "Cadence"),
    ("La source contrôle les nouvelles enquêtes chaque jour à 11:00 et recalcule sa prévision à 07:20. Nos pages se régénèrent le soir à 18:00 : un sondage publié dans la journée apparaît le lendemain.",
     "The source checks for new polls every day at 11:00 and recomputes its forecast at 07:20. Our pages rebuild in the evening at 18:00: a poll published during the day appears the next day."),
    ("Ce que la loi impose", "What the law requires"),
    ("Loi n° 77-808 du 19 juillet 1977 : institut, commanditaire, effectif, dates et marges pour chaque enquête agrégée (art. 2), aucune publication la veille et le jour de chaque tour (art. 11).",
     "Law no. 77-808 of 19 July 1977: pollster, client, sample size, dates and margins for every aggregated poll (art. 2); no publication on the eve and the day of each round (art. 11)."),

    # ── page : rétro-test ────────────────────────────────────────────────────
    ("Ce que le rétro-test 2022 a appris", "What the 2022 backtest taught us"),
    ("La méthode rejouée sur la campagne 2022, comparée au résultat officiel du ministère de l'Intérieur (12 scores sur 12 vérifiés). C'est ce qui a fixé la configuration retenue.",
     "The method replayed on the 2022 campaign, compared with the official result from the Interior Ministry (12 scores out of 12 verified). This is what settled the retained configuration."),
    ("Erreur moyenne", "Mean error"),
    ("3,11 point", "3.11 points"),
    ("avec la configuration retenue (fenêtre 90 jours, correction des effets de maison activée).",
     "with the retained configuration (90-day window, house-effect correction on)."),
    ("Les deux finalistes identifiés dès", "Both finalists identified from"),
    (", dans le bon ordre.", ", in the right order."),
    ("La pondération par fraîcheur", "Weighting by recency"),
    ("n'apporte rien", "adds nothing"),
    (": 3,83 contre 3,73 pour la dernière enquête seule. La valeur de cette page est la lisibilité, pas le calcul.",
     ": 3.83 against 3.73 for the latest poll alone. The value of this page is legibility, not computation."),
    ("Les biais sont", "The biases are"),
    ("structurels", "structural"),
    (": à J−132, Mélenchon sous-estimé de 13,8 points, Zemmour surestimé de 8,3. Un agrégateur de sondages ne corrige pas ces biais.",
     ": at D−132, Mélenchon understated by 13.8 points, Zemmour overstated by 8.3. A poll aggregator does not correct these biases."),
    ("Grilles complètes, réglage par réglage, sur la page", "Full grids, setting by setting, on the page"),

    # ── page : vérification et sources ───────────────────────────────────────
    ("Vérifier par soi-même", "Check for yourself"),
    ("Le code est publié sous licence MIT, les données dérivées et le contenu éditorial sont versionnés au jour le jour :",
     "The code is published under the MIT licence; derived data and editorial content are versioned day by day:"),
    ("dépôt observatoire-presidentielle-2027", "repository observatoire-presidentielle-2027"),
    (". Les caches téléchargés (~900 Ko chez MieuxVoter) ne sont pas recopiés : ils se rechargent, et la source est citée.",
     ". Downloaded caches (~900 KB from MieuxVoter) are not copied over: they reload, and the source is credited."),
    ("Page régénérée par", "Page rebuilt by"),
    (". Journal des changements de chiffres et de textes :", ". Log of changes to figures and text:"),
    ("du dépôt.", "in the repository."),
    ("Mentions légales", "Legal notice"),

    # ── page : navigation et liens de bas de page ────────────────────────────
    ("Présidentielle 2027", "2027 presidential election"),
    ("Accueil", "Home"),
    ("Agrégation", "Aggregation"),
    ("Veille législative", "Legislative watch"),
]

# Phrases du gabarit, reproduites ici au caractère près, espaces normalisés. Elles
# sont coupées sur plusieurs lignes dans workflow.py : la correspondance en texte
# normalisé les remplace en bloc, ce qu'un simple fragment ne pourrait pas faire.
EXACTES = [
    ("Un observatoire de sondages ne vaut que si l'on peut vérifier d'où viennent ses chiffres et comment ils sont calculés. Cette page montre la chaîne complète : une seule source pour les intentions de vote, des couches séparées pour le reste, aucun chiffre saisi à la main, et une page qui se suspend d'elle-même pendant la période légale.",
     "A poll monitor is worth only as much as the reader's ability to check where its figures come from and how they are computed. This page shows the whole chain: a single source for voting intentions, separate layers for everything else, no figure typed in by hand, and a page that suspends itself during the legal blackout period."),
    ("Six étapes, une seule source de chiffres (MieuxVoter, licence MIT) et des couches complémentaires toujours étiquetées séparément. Une intention de vote ne se moyenne jamais avec une probabilité de marché ou de modèle.",
     "Six steps, a single source of figures (MieuxVoter, MIT licence) and complementary layers always labelled apart. A voting intention is never averaged with a market or model probability."),
    ("w = exp(−ln2 × âge_jours / 30) × √(échantillon / 1000)",
     "w = exp(−ln2 × age_days / 30) × √(sample / 1000)"),
    (". Intervalle à 95 % sur la moyenne, plancheré à ±1 point — un intervalle de moyenne, pas de prévision. Scénario de candidatures unique, fenêtre de 90 jours, agrégation sur 180 jours, minimum trois sondages pour publier.",
     ". A 95% interval on the mean, floored at ±1 point — an interval on a mean, not a forecast. A single candidate scenario, a 90-day window, aggregation over 180 days, at least three polls before publishing."),
    ("La source contrôle les nouvelles enquêtes chaque jour à 11:00 et recalcule sa prévision à 07:20. Nos pages se régénèrent le soir à 18:00 : un sondage validé le matin est publié le jour même. Un cron horodate, contrôle le HTTP 200 et envoie une synthèse.",
     "The source checks for new polls every day at 11:00 and recomputes its forecast at 07:20. Our pages rebuild in the evening at 18:00: a poll validated in the morning is published the same day. A cron job timestamps the run, checks HTTP 200 and sends a summary."),
    ("Loi n° 77-808 du 19 juillet 1977 : institut, commanditaire, effectif, dates et marges pour chaque enquête agrégée (art. 2), aucune publication la veille et le jour d'un scrutin (art. 11). Jamais « notre sondage » — une moyenne de sondages n'est pas un sondage.",
     "Law no. 77-808 of 19 July 1977: pollster, client, sample size, dates and margins for every aggregated poll (art. 2); no publication on the eve or the day of a vote (art. 11). Never \u201cour poll\u201d — an average of polls is not a poll."),
    ("La méthode rejouée sur la campagne 2022, comparée au résultat officiel du ministère de l'Intérieur (12 scores sur 12 vérifiés). C'est ce qui a fixé les deux réglages ci-dessus, et c'est aussi ce qui borne la confiance à leur accorder.",
     "The method replayed on the 2022 campaign, compared with the official result from the Interior Ministry (12 scores out of 12 verified). This is what settled the two settings above, and it also bounds the confidence to place in them."),
    ("avec la configuration retenue (fenêtre 90 jours, house-effect correction activée).",
     "with the retained configuration (90-day window, house-effect correction on)."),
    (": 3,83 contre 3,73 pour la dernière enquête seule. La valeur de cette page est la lisibilité, pas le calcul.",
     ": 3.83 against 3.73 for the latest poll alone. The value of this page is legibility, not computation."),
    (": à J−132, Mélenchon sous-estimé de 13,8 points, Zemmour surestimé de 8,3. Un agrégateur de sondages ne corrige pas ces biais.",
     ": at D−132, Mélenchon understated by 13.8 points, Zemmour overstated by 8.3. A poll aggregator does not correct these biases."),
    ("Le code est publié sous licence MIT, les données dérivées et le contenu éditorial sont versionnés au jour le jour :",
     "The code is published under the MIT licence; derived data and editorial content are versioned day by day:"),
    ("dépôt observatoire-presidentielle-2027", "repository observatoire-presidentielle-2027"),
    (". Les caches téléchargés (~900 Ko chez MieuxVoter) ne sont pas recopiés : ils se rechargent, et la source est citée.",
     ". Downloaded caches (~900 KB from MieuxVoter) are not copied over: they reload, and the source is credited."),
    (". Journal des changements de chiffres et de textes :", ". Log of changes to figures and text:"),
]


def _fragments_tries():
    return sorted(FRAGMENTS + EXACTES, key=lambda p: len(p[0]), reverse=True)


def traduire(html):
    """Remplace les fragments français dans les nœuds de texte, jamais dans les balises."""
    import re
    TRI = _fragments_tries()

    EXACT = {fr: en for fr, en in FRAGMENTS + EXACTES}

    def sur_texte(mo):
        # mo.group(1) est le texte seul : les chevrons appartiennent au motif et ne
        # doivent pas être réémis, sinon on obtient « >>FR<< » dans la page.
        brut = mo.group(1)
        # Un nœud fait uniquement d'espaces sépare deux éléments en ligne : le vider
        # collerait le lien et son libellé (« election· workflow »). On le garde tel quel.
        if not brut.strip():
            return brut
        norme = " ".join(brut.split())
        if norme in EXACT:
            return EXACT[norme]
        # Les phrases du gabarit sont coupées sur plusieurs lignes : on travaille
        # donc sur le texte normalisé, sinon aucun fragment ne pourrait s'y trouver.
        for fr, en in TRI:
            if fr in norme:
                norme = norme.replace(fr, en)
        return norme

    # On ne traite que le texte entre les balises : les attributs restent intacts.
    return re.sub(r"(?<=>)([^<>]+)(?=<)", sur_texte, html)


def restes(html):
    """Liste les nœuds de texte encore français, pour contrôle avant publication."""
    import re
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S)
    noeuds = re.findall(r">([^<>]+)<", html)
    marque = re.compile(r"[àâçéèêëîïôûùüÿœ]|\b(le|la|les|des|une|est|sont|sur|pour|avec|dans|aux|du|au|qui|que)\b", re.I)
    vus, sortie = set(), []
    for n in noeuds:
        n = " ".join(n.split())
        if len(n) > 3 and marque.search(n) and n not in vus:
            vus.add(n)
            sortie.append(n)
    return sortie


# Textes qui ont la même forme dans les deux langues sans être des oublis : noms de
# fichiers, chemins, domaines, en-têtes HTTP, sigles. Tout autre texte identique
# dans les deux pages signale une traduction manquante.
AUTORISES = {
    "· workflow", "Workflow", "DATA · CACHE", "PUBLICATION", "ORCHESTRATION",
    "Orchestration", "Publication", "2022 · stable", "Cache-Control: no-cache",
    "absolute_redirect off", "handle /observatoire*", "Caddy — reverse proxy",
    "nginx:alpine — simulation-poc", "MieuxVoter/presidentielle2027",
    "whyalwaysrose", "observatoire-presidentielle-2027", "dileviathan.fr",
    "J−132", "&#9681;", "Cron · 0 18 * * *",
    "→ data/polls.json", "→ data/forecast_bayes.json", "→ data/polls2022.json",
}


def restes_par_comparaison(html_fr, html_en):
    """Textes présents à l'identique dans les deux langues, hors éléments autorisés."""
    import re

    def noeuds(h):
        h = re.sub(r"<(script|style)\b.*?</\1>", " ", h, flags=re.S)
        h = re.sub(r"<!--.*?-->", " ", h, flags=re.S)
        return [" ".join(x.split()) for x in re.findall(r">([^<>]+)<", h)]

    ens_en = set(noeuds(html_en))
    sortie = []
    for x in noeuds(html_fr):
        if len(x) < 3 or x in AUTORISES or x in sortie:
            continue
        if x in ens_en and re.search(r"[A-Za-zÀ-ÿ]", x):
            # les chemins et les noms de fichiers sont légitimes
            if re.fullmatch(r"[\w./\-]+", x):
                continue
            sortie.append(x)
    return sortie
