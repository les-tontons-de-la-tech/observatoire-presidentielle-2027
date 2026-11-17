#!/usr/bin/env python3
"""
Observatoire des sondages de la présidentielle 2027 — pages publiées (agrégation, rétro-test).

Source de données : MieuxVoter/presidentielle2027 (licence MIT)
  https://github.com/MieuxVoter/presidentielle2027
Sortie : site/index.html (statique, sans JS) + data/summary.json

Méthode (volontairement simple et publiée) :
  - on ne garde qu'un seul scénario de candidatures (celui qui compte le plus
    de sondages récents), parce que mélanger les scénarios n'a pas de sens ;
  - poids = décroissance temporelle (demi-vie 30 j) x racine de la taille
    de l'échantillon ;
  - intervalle à 95 % = 1,96 x écart-type pondéré / racine de l'effectif
    effectif (n_eff = (Σw)² / Σw²) ;
  - correction des effets de maison par institut (estimation itérative, contraction
    vers zéro selon le nombre d'enquêtes) ;
  - fenêtre de sélection du scénario et correction des effets de maison validées
    par le rétro-test 2022 (backtest2022.py), pas choisies au feeling.
"""
import json, math, os, csv, urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta

SRC = "https://raw.githubusercontent.com/MieuxVoter/presidentielle2027/refs/heads/main/presidentielle2027.json"
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
SITE = os.path.join(BASE, "site")
SCENARIO_WINDOW = 90   # fenêtre de sélection du scénario (validée par le rétro-test 2022 : couverture
                       # 6/6 des échéances et erreur moyenne 3,15 pt contre 3,22 pt à 60 jours)
HOUSE_CORRECTION = True  # correction des effets de maison par institut (rétro-test : −0,04 pt)
AGG_WINDOW = 180       # fenêtre d'agrégation des sondages du scénario retenu
# Dates des tours de scrutin (à renseigner dès leur fixation par décret) : la publication cesse
# automatiquement la veille et le jour de chaque tour (art. 11 de la loi du 19 juillet 1977).
SCRUTINS = [date(2027, 4, 18), date(2027, 5, 2)]   # 1er et 2d tour, dates officielles
# Source : compte rendu du Conseil des ministres du 1er juillet 2026 (info.gouv.fr). Sert à deux
# choses : le compte à rebours affiché, et la suspension légale de publication la veille et le jour
# de chaque tour (art. 11 de la loi du 19 juillet 1977).
SCRUTIN_1 = SCRUTINS[0] if SCRUTINS else None


def suspension_legale(ref=None):
    """Vrai si la publication de chiffres est interdite à cette date (veille ou jour de scrutin)."""
    ref = ref or TODAY
    for s in SCRUTINS:
        if ref in (s - timedelta(days=1), s):
            return s
    return None


HALF_LIFE = 30      # demi-vie
MIN_POLLS = 3          # nombre minimum de sondages pour être publié
IC_FLOOR = 1.0         # plancher de l'intervalle (± points) : anti-fausse précision
TODAY = date.today()


# ── Données structurées et mesure d'audience (17/09/2026) ────────────────────────────
# Une seule source pour les six pages : le titre et la description d'une page servent à
# la fois à ses données structurées et à sa balise <meta>. Deux textes divergents pour la
# même page seraient exactement le genre d'incohérence qu'un audit reproche.
SITE_URL = "https://dileviathan.fr"
MATOMO_URL = "https://analytics.dileviathan.fr/"

PAGES_LD = {
    "/observatoire/": ("Présidentielle 2027 — observatoire des sondages, agrégation sourcée",
        "Observatoire des sondages de la présidentielle 2027 : agrégation sourcée des enquêtes publiées, méthode publiée, limites affichées.",
        "WebPage"),
    "/observatoire/sondages/": ("Présidentielle 2027 — agrégation des sondages, méthode et limites",
        "Moyenne de sondages de la présidentielle 2027 : pondération, intervalle, marges de chaque enquête, mentions légales et limites.",
        "Article"),
    "/observatoire/candidats/": ("Les candidats à la présidentielle 2027 — qui est déclaré, qui ne l'est pas",
        "Qui est candidat à la présidentielle de 2027 : déclarés, candidatures sous condition, suspens, retraits, et ce qu'il reste à trancher.",
        "Article"),
    "/observatoire/backtest/": ("Rétro-test 2022 — la méthode mise à l'épreuve",
        "La méthode d'agrégation rejouée sur la campagne de 2022 : erreur moyenne, grilles de sensibilité, et la décision qui en découle.",
        "Article"),
    "/observatoire/lois/": ("Veille législative — les textes « technologie et pouvoir »",
        "Ce que le Parlement vote sur le numérique, les données et la surveillance : les scrutins publics de l'Assemblée nationale, par texte et par groupe.",
        "Article"),
    "/observatoire/workflow/": ("Comment ce site se fabrique",
        "Comment l'observatoire se fabrique : sources, cache, calculs, pages statiques, publication et orchestration quotidienne, en un schéma.",
        "TechArticle"),
}


# Métadonnées anglaises. Mêmes clés, mêmes types que PAGES_LD : une page française et sa
# jumelle anglaise ne peuvent pas décrire deux choses différentes. Les titres restent sous
# 60 caractères et les descriptions entre 120 et 160, comme leurs équivalents français.
PAGES_LD_EN = {
    "/observatoire/": ("2027 presidential election — poll monitor, sourced aggregation",
        "Poll monitor for the 2027 presidential election: sourced aggregation of the published surveys, published method, limits displayed.",
        "WebPage"),
    "/observatoire/sondages/": ("2027 presidential election — poll aggregation, method and limits",
        "Averaging the 2027 presidential election polls: weighting, confidence interval, margins for each survey, legal notice and limits.",
        "Article"),
    "/observatoire/candidats/": ("Candidates in the 2027 presidential election — declared or not",
        "Who is running in the 2027 presidential election: declared candidates, conditional bids, pending cases, withdrawals, and what remains to be settled.",
        "Article"),
    "/observatoire/backtest/": ("2022 backtest — the method put to the test",
        "The aggregation method replayed on the 2022 campaign: average error, sensitivity grids, and the decision that follows from it.",
        "Article"),
    "/observatoire/lois/": ("Legislative watch — technology and power bills",
        "What Parliament votes on digital, data and surveillance: the public votes of the National Assembly, by bill and by political group.",
        "Article"),
    "/observatoire/workflow/": ("How this monitor is built",
        "How the monitor is built: sources, cache, calculations, static pages, publication and daily orchestration, in one diagram.",
        "TechArticle"),
}

TITRES_COURTS_EN = {
    "/observatoire/": "2027 election — poll monitor",
    "/observatoire/sondages/": "2027 election — poll aggregation",
    "/observatoire/candidats/": "Candidates in the 2027 election",
    "/observatoire/backtest/": "2022 backtest — the method at work",
    "/observatoire/lois/": "Legislative watch — tech bills voted",
    "/observatoire/workflow/": "How this monitor is built",
}


def table_ld(lang):
    """Table de métadonnées de la langue demandée (français par défaut)."""
    return PAGES_LD_EN if lang == "en" else PAGES_LD


def url_page(chemin, lang="fr"):
    """Adresse publique d'une page, arborescence anglaise comprise."""
    if lang == "en":
        return SITE_URL + chemin.replace("/observatoire/", "/observatoire/en/", 1)
    return SITE_URL + chemin


DESC_MIN = 120
DESC_MAX = 160

# ── Le jeu de données machine de l'agrégation ──────────────────────────────────────────────
# Il est écrit par ecrire_dataset() en même temps que la page ; ici, on ne fait que le DÉCLARER.
# Un `Dataset` sans `distribution` ne dit rien de vérifiable : l'export existe depuis le
# 19/10/2026 (JSON + CSV), c'est lui qu'on pointe, et pas une URL à venir.
DATASET_ID = SITE_URL + "/observatoire/sondages/#dataset"
DATASET_LD = {
    "@type": "Dataset",
    "@id": DATASET_ID,
    "name": "Agrégation des sondages de la présidentielle 2027",
    "description": "Moyenne pondérée des enquêtes publiées pour l'élection présidentielle de "
                   "2027, candidat par candidat : intention de vote, intervalle de confiance à "
                   "95 %, amplitude, effectif corrigé des poids et instituts contributeurs.",
    "url": SITE_URL + "/observatoire/sondages/",
    "inLanguage": "fr-FR",
    "isAccessibleForFree": True,
    "license": SITE_URL + "/fr/mentions-legales",
    "creator": {"@id": SITE_URL + "/#person"},
    "publisher": {"@id": SITE_URL + "/#organization"},
    "variableMeasured": [
        "intention de vote (points de pourcentage)",
        "intervalle de confiance à 95 % (points de pourcentage)",
        "nombre d'enquêtes agrégées",
        "effectif corrigé des poids (milliers)",
    ],
    "distribution": [
        {"@type": "DataDownload", "encodingFormat": "application/json",
         "contentUrl": SITE_URL + "/observatoire/sondages/donnees.json"},
        {"@type": "DataDownload", "encodingFormat": "text/csv",
         "contentUrl": SITE_URL + "/observatoire/sondages/donnees.csv"},
    ],
}
# Pages qui portent le jeu de données : l'accueil de l'observatoire (par où l'on entre) et la
# page qui l'affiche. Ailleurs, le nœud serait du bruit.
PAGES_DATASET = ("/observatoire/", "/observatoire/sondages/")


def couper_description(texte, maxi=DESC_MAX, mini=DESC_MIN):
    """Ramène une description sous la limite que les moteurs affichent, sans la charcuter.

    Deux règles, dans cet ordre :
      1. si un point de fin de phrase tombe au-delà de `mini`, on coupe là — la phrase reste
         entière, et c'est la coupe la moins visible ;
      2. sinon on coupe au dernier mot entier, et on l'annonce par des points de suspension.

    Jamais de coupe au caractère : « … transférabilit » ne se lit pas. Mêmes bornes que
    `couperDescription()` côté site (`src/lib/seo.ts`, DESC_MIN/DESC_MAX) : une seule
    définition de « ce qui tient », des deux côtés.
    """
    texte = " ".join(texte.split())  # les coupures nettes dépendent d'espaces normalisés
    if len(texte) <= maxi:
        return texte
    tranche = texte[:maxi]
    fin = max(tranche.rfind(". "), tranche.rfind("! "), tranche.rfind("? "), tranche.rfind("» "))
    # Cas de bord trouvé par le contrôle : si la phrase se termine pile au dernier caractère
    # de la tranche, le motif « point + espace » n'y figure pas — on coupait alors au mot avec
    # ellipse alors que la phrase tenait entière. On regarde donc aussi le bord.
    if tranche and tranche[-1] in ".!?»":
        fin = maxi - 1
    if fin >= mini:
        return tranche[: fin + 1].strip()
    coupe = tranche.rfind(" ")
    if coupe <= 0:
        coupe = maxi - 1
    return tranche[:coupe].rstrip(" ,;:.") + "…"


def meta_description(chemin, lang="fr"):
    """Description de la balise <meta>, tenue entre 120 et 160 caractères.

    Le texte de l'auteur reste intégral dans PAGES_LD : il alimente les données structurées et
    reste la source du JSON-LD. Seule la balise <meta> — ce que le moteur affiche et tronque à
    sa façon — est ramenée sous la limite, exactement comme `titre_court()` le fait pour
    <title>. Audit Ahrefs du 17/09/2026 (« Meta description too long »), resté ouvert sur
    /observatoire/backtest2017/ parce que cette fonction était un simple passe-plat.

    La borne basse est un objectif d'écriture, pas une contrainte de code : on ne complète pas
    une description trop courte, on ne l'invente pas — c'est à l'auteur de l'écrire.
    """
    return couper_description(table_ld(lang)[chemin][1])


def titre_court(chemin, lang="fr"):
    """Titre de la balise <title>, tenu sous 60 caractères.

    Le nom complet de la page reste dans PAGES_LD (données structurées) et dans le <h1> :
    seule la balise <title> est raccourcie, parce qu'au-delà d'une soixantaine de caractères
    les moteurs en coupent la fin eux-mêmes, sans choisir où. Audit Ahrefs du 17/09/2026.
    """
    table_courts = TITRES_COURTS_EN if lang == "en" else TITRES_COURTS
    return table_courts.get(chemin, table_ld(lang)[chemin][0])


TITRES_COURTS = {
    "/observatoire/": "Présidentielle 2027 — observatoire des sondages",
    "/observatoire/sondages/": "Présidentielle 2027 — agrégation des sondages",
    "/observatoire/candidats/": "Les candidats à la présidentielle 2027",
    "/observatoire/backtest/": "Rétro-test 2022 — la méthode à l'épreuve",
    "/observatoire/lois/": "Veille législative — les textes numériques votés",
    "/observatoire/workflow/": "Comment cet observatoire se fabrique",
}


def meta_social(chemin, lang="fr"):
    """Balises Open Graph et carte X d'une page de l'observatoire.

    Audit Ahrefs du 17/09/2026 : les six pages n'avaient ni Open Graph ni carte X
    (« Open Graph tags missing » et « X (Twitter) card missing »). Les valeurs viennent de
    PAGES_LD — même source que la balise <meta> et les données structurées, pour que les
    trois ne puissent pas diverger.
    """
    from html import escape
    titre, description, _ = table_ld(lang)[chemin]
    url = url_page(chemin, lang)
    image = SITE_URL + "/images/og.jpg"
    return "\n".join([
        '<meta property="og:type" content="article">',
        '<meta property="og:site_name" content="Diléviathan">',
        f'<meta property="og:locale" content="{"en_GB" if lang == "en" else "fr_FR"}">',
        f'<meta property="og:url" content="{url}">',
        f'<meta property="og:title" content="{escape(titre)}">',
        f'<meta property="og:description" content="{escape(description)}">',
        f'<meta property="og:image" content="{image}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{escape(titre)}">',
        f'<meta name="twitter:description" content="{escape(description)}">',
        f'<meta name="twitter:image" content="{image}">',
    ])


def ld_json(chemin, lang="fr"):
    """Données structurées d'une page de l'observatoire.

    Le graphe est auto-portant : la page, le site, l'auteur et l'éditeur sont décrits ici,
    et reliés par @id aux mêmes entités que celles déclarées par le site Next.js. C'est ce
    qui permet à un moteur de rattacher cette page à une personne et à une organisation.
    """
    import json as _json
    titre, description, type_page = table_ld(lang)[chemin]
    url = url_page(chemin, lang)
    graphe = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": type_page,
                "@id": url + "#page",
                "url": url,
                "name": titre,
                "description": description,
                "inLanguage": "en-GB" if lang == "en" else "fr-FR",
                "dateModified": TODAY.isoformat(),
                "isPartOf": {"@id": SITE_URL + "/#website"},
                "author": {"@id": SITE_URL + "/#person"},
                "publisher": {"@id": SITE_URL + "/#organization"},
            },
            {"@type": "WebSite", "@id": SITE_URL + "/#website", "url": SITE_URL,
             "name": "Diléviathan", "inLanguage": "fr-FR"},
            {"@type": "Person", "@id": SITE_URL + "/#person", "name": "Christophe Wiest",
             "url": SITE_URL + "/fr/a-propos"},
            {"@type": "Organization", "@id": SITE_URL + "/#organization", "name": "Flying Kujira",
             "url": SITE_URL},
        ],
    }
    # Le jeu de données est une entité à part de la page : on l'ajoute au graphe plutôt que de
    # changer le type de la page, pour que « ceci est un article qui décrit un jeu de données »
    # reste lisible. Même @id sur les deux pages qui le portent : une seule entité, pas deux.
    if chemin in PAGES_DATASET:
        graphe["@graph"].append(dict(DATASET_LD, dateModified=TODAY.isoformat()))
    return ('<script type="application/ld+json">'
            + _json.dumps(graphe, ensure_ascii=False, separators=(",", ":"))
            + "</script>")


def matomo():
    """Mesure d'audience — site 1 en production, site 2 sur le bac à sable.

    L'observatoire n'est aujourd'hui servi que sur dileviathan.fr (conteneur nginx
    « simulation-poc », un seul jeu de fichiers : publier, c'est mettre en production).
    Le garde-fou sur le nom d'hôte n'a donc pas d'effet aujourd'hui ; il évite que des
    visites de bac à sable polluent les statistiques de production le jour où
    l'observatoire sera aussi exposé sur dev.dileviathan.fr.
    """
    return """<script>
(function(){
  var u = '%s';
  var id = (location.hostname.indexOf('dev.') === 0) ? 2 : 1;
  window._paq = window._paq || [];
  _paq.push(['setTrackerUrl', u + 'matomo.php']);
  _paq.push(['setSiteId', id]);
  _paq.push(['enableLinkTracking']);
  // Sans cet ordre, Matomo ne compte AUCUNE vue : le script se charge, aucune requête
  // vers matomo.php n'est émise, et rien ne le signale. Zéro vue silencieux, constaté
  // du 14/09 au 07/10/2026. Ne pas le retirer.
  _paq.push(['trackPageView']);
  var g = document.createElement('script'); g.async = true; g.src = u + 'matomo.js';
  document.head.appendChild(g);
})();
</script>""" % MATOMO_URL


def _sondages(payload):
    """La forme du jeu de données amont a changé le 22/09/2026.

    C'était une liste de sondages ; c'est désormais un objet qui les range sous la clé « polls »,
    à côté de la source, des règles d'usage et des hypothèses. On accepte les deux formes, et on
    écarte en le disant toute entrée qui n'est pas exploitable : une ligne douteuse ne doit pas
    faire tomber l'agrégation du jour.
    """
    if isinstance(payload, dict):
        arr = payload.get("polls") or []
        if not arr:
            raise SystemExit(f"Charge amont sans liste de sondages : clés {sorted(payload)}")
    else:
        arr = payload
    bons = [p for p in arr if isinstance(p, dict)]
    if len(bons) != len(arr):
        print(f"⚠ {len(arr) - len(bons)} entrée(s) de sondage ignorée(s) : format inattendu")
    return bons


OVERLAY = os.path.join(DATA, "polls_importes.json")
IDS_IMPORTES = set()  # poll_id des enquêtes ajoutées par notre extraction, pour les signaler


def _cle_nom(nom):
    """Nom de candidat ramené à une forme comparable (accents, casse, tirets, espaces)."""
    import unicodedata
    n = unicodedata.normalize("NFKD", str(nom or ""))
    n = "".join(c for c in n if not unicodedata.combining(c)).lower().replace("-", " ")
    return " ".join(n.split())


def _identite_sondage(p):
    """Clé de dédoublonnage : institut + dates de terrain + ensemble des candidats testés.

    Ni le poll_id ni le numéro d'hypothèse ne peuvent servir : l'amont réutilise le même
    poll_id pour plusieurs tableaux d'une même enquête (sept hypothèses partagent un seul
    identifiant chez OpinionWay), et sa numérotation H… ne coïncide pas avec la nôtre.
    L'ensemble des candidats testés, lui, décrit le tableau lui-même.
    """
    noms = frozenset(_cle_nom(c.get("candidat") or c.get("complete_name") or "")
                     for c in (p.get("candidats") or []))
    return (str(p.get("institut") or p.get("nom_institut") or "").strip().lower(),
            str(p.get("debut_enquete") or ""), str(p.get("fin_enquete") or ""), noms)


def _avec_imports(sondages):
    """Ajoute les enquêtes extraites par nos soins que l'amont n'a pas encore intégrées.

    L'amont gagne toujours : dès qu'il publie la même enquête (même identité, ou même
    poll_id), notre ligne est écartée. Le jour où MieuxVoter reprend son intégration,
    l'apport disparaît de lui-même et la chaîne redevient exactement la sienne. C'est ce
    qui rend ce mécanisme réversible : l'import ne remplace pas la source, il comble le
    trou tant qu'il existe.
    """
    if os.environ.get("OBS_SANS_IMPORT") == "1" or not os.path.exists(OVERLAY):
        return sondages
    try:
        importes = json.load(open(OVERLAY, encoding="utf-8"))
    except (ValueError, OSError):
        print("⚠ polls_importes.json illisible : chaîne amont seule")
        return sondages
    importes = importes.get("polls", importes) if isinstance(importes, dict) else importes
    identites = {_identite_sondage(p) for p in sondages}
    # Pas de test sur poll_id : il n'est pas unique dans la source (plusieurs tableaux d'une
    # même enquête le partagent), et s'en servir écartait un tableau légitime.
    #
    # Cas résiduel : le même tableau chez eux et chez nous, mais ils impriment un candidat
    # sous 1 % (« <1 % ») que notre extraction n'a pas retenu faute de valeur numérique.
    # Nos noms forment alors un sous-ensemble des leurs, avec les mêmes chiffres : c'est la
    # même enquête, on garde la leur.
    par_enquete = {}
    for p in sondages:
        k = (str(p.get("institut") or "").strip().lower(), p.get("debut_enquete"), p.get("fin_enquete"))
        par_enquete.setdefault(k, []).append({
            _cle_nom(c.get("candidat") or ""): c.get("intentions") for c in (p.get("candidats") or [])})

    def _deja_chez_eux(p):
        k = (str(p.get("institut") or "").strip().lower(), p.get("debut_enquete"), p.get("fin_enquete"))
        nous = {_cle_nom(c.get("candidat") or ""): c.get("intentions") for c in (p.get("candidats") or [])}
        for leur in par_enquete.get(k, []):
            if nous and set(nous) <= set(leur) and all(leur[n] == v for n, v in nous.items()):
                return True
        return False

    gardes = [p for p in importes
              if _identite_sondage(p) not in identites and not _deja_chez_eux(p)]
    if gardes:
        IDS_IMPORTES.update(p.get("poll_id") for p in gardes if p.get("poll_id"))
        print(f"imports locaux : {len(gardes)} enquête(s) ajoutée(s) à la source amont")
    return sondages + gardes


def fetch(force=False):
    os.makedirs(DATA, exist_ok=True)
    cache = os.path.join(DATA, "polls.json")
    if not force and os.path.exists(cache):
        age_h = (datetime.now().timestamp() - os.path.getmtime(cache)) / 3600
        if age_h < 12:
            return _avec_imports(_sondages(json.load(open(cache, encoding="utf-8"))))
    req = urllib.request.Request(SRC, headers={"User-Agent": "poc-agregateur-2027"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8")
        json.loads(raw)  # validation
    except Exception as e:  # réseau, 404, réponse illisible
        # La source est la base, pas une condition de survie : si elle est injoignable, on
        # republie le dernier état connu plutôt que de laisser la page se figer sans le dire.
        # Le cache est daté dans le message, pour que la péremption reste visible.
        if os.path.exists(cache):
            age = (datetime.now().timestamp() - os.path.getmtime(cache)) / 3600
            quand = datetime.fromtimestamp(os.path.getmtime(cache)).strftime("%d/%m/%Y %H:%M")
            print(f"⚠ source amont injoignable ({type(e).__name__}) : reprise du cache "
                  f"du {quand} ({age:.0f} h)")
            return _avec_imports(_sondages(json.load(open(cache, encoding="utf-8"))))
        raise SystemExit(f"Source amont injoignable ({type(e).__name__}) et aucun cache local : "
                         "rien à publier, la page reste en l'état.")
    open(cache, "w", encoding="utf-8").write(raw)
    return _avec_imports(_sondages(json.loads(raw)))


FORECAST_URL = ("https://raw.githubusercontent.com/whyalwaysrose/presidentielle-2027/"
                "main/site/data/forecast.json")


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "poc-agregateur-2027"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def fetch_forecast(force=False):
    """Prévision bayésienne whyalwaysrose/presidentielle-2027 (MIT) : probabilités, pas intentions.
    Toute erreur renvoie None — la page se génère sans la comparaison."""
    cache = os.path.join(DATA, "forecast_bayes.json")
    if not force and os.path.exists(cache):
        age_h = (datetime.now().timestamp() - os.path.getmtime(cache)) / 3600
        if age_h < 6:
            try:
                return json.load(open(cache, encoding="utf-8"))
            except Exception:
                pass
    try:
        fc = _get_json(FORECAST_URL)
        keep = dict(
            as_of=fc.get("as_of"), generated_at=fc.get("generated_at"),
            n_simulations=fc.get("n_simulations"), election=fc.get("election"),
            sondages=fc.get("sondages"), diagnostics=fc.get("diagnostics"),
            duels=fc.get("duels") or [],
            candidats=[dict(id=c.get("id"), nom=c.get("nom"), parti=c.get("parti"),
                            share=c.get("share"), p_qualify=c.get("p_qualify"),
                            p_win=c.get("p_win"), p_standing=c.get("p_standing"))
                       for c in fc.get("candidats") or []])
        json.dump(keep, open(cache, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return keep
    except Exception:
        # Échec du fetch : conserver le cache existant avec horodatage
        if os.path.exists(cache):
            try:
                stale = json.load(open(cache, encoding="utf-8"))
                stale["cached_at"] = os.path.getmtime(cache)
                return stale
            except Exception:
                return None


def _match_forecast(nom, cands):
    """Rapproche un candidat de notre tableau de son équivalent dans la prévision."""
    for c in cands:
        if (c.get("nom") or "").lower() == nom.lower():
            return c
    last = nom.split()[-1].lower()
    for c in cands:
        if (c.get("nom") or "").lower().endswith(last):
            return c
    return None


def forecast_rows(agg, trends, fc):
    """Lignes de comparaison, pour le tableau de la page."""
    cands = (fc or {}).get("candidats") or []
    allx = dict(agg.get("all_lists") or {})
    if not allx:
        allx = {m["candidat"]: m["intentions"] for m in (trends or [])}
    out = []
    for r in agg["rows"]:
        c = _match_forecast(r["candidat"], cands)
        sh = (c or {}).get("share") or {}
        out.append(dict(
            candidat=r["candidat"], nous_num=r["intentions"],
            nous_tous_num=allx.get(r["candidat"]),
            nous=fr1u(r["intentions"]), nous_tous=fr1u(allx.get(r["candidat"])),
            q50=(None if sh.get("q50") is None else round(sh["q50"] * 100, 1)),
            q05=(None if sh.get("q05") is None else round(sh["q05"] * 100, 1)),
            q95=(None if sh.get("q95") is None else round(sh["q95"] * 100, 1)),
            p_qualify=(None if not c else round((c.get("p_qualify") or 0) * 100, 1)),
            p_win=(None if not c else round((c.get("p_win") or 0) * 100, 1)),
        ))
    return out


def backtest_summary():
    """Résumé du rétro-test 2022 s'il a été calculé (backtest2022.py). None sinon."""
    f = os.path.join(DATA, "backtest2022.json")
    if not os.path.exists(f):
        return None
    try:
        bt = json.load(open(f, encoding="utf-8"))
        m = bt["dernier"]["modes"]
        return dict(date=bt["dernier"]["date"], jours=bt["dernier"]["jours_avant"],
                    mae=m[0]["mae"], egal=m[1]["mae"], dernier=m[2]["mae"],
                    top2=m[0]["top2"], n=m[0]["n"], non_cand=m[0]["poids_non_candidats"],
                    genere=bt["genere"], sondage_max=bt["dernier_sondage"])
    except Exception:
        return None


def backtest_block(lang="fr"):
    """Bloc de validation, affiché avec la comparaison bayésienne."""
    m = (lambda a, b: b) if lang == "en" else (lambda a, b: a)
    b = backtest_summary()
    if not b:
        return ('<h3 style="margin-top:24px">' + m("Validation", "Validation") + '</h3><p class="small muted">'
                + m("Rétro-test 2022 non calculé (lancer ", "2022 backtest not computed (run ")
                + '<code>python3 backtest2022.py</code>).</p>')
    top2 = m(" et ", " and ").join(b["top2"])
    return (
        '<h3 style="margin-top:24px">'
        + m("Validation : la méthode rejouée sur 2022", "Validation: the method replayed on 2022") + '</h3>'
        '<p class="small" style="max-width:none">'
        + m("Rejouée sur la campagne 2022 (sondages compilés sous licence MIT, résultat officiel vérifié), "
            "notre agrégation affiche ",
            "Replayed on the 2022 campaign (compiled polls under MIT licence, official result verified), "
            "our aggregation shows ")
        + '<strong>' + fr1u(b["mae"])
        + m(" point d'erreur moyenne", " point mean error") + '</strong> '
        + m("à J−", "at D−") + str(b["jours"]) + ", " + str(b["n"])
        + m(" candidats réels publiés, et les deux finalistes identifiés (",
            " real candidates published, and both finalists identified (") + top2 + "). "
        + m("Deux enseignements désagréables : la pondération par fraîcheur n'apporte <em>rien</em> "
            "face à la dernière enquête seule (",
            "Two unpleasant lessons: recency weighting adds <em>nothing</em> over the latest poll alone (")
        + fr1u(b["dernier"]) + m(" point), et le poids donné aux non-candidats atteignait ",
                                 " point), and the weight given to non-candidates reached ")
        + fr1u(b["non_cand"]) + m(" points au dernier point. ", " points at the last data point. ")
        + '<a href="/observatoire/backtest/">'
        + m("Voir le rétro-test complet, échéance par échéance",
            "See the full backtest, deadline by deadline") + '</a>.</p>')


def compare_table(agg, trends, fc, lang="fr"):
    m = (lambda a, b: b) if lang == "en" else (lambda a, b: a)
    rows = forecast_rows(agg, trends, fc)
    body = "\n".join(
        f'<tr><td>{r["candidat"]}</td>'
        f'<td class="num">{r["nous"]}</td>'
        f'<td class="num muted">{r["nous_tous"]}</td>'
        f'<td class="num"><strong>{fr1u(r["q50"])}</strong></td>'
        f'<td class="num muted small">{fr1u(r["q05"])} – {fr1u(r["q95"])}</td>'
        f'<td class="num muted">{fr1u(r["p_qualify"])}</td>'
        f'<td class="num">{fr1u(r["p_win"])}</td></tr>'
        for r in rows)
    head = ('<tr><th rowspan="2">' + m("Candidat", "Candidate") + '</th>'
            '<th class="num" colspan="2">MieuxVoter<br><span class="muted small">'
            + m("agrégation des sondages compilés", "aggregation of the compiled polls") + '</span></th>'
            '<th class="num" colspan="4">'
            + m("Prévision bayésienne", "Bayesian forecast") + '<br><span class="muted small">'
            'whyalwaysrose, 80 000 simulations</span></th></tr>'
            '<tr><th class="num small">' + m("scénario ", "scenario ") + str(agg["scenario"]) + '</th>'
            '<th class="num small">' + m("toutes listes", "all lists") + '</th>'
            '<th class="num small">' + m("médiane 1<sup>er</sup> tour", "median 1st round") + '</th>'
            '<th class="num small">90 % (5–95)</th>'
            '<th class="num small">' + m("P(2<sup>e</sup> tour)", "P(runoff)") + '</th>'
            '<th class="num small">' + m("P(victoire)", "P(victory)") + '</th></tr>')
    return ('<table style="margin-top:10px">' + head + body + '</table>')


def compare_duels(fc, lang="fr"):
    duels = sorted((fc or {}).get("duels") or [], key=lambda z: -(z.get("p_matchup") or 0))[:5]
    if not duels:
        return ""
    m = (lambda a, b: b) if lang == "en" else (lambda a, b: a)
    pour = m("pour", "for")
    body = "\n".join(
        f'<tr><td>{x.get("nom_a")} <span class="muted small">vs</span> {x.get("nom_b")}</td>'
        f'<td class="num muted">{fr1u((x.get("p_matchup") or 0) * 100)} %</td>'
        f'<td class="num"><strong>{fr1u((x.get("p_a_wins") or 0) * 100)} %</strong> '
        f'<span class="muted small">{pour} {x.get("nom_a")}</span></td></tr>'
        for x in duels)
    return ('<h3 style="margin-top:24px">'
            + m("Leurs duels les plus probables", "Their most likely runoffs") + '</h3>'
            '<table style="margin-top:8px"><tr><th>'
            + m("Affiche", "Matchup") + '</th>'
            '<th class="num">' + m("Probabilité du duel", "Probability of the matchup") + '</th>'
            '<th class="num">' + m("Issue", "Outcome") + '</th></tr>'
            + body + '</table>')


def forecast_block(agg, trends, fc, lang="fr"):
    """Comparaison honnête : moyenne maison (scénario verrouillé) vs prévision bayésienne."""
    m = (lambda a, b: b) if lang == "en" else (lambda a, b: a)
    if not fc or not fc.get("candidats"):
        return ('<p class="small muted">'
                + m("Prévision bayésienne indisponible à cette génération (source externe) — la page reste complète par ailleurs.",
                    "Bayesian forecast unavailable for this build (external source) — the rest of the page is complete.")
                + '</p>')
    stale = ''
    if fc.get("cached_at"):
        from datetime import datetime as dt
        stale = ('<p class="small muted" style="color:var(--amber);max-width:none">'
                 + m("⚠ Données mises à jour le ", "⚠ Data last updated on ")
                 + dt.fromtimestamp(fc["cached_at"]).strftime("%d/%m/%Y à %H:%M" if lang == "fr" else "%d/%m/%Y at %H:%M")
                 + m(" — la source externe est temporairement injoignable.",
                     " — the external source is temporarily unreachable.")
                 + '</p>')
    d = fc.get("diagnostics") or {}
    s = fc.get("sondages") or {}
    rf = d.get("runoff_fit") or {}
    intro = ('<p class="small muted" style="max-width:none">'
             + m("Deux colonnes de gauche : nos <strong>intentions de vote</strong> mesurées "
                 "(moyenne pondérée). Quatre colonnes de droite : leurs <strong>probabilités</strong> "
                 "issues de 80 000 simulations d'un modèle bayésien. Les niveaux se comparent avec prudence "
                 "(deux objets différents) ; l'incertitude, elle, se compare directement — et elle est "
                 "édifiante.",
                 "Left two columns: our measured <strong>voting intentions</strong> (weighted average). "
                 "Right four columns: their <strong>probabilities</strong> from 80,000 simulations of a "
                 "Bayesian model. Levels are compared cautiously (two different objects); uncertainty, "
                 "on the other hand, compares directly — and it is telling.")
             + '</p>'
             '<p class="small muted" style="max-width:none">'
             + m("Ce que recouvre la colonne « MieuxVoter » : la compilation ouverte des sondages "
                 "(licence MIT) et la moyenne pondérée calculée à partir d'elle, selon la méthode "
                 "publiée plus bas — jamais un chiffre repris tel quel.",
                 "What the \u201cMieuxVoter\u201d column covers: the open compilation of polls (MIT licence) "
                 "and the weighted average computed from it, following the method published below — "
                 "never a figure taken as is.")
             + '</p>')
    chiffres = ('<h3 style="margin-top:24px">'
                + m("La prévision bayésienne, en chiffres", "The Bayesian forecast, in figures")
                + '</h3><ul class="tight small" style="max-width:none">'
                f'<li><strong>{s.get("surveys", "?")} ' + m("enquêtes", "surveys") + '</strong> '
                + m("et ", "and ") + f'<strong>{s.get("hypotheses", "?")} '
                + m("hypothèses", "hypotheses") + '</strong> '
                + m("de candidatures dépouillées ", "of candidacies parsed ")
                + f'({s.get("hypotheses_tour1", "?")} '
                + m("de premier tour, ", "first round, ")
                + f'{s.get("hypotheses_tour2", "?")} '
                + m("de second), ", "second), ")
                + f'{len(s.get("instituts") or [])} ' + m("instituts", "pollsters") + ', '
                + m("du ", "from ") + f'{s.get("date_min")} ' + m("au ", "to ") + f'{s.get("date_max")}'
                + m(" — quand l'agrégation, scénario verrouillé, n'en retient que ",
                    " — where the aggregation, with a locked scenario, keeps only ")
                + f'{agg["polls_aggregated"]}.</li>'
                f'<li><strong>' + m("Échantillon effectif", "Effective sample") + f'</strong> : {frnum(s.get("effective_sample_tour1", 0))} '
                + m("sur ", "out of ") + f'{frnum(s.get("raw_sample_tour1", 0))} '
                + m("bruts, après pondération.", "raw, after weighting.") + '</li>'
                f'<li><strong>{frnum(fc.get("n_simulations", 0))} '
                + m("simulations", "simulations") + '</strong> ; '
                + m("convergence publiée : ", "published convergence: ")
                + f'R̂ max {d.get("max_rhat", "?")}, ESS min {frnum(d.get("min_ess_bulk", 0))}.</li>'
                f'<li><strong>' + m("Validation", "Validation") + '</strong> : '
                + m("rétro-test 2022 sur les duels, erreur absolue moyenne ",
                    "2022 backtest on runoffs, mean absolute error ")
                + f'{fr1u(rf.get("mae_points"))} ' + m("point(s), biais ", "point(s), bias ")
                + f'{fr1u(rf.get("bias_points"))} ; '
                + f'{d.get("n_transferts_2022", "?")} '
                + m("reports de voix de 2022 modélisés.", "vote transfers from 2022 modelled.") + '</li>'
                f'<li><strong>' + m("Mise à jour quotidienne", "Daily update") + '</strong> '
                + m("par GitHub Action ; sortie arrêtée au ", "by GitHub Action; output as of ")
                + f'{fc.get("as_of")} '
                + m("(calcul du ", "(computed ")
                + f'{str(fc.get("generated_at"))[:16]}'
                + m("), site bilingue ", "), bilingual site ")
                + '<a href="https://whyalwaysrose.github.io/presidentielle-2027/">'
                + 'whyalwaysrose.github.io</a>.</li></ul>')
    rows_cmp = forecast_rows(agg, trends, fc)
    ecarts = [r for r in rows_cmp if r["q50"] is not None]
    tete3 = ecarts[:3]
    tete_max = max(tete3, key=lambda r: abs(r["nous_num"] - r["q50"])) if tete3 else None
    reste = ecarts[3:]
    reste_max = max(reste, key=lambda r: abs(r["nous_num"] - r["q50"])) if reste else None
    largeur_agr = 2 * agg["ic_floor"]
    largeur_bayes = (tete_max["q95"] - tete_max["q05"]) if tete_max else None
    facteur = (round(largeur_bayes / largeur_agr, 1) if (largeur_bayes and largeur_agr) else None)
    ecart_txt = " · ".join(
        f'{r["candidat"]} {fr1u(r["nous_num"])} % '
        + m("contre", "against") + f' {fr1u(r["q50"])} %' for r in tete3)
    lecture = (
        '<h3 style="margin-top:24px">'
        + m("Ce qu'on lit dans l'écart", "What the gap says") + '</h3>'
        '<ul class="tight small" style="max-width:none">'
        '<li><strong>'
        + m("Les deux lectures se rejoignent sur le haut du tableau.",
            "Both reads converge at the top of the table.")
        + '</strong> '
        + ecart_txt + m(". Deux méthodes opposées, la même source de sondages : ",
                         ". Two opposite methods, the same poll source: ")
        + ((m("le plus large écart des trois est de ", "the widest gap of the three is ")
            + fr1u(abs(tete_max["nous_num"] - tete_max["q50"]))
            + m(" point (", " point (") + tete_max["candidat"]
            + m("), les autres se comptent en dixièmes.",
                "), the others are counted in tenths."))
           if tete_max else '—') + '</li>'
        '<li><strong>'
        + m("Le reste du tableau suit la même logique", "The rest of the table follows the same logic")
        + '</strong> : '
        + ((m("aucun écart ne dépasse ", "no gap exceeds ")
            + fr1u(abs(reste_max["nous_num"] - reste_max["q50"]))
            + m(" point (", " point (") + reste_max["candidat"] + ')') if reste_max else '—')
        + m(". Là où des écarts subsistent, l'agrégation donne le niveau d'un scénario précis de "
            "candidatures, la prévision bayésienne une moyenne pondérée sur toutes les hypothèses : "
            "l'écart mesure surtout la différence de question posée.",
            ". Where gaps remain, the aggregation gives the level of one precise candidacy scenario, the "
            "Bayesian forecast a weighted average over all hypotheses: the gap mostly measures the "
            "difference in the question asked.")
        + '</li>'
        '<li><strong>'
        + m("L'intervalle de l'agrégation n'est pas un intervalle de prévision.",
            "The aggregation interval is not a forecast interval.")
        + '</strong> '
        + fr1u(largeur_agr) + m(" point du côté MieuxVoter contre ", " point on the MieuxVoter side against ")
        + (fr1u(largeur_bayes) + m(" points dans la prévision bayésienne sur le premier",
                                   " points in the Bayesian forecast on the front-runner")
           if largeur_bayes else '—')
        + (m(f' — un facteur {fr1u(facteur)}', f' — a factor of {fr1u(facteur)}') if facteur else '')
        + m(". La largeur bayésienne contient l'incertitude sur le champ de candidats, les erreurs "
            "d'enquête et la campagne à venir ; l'intervalle d'agrégation ne dit que la dispersion des "
            "sondages retenus.",
            ". The Bayesian width contains the uncertainty over the field of candidates, the polling "
            "errors and the campaign to come; the aggregation interval only reports the dispersion of "
            "the polls kept.")
        + '</li>'
        '<li><strong>'
        + m("Ils répondent à « qui gagne »", "They answer \u201cwho wins\u201d")
        + '</strong>'
        + m(" — P(second tour), P(victoire), duels — ce que cette page ne sait pas faire et ne prétend pas faire.",
            " — P(runoff), P(victory), runoffs — what this page cannot do and does not claim to do.")
        + '</li>'
        '<li><strong>'
        + m("Validation : match nul.", "Validation: a draw.")
        + '</strong> '
        + m("Ils publient rétro-test 2022, convergence MCMC et qualité des instituts ajustée. Nous "
            "publions désormais notre propre rétro-test 2022 — même exercice, un seul millésime, une "
            "erreur de 3,8 points à J−132 et deux réglages corrigés (voir la section Validation "
            "ci-dessous). Ni l'un ni l'autre ne peut prétendre avoir raison : même source de données, "
            "deux modèles, deux façons de se tromper.",
            "They publish a 2022 backtest, MCMC convergence and an adjusted pollster quality. We now "
            "publish our own 2022 backtest — the same exercise, a single vintage, an error of 3.8 points "
            "at D−132 and two settings corrected (see the Validation section below). Neither can claim to "
            "be right: the same data source, two models, two ways of being wrong.")
        + '</li>'
        '<li><strong>'
        + m("Le décalage a une cause connue.", "The offset has a known cause.")
        + '</strong> '
        + m("Nos chiffres de milieu de tableau étaient systématiquement plus bas que les leurs : c'est ce "
            "qui nous a fait passer la fenêtre de sélection du scénario de 60 à 90 jours, après mesure "
            "sur 2022. Depuis, les deux lectures se rejoignent — un modèle bayésien et une moyenne "
            "expliquée ne convergent pas par hasard.",
            "Our mid-table figures were systematically lower than theirs: that is what led us to move the "
            "scenario selection window from 60 to 90 days, after measuring it on 2022. Since then, both "
            "reads converge — a Bayesian model and an explained average do not converge by chance.")
        + '</li>'
        '</ul>')

    garde = ('<p class="small muted" style="max-width:none">'
             + m("Ce que cette page garde : lisibilité totale (aucune dépendance, aucun modèle latent à "
                 "croire sur parole), chiffre explicite d'un scénario donné, aucune donnée non licite. "
                 "Ce qu'il doit emprunter : la validation par rétro-test.",
                 "What this page keeps: full readability (no dependency, no latent model to be taken on "
                 "trust), an explicit figure for a given scenario, no non-licensed data. What it must "
                 "borrow: validation by backtest.")
             + '</p>')
    return intro + stale + compare_table(agg, trends, fc, lang) + chiffres + compare_duels(fc, lang) + lecture + garde


def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def signature(poll):
    return tuple(sorted(c["candidat"] for c in poll.get("candidats", [])))


def _observations(polls_with_age, weight_mode="recence"):
    """Prépare les observations (institut, poids, {candidat: valeur}) pour l'estimation des effets."""
    obs = []
    for poll, age, d in polls_with_age:
        inst = poll.get("institut") or "?"
        if weight_mode == "egal":
            w = 1.0
        elif weight_mode == "dernier":
            w = 1.0
        else:
            w = (math.exp(-math.log(2) * age / HALF_LIFE)
                 * math.sqrt((poll.get("echantillon") or 1000) / 1000.0))
        vals = {c["candidat"]: float(c["intentions"]) for c in poll.get("candidats", [])
                if isinstance(c.get("intentions"), (int, float))}
        if vals:
            obs.append((inst, w, vals))
    return obs


def house_effects(obs, iterations=3, shrink=2.0):
    """Effet de maison par (institut, candidat) : écart moyen du sondage à la moyenne des autres
    instituts, estimé par itérations (les valeurs corrigées nourrissent l'estimation suivante) et
    contracté vers zéro selon le nombre d'enquêtes de l'institut — un institut vu deux fois ne peut
    pas déplacer une moyenne de plusieurs points.

    Retourne {(institut, candidat): effet en points}. Les effets sont centrés par candidat, donc
    relatifs : corriger un institut revient à le rapprocher du consensus des autres."""
    if not obs:
        return {}
    insts = sorted({o[0] for o in obs})
    cands = sorted({c for o in obs for c in o[2]})
    h = {}
    for _ in range(iterations):
        # consensus par candidat, calculé sur les valeurs déjà corrigées
        num, den = defaultdict(float), defaultdict(float)
        for inst, w, vals in obs:
            for c, v in vals.items():
                num[c] += w * (v - h.get((inst, c), 0.0))
                den[c] += w
        cons = {c: num[c] / den[c] for c in num if den.get(c)}
        new = {}
        for inst in insts:
            rows = [(w, vals) for i2, w, vals in obs if i2 == inst]
            for c in cands:
                pairs = [(w, vals[c]) for w, vals in rows if c in vals]
                if not pairs:
                    continue
                sw = sum(w for w, _ in pairs)
                dev = sum(w * (v - cons.get(c, v)) for w, v in pairs) / sw
                n = len(pairs)
                new[(inst, c)] = dev * (n / (n + shrink))
        # centrage par candidat : les effets sont relatifs, pas absolus
        for c in cands:
            vals = [new[(i, c)] for i in insts if (i, c) in new]
            if vals:
                m = sum(vals) / len(vals)
                for i in insts:
                    if (i, c) in new:
                        new[(i, c)] -= m
        h = new
    return h


def corrected_values(poll, h):
    """Valeurs d'un sondage après correction d'effet de maison (bornées à zéro)."""
    inst = poll.get("institut") or "?"
    out = {}
    for c in poll.get("candidats", []):
        if not isinstance(c.get("intentions"), (int, float)):
            continue
        out[c["candidat"]] = max(0.0, float(c["intentions"]) - h.get((inst, c["candidat"]), 0.0))
    return out


def _scenario_precedent():
    """Signature du scénario du dernier relevé publié (data/summary.json), pour départager une égalité.

    Lecture tolérante : fichier absent ou illisible = aucune préférence, la règle du maximum s'applique.
    """
    try:
        with open(os.path.join(DATA, "summary.json"), encoding="utf-8") as f:
            return tuple(json.load(f).get("scenario_sign") or ())
    except Exception:
        return ()


def aggregate(polls, as_of=None, scenario_sign=None, scenario_label=None, weight_mode="recence",
              min_polls=None, scenario_window=None, house_correction=None):
    """Agrégation. `as_of` = date de référence (rétro-calcul) ; `scenario_sign` = verrouille le
    scénario ; `weight_mode` : "recence" | "egal" | "dernier" ; `scenario_window` = fenêtre de
    sélection du scénario (défaut SCENARIO_WINDOW) ; `house_correction` = corrige les effets de
    maison par institut avant agrégation."""
    ref = as_of or TODAY
    swin = SCENARIO_WINDOW if scenario_window is None else scenario_window
    hcorr = HOUSE_CORRECTION if house_correction is None else house_correction
    # 1. 1er tour, date de fin exploitable, enquêtes publiées au plus tard le jour de référence
    r1 = []
    for p in polls:
        if (p.get("tour") or "") != "1er Tour":
            continue
        d = parse_date(p.get("fin_enquete") or "")
        if not d:
            continue
        age = (ref - d).days
        # Tolérance de 3 jours pour le point du jour (dates d'enquête limite) ; coupe stricte
        # pour les points rétro-calculés, sinon un sondage publié après la date serait compté.
        if age < (0 if as_of is not None else -3):
            continue
        r1.append((p, age, d))

    if not r1:
        return None

    # 2. Scénario de référence : la liste **testée le plus récemment** parmi celles qui comptent
    #    au moins `seuil_scen` enquêtes dans la fenêtre courte — pour ne pas moyenner des
    #    configurations de candidatures différentes, et pour ne pas s'accrocher à une liste que
    #    plus aucun institut ne teste. Le 16/11/2026, H42 (20 enquêtes) n'avait plus été testée
    #    depuis le 05/11 quand H67 (19 enquêtes) l'était le 13/11 : compter d'abord le nombre
    #    d'enquêtes figeait la page sur une liste morte.
    if scenario_sign is not None:
        scen_sign = tuple(scenario_sign)
        scen_recent = [(p, age, d) for (p, age, d) in r1
                       if signature(p) == scen_sign and age <= swin]
        scenario = scenario_label or (scen_recent[0][0].get("hypothese") if scen_recent else "—")
    else:
        recent = defaultdict(list)
        for item in r1:
            if item[1] <= swin:
                recent[signature(item[0])].append(item)
        if not recent:
            recent = defaultdict(list)
            for item in r1:
                recent[signature(item[0])].append(item)
        # Une liste testée une seule fois ne devient pas la référence : on exige le même seuil
        # que pour publier un candidat. S'il n'y a pas de quoi, on retombe sur toutes les listes.
        seuil_scen = MIN_POLLS
        eligibles = {k: v for k, v in recent.items() if len(v) >= seuil_scen} or recent
        # Départage : la plus grande fraîcheur, puis le plus de sondages — et, à égalité
        # stricte, la liste du relevé précédent. Sans ce troisième critère, `max()` tranche
        # sur l'ordre interne des données : le 29/09/2026 les deux listes de dix noms
        # comptaient 10 sondages chacune et la page a changé de tableau pour un tirage.
        # Ne s'applique qu'au relevé du jour : un point rétro-calculé garde la règle du maximum.
        precedent = _scenario_precedent() if as_of is None else ()
        scen_sign, scen_recent = max(eligibles.items(),
                                     key=lambda kv: (max(-x[1] for x in kv[1]), len(kv[1]),
                                                     tuple(kv[0]) == precedent))
        scenario = scen_recent[0][0]["hypothese"]

    # 3. Agrégation : tous les sondages de ce scénario dans la fenêtre longue,
    #    pondérés par la fraîcheur (demi-vie) et la taille d'échantillon.
    scen_polls = [(p, age, d) for (p, age, d) in r1 if signature(p) == scen_sign and age <= AGG_WINDOW]
    if not scen_polls:
        return None
    if weight_mode == "dernier":
        newest = max(d for _, _, d in scen_polls)
        scen_polls = [(p, age, d) for (p, age, d) in scen_polls if d == newest]
    h_eff = house_effects(_observations(scen_polls, weight_mode)) if hcorr else {}
    acc = defaultdict(list)
    for poll, age, d in scen_polls:
        if weight_mode == "egal":
            w = 1.0
        else:
            w = math.exp(-math.log(2) * age / HALF_LIFE) * math.sqrt((poll.get("echantillon") or 1000) / 1000.0)
        vals = corrected_values(poll, h_eff) if h_eff else None
        for c in poll.get("candidats", []):
            if isinstance(c.get("intentions"), (int, float)):
                v = vals[c["candidat"]] if vals and c["candidat"] in vals else float(c["intentions"])
                acc[c["candidat"]].append((w, v, poll.get("institut"), d, c.get("parti")))

    seuil = MIN_POLLS if min_polls is None else min_polls
    rows = []
    somme_exacte = 0.0   # somme des moyennes NON arrondies (voir total_intentions plus bas)
    for name, vals in acc.items():
        if len(vals) < seuil:
            continue
        sw = sum(v[0] for v in vals)
        mean = sum(w * x for w, x, *_ in vals) / sw
        somme_exacte += mean
        var = sum(w * (x - mean) ** 2 for w, x, *_ in vals) / sw
        n_eff = (sw ** 2) / sum(w ** 2 for w, *_ in vals)
        half = 1.96 * math.sqrt(var) / math.sqrt(n_eff) if n_eff > 1 else 0.0
        half = max(half, IC_FLOOR)  # plancher : anti-fausse précision
        xs = [x for _, x, *_ in vals]
        rows.append(dict(
            candidat=name, parti=vals[-1][4], intentions=round(mean, 1),
            bas=round(max(0.0, mean - half), 1), haut=round(mean + half, 1),
            mini=round(min(xs), 1), maxi=round(max(xs), 1), amplitude=round(max(xs) - min(xs), 1),
            n=len(vals), neff=round(n_eff, 1), dernier=max(v[3] for v in vals).isoformat(),
            instituts=sorted({v[2] for v in vals if v[2]}),
        ))
    rows.sort(key=lambda r: -r["intentions"])

    inst = sorted({p.get("institut") for p, _, _ in scen_recent if p.get("institut")})
    return dict(
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_polls_all=len(polls),
        polls_in_window=len([1 for _, age, _ in r1 if age <= swin]),
        scenario=scenario,
        scenario_sign=sorted(scen_sign),
        scenario_size=len(scen_sign),
        polls_in_scenario=len(scen_recent),
        polls_aggregated=len(scen_polls),
        imports=sum(1 for p, _a, _d in scen_polls if p.get("poll_id") in IDS_IMPORTES),
        window=SCENARIO_WINDOW, agg_window=AGG_WINDOW, half_life=HALF_LIFE,
        min_polls=seuil, ic_floor=IC_FLOOR, weight_mode=weight_mode,
        scenario_window=swin, house_correction=bool(hcorr),
        first=f"{min(d for _, _, d in scen_polls)}",
        last=f"{max(d for _, _, d in scen_polls)}",
        instituts=inst,
        polls_detail=[dict(
            institut=p.get("institut") or "—",
            commanditaire=p.get("commanditaire") or "—",
            debut=p.get("debut_enquete") or "—", fin=p.get("fin_enquete") or "—",
            echantillon=int(p.get("echantillon") or 0),
            population=p.get("population") or "",
            marge=max([abs(float(c.get("erreur_sup") or 0)) for c in (p.get("candidats") or [])]
                      or [0]),
            fichier=p.get("filename") or "—",
            importe=p.get("poll_id") in IDS_IMPORTES)
            for p, _a, _d in sorted(scen_polls, key=lambda x: x[2], reverse=True)],
        # Somme des moyennes exactes, et non des valeurs affichées : additionner dix nombres
        # arrondis au dixième fait dériver le total (100,1 % affiché pour 100,0000 % exact), et
        # un total d'intentions de vote qui dépasse 100 % n'a pas de sens à montrer.
        total_intentions=round(somme_exacte, 1),
        rows=rows,
    )


def weekly_series(polls, weeks=8, base=None):
    """Série rétro-calculée : l'agrégation telle qu'elle aurait été produite à chaque échéance
    hebdomadaire, sur le scénario retenu aujourd'hui (lignes comparables d'un point à l'autre)."""
    base = base or aggregate(polls)
    if not base:
        return []
    sign = base["scenario_sign"]
    out = []
    for k in range(weeks, -1, -1):
        cut = TODAY - timedelta(days=7 * k)
        a = aggregate(polls, as_of=cut, scenario_sign=sign, scenario_label=base["scenario"])
        out.append(dict(date=cut.isoformat(), weeks_ago=k,
                        polls=a["polls_aggregated"] if a else 0,
                        inst=len(a["instituts"]) if a else 0,
                        rows={r["candidat"]: r for r in (a["rows"] if a else [])}))
    return out


def movements(series):
    """Écarts par candidat : aujourd'hui vs il y a 7 jours (et 28 jours à titre de contexte)."""
    if not series:
        return []
    cur = series[-1]
    p7 = series[-2] if len(series) > 1 else None
    p28 = series[-5] if len(series) > 4 else None
    out = []
    for name, r in cur["rows"].items():
        def val(pt):
            if not pt:
                return None
            rr = pt["rows"].get(name)
            return rr["intentions"] if rr else None
        v, v7, v28 = r["intentions"], val(p7), val(p28)
        ser = [pt["rows"].get(name, {}).get("intentions") for pt in series]
        nums = [x for x in ser if isinstance(x, (int, float))]
        out.append(dict(
            candidat=name, parti=r["parti"], intentions=v,
            intention7=v7, delta7=(None if v7 is None else round(v - v7, 1)),
            intention28=v28, delta28=(None if v28 is None else round(v - v28, 1)),
            serie=ser,
            mini8=(min(nums) if nums else None), maxi8=(max(nums) if nums else None),
            polls7=(p7["polls"] if p7 else 0),
        ))
    return out


def sparkline(values, w=96, h=22):
    """Mini-courbe SVG, sans JavaScript, sur les points disponibles de la série."""
    pts = [(i, v) for i, v in enumerate(values) if isinstance(v, (int, float))]
    if len(pts) < 3:
        return '<span class="muted small">—</span>'
    lo = min(v for _, v in pts)
    hi = max(v for _, v in pts)
    span = (hi - lo) or 1.0
    n = len(values)
    xy = []
    for i, v in pts:
        x = 4 + (w - 8) * (i / (n - 1) if n > 1 else 0)
        y = h - 4 - (h - 8) * ((v - lo) / span)
        xy.append(f"{x:.1f},{y:.1f}")
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="tendance" style="vertical-align:middle">'
            f'<polyline points="{" ".join(xy)}" fill="none" stroke="#d73d2f" stroke-width="1.6"/>'
            f'<circle cx="{xy[-1].split(",")[0]}" cy="{xy[-1].split(",")[1]}" r="2.4" fill="#d73d2f"/></svg>')


def save_history(agg):
    """Archive quotidienne (une ligne par jour) : la mémoire réelle du projet, réécrite sans doublon."""
    os.makedirs(DATA, exist_ok=True)
    f = os.path.join(DATA, "history.jsonl")
    lines = []
    if os.path.exists(f):
        for ln in open(f, encoding="utf-8"):
            ln = ln.strip()
            if ln:
                try:
                    lines.append(json.loads(ln))
                except Exception:
                    pass
    today = TODAY.isoformat()
    lines = [l for l in lines if l.get("date") != today]
    lines.append(dict(date=today, scenario=agg["scenario"], polls=agg["polls_aggregated"],
                      rows=[dict(candidat=r["candidat"], intentions=r["intentions"],
                                 bas=r["bas"], haut=r["haut"]) for r in agg["rows"]]))
    lines.sort(key=lambda l: l["date"])
    with open(f, "w", encoding="utf-8") as fh:
        for l in lines:
            fh.write(json.dumps(l, ensure_ascii=False) + "\n")
    return len(lines)


# ---------- rendu ----------
CSS = """
:root{--bg:#f3efe5;--paper:#fffdf8;--ink:#171713;--muted:#676459;--line:#d9d2c3;
--red:#d73d2f;--red-text:#c53325;--green:#166b4e;--amber:#a05a0d;--blue:#245d8c;
/* ajoutées pour le thème sombre : les valeurs claires restent la référence */
--track:#efe9dc;--topbar:rgba(248,244,234,.86);--bg-top:#f8f4ea;--excl-bg:#fff9ec}
*{box-sizing:border-box}
body{margin:0;background-color:var(--bg);
background-image:linear-gradient(180deg,var(--bg-top) 0%,var(--bg) 100%);color:var(--ink);
font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.55}
a{color:var(--red-text)}
.wrap{width:min(1080px,calc(100% - 40px));margin:0 auto}
.topbar{border-bottom:1px solid var(--line);background:var(--topbar);position:sticky;top:0;z-index:10}
.nav{min-height:62px;display:flex;align-items:center;justify-content:space-between;gap:18px}
.brand{font-weight:850;letter-spacing:-.04em}
.brand span{color:var(--red-text)}
.navlinks{display:flex;gap:20px;font-size:.88rem;color:var(--muted);flex-wrap:wrap}
/* Mesure de lecture : au-delà d'environ 72 signes, l'œil perd la ligne suivante.
   Mesuré avant correction : 88 signes par ligne à 768 px comme à 1280 px. */
main p, main li, .card > p, .card > ul > li, header p, footer p{max-width:36em}
.navlinks a{white-space:nowrap}
@media(max-width:760px){
  /* En-tête : une seule ligne qui défile, au lieu de sept lignes empilées
     (mesuré avant correction : 147 à 189 px de hauteur, soit un tiers de l'écran). */
  .nav{min-height:auto;flex-wrap:wrap;gap:4px;padding:10px 0 6px;position:relative}
  .themebtn{position:absolute;right:0;top:8px}
  .brand{width:100%}
  .navlinks{flex-wrap:nowrap;overflow-x:auto;width:100%;gap:16px;padding-bottom:4px;
    scrollbar-width:none;-webkit-overflow-scrolling:touch;
    /* le dernier lien s'estompe : on comprend que la barre défile */
    -webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 26px),transparent);
    mask-image:linear-gradient(90deg,#000 calc(100% - 26px),transparent)}
  .navlinks::-webkit-scrollbar{display:none}
}
@media(max-width:899px){
  /* Grand tableau dans une carte défilante : la première colonne reste visible,
     sinon on ne sait plus quelle ligne on lit. */
  .card table td:first-child, .card table th:first-child{position:sticky;left:0;
    background:var(--paper);z-index:1}
  .card table th:first-child{z-index:3}
}
.navlinks a{text-decoration:none;color:inherit}
.themebtn{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;
  border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--muted);
  font-size:.86rem;line-height:1;cursor:pointer;flex:0 0 auto}
.themebtn:hover{color:var(--ink);border-color:var(--muted)}
/* Sélecteur de langue : deux liens, la langue courante marquée. Pas de JavaScript —
   chaque version a sa propre adresse, un lien suffit à changer de langue. */
/* Sélecteur FR/EN : même dessin que celui du site (Header.tsx) — pastille arrondie,
   filet fin, libellé actif en rouge, séparateur vertical. Adapté aux jetons de
   l'observatoire, qui a ses propres variables et deux thèmes. */
.langsw{display:inline-flex;align-items:center;gap:.375rem;margin-left:10px;
  font-size:.75rem;font-weight:600;border:1px solid var(--line);border-radius:999px;
  padding:.25rem .625rem}
.langsw a{color:var(--muted);text-decoration:none}
.langsw a:hover{color:var(--ink)}
.langsw a[aria-current="true"]{color:var(--red-text)}
.langsw .sep{color:var(--muted);opacity:.35}
.langsw .absente{color:var(--muted);opacity:.45;cursor:not-allowed}
header{padding:56px 0 24px}
.eyebrow{display:inline-block;font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;
color:var(--red-text);border:1px solid var(--red);border-radius:999px;padding:4px 12px}
h1{font-size:clamp(1.7rem,4vw,2.6rem);line-height:1.12;letter-spacing:-.03em;margin:18px 0 10px}
.lede{font-size:1.02rem;color:var(--muted);max-width:36em}
.card{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:26px;
box-shadow:0 18px 50px rgba(45,39,28,.07);margin:22px 0}
.grid{display:grid;gap:18px}
@media(min-width:820px){.grid.cols{grid-template-columns:1.15fr .85fr}}
.kpi{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.kpi .big{font-size:clamp(2.6rem,7vw,4rem);font-weight:850;letter-spacing:-.05em;line-height:1}
.kpi .unit{font-size:1.3rem;font-weight:700;color:var(--muted)}
.duo{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));margin-top:18px}
.duo .slot{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.duo .slot .tag{display:block;font-size:.68rem;text-transform:uppercase;letter-spacing:.09em;color:var(--muted)}
.duo .slot b{display:block;font-size:1.05rem;color:var(--ink);margin:4px 0 2px}
.duo .slot b{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.duo .slot .sc{white-space:nowrap}
.blrow{display:flex;justify-content:space-between;gap:10px;align-items:baseline;font-size:.88rem}
.bl-name{white-space:nowrap}
.bl-val{white-space:nowrap;text-align:right}
@media(max-width:620px){
  /* Mesuré avant correction : les noms se coupaient au milieu (« Marine Le / Pen ») et les
     intervalles se détachaient de leur score. Le libellé passe au-dessus de sa valeur. */
  .blrow{flex-wrap:wrap;gap:1px}
  .bl-name{flex:1 1 100%}
  .bl-val{flex:1 1 100%;text-align:left}
}
.duo .slot i{font-style:normal;font-weight:700;color:var(--red-text)}
.mets{display:grid;gap:16px 24px;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));margin-top:16px}
.mets .met span{display:block;font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.mets .met b{font-size:1.02rem;color:var(--ink);font-weight:650}
.mets .met{min-width:0}
.mets .met.wide{grid-column:span 2}
@media(max-width:899px){.mets .met.wide{grid-column:auto}
  /* Mobile : chaque carte devient son propre conteneur défilant, pour qu'un tableau large
     ne fasse plus déborder toute la page (mesuré : +390 px de débordement avant). */
  .card{overflow-x:auto}}
@media(max-width:899px){
  /* Huit colonnes ne tiennent pas sur un téléphone : chaque candidat devient une fiche.
     Mesuré avant correction : 732 px de tableau pour 348 px disponibles. */
  table.data{display:block}
  table.data tbody{display:block}
  table.data tr{display:block;background:var(--paper);border:1px solid var(--line);
    border-radius:12px;padding:10px 14px;margin-bottom:12px}
  table.data tr:first-child{display:none}
  table.data td{display:grid;grid-template-columns:112px 1fr;gap:10px;align-items:baseline;
    padding:4px 0;border-bottom:0;text-align:left}
  table.data td::before{content:attr(data-label);font-size:.68rem;letter-spacing:.07em;
    text-transform:uppercase;color:var(--muted)}
  table.data td:first-child{grid-template-columns:1fr;margin-bottom:2px}
  table.data td:first-child::before{display:none}
  table.data td:first-child{font-weight:600;font-size:1.02rem;color:var(--ink)}
}

ul.liste2{columns:2 300px;column-gap:28px;margin:8px 0 0;padding-left:18px}
ul.liste2 li{break-inside:avoid;margin-bottom:6px}
.pill{display:inline-block;font-size:.74rem;padding:3px 10px;border-radius:999px;border:1px solid var(--line);
color:var(--muted);background:color-mix(in srgb, currentColor 9%, var(--paper))}
.pill.g{color:var(--green);border-color:#bfd8cb}
.pill.a{color:var(--amber);border-color:color-mix(in srgb, var(--amber) 45%, var(--paper))}
.pill.b{color:var(--blue);border-color:color-mix(in srgb, var(--blue) 45%, var(--paper))}
h2{font-size:1.3rem;letter-spacing:-.02em;margin:0 0 12px}
h3{font-size:1rem;margin:20px 0 8px}
.bar{position:relative;height:26px;border-radius:6px;background:var(--track);overflow:hidden;display:flex;align-items:center}
.bar i{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,var(--red),#e2695c)}
.bar span{position:relative;padding-left:10px;font-size:.82rem;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:middle}
th{font-size:.76rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
th.num{text-align:right;letter-spacing:normal}
.muted{color:var(--muted)}
.small{font-size:.85rem}
.maj{border-left:3px solid var(--line);padding:2px 0 2px 14px;margin:16px 0 0}
.maj-t{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.maj-t strong{font-size:.95rem;color:var(--ink)}
.maj-n{font-size:.66rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);
  border:1px solid var(--line);border-radius:999px;padding:2px 0;min-width:76px;text-align:center;white-space:nowrap}
.excl{border-left:3px solid var(--amber);background:var(--excl-bg);padding:12px 14px;border-radius:0 10px 10px 0}
footer{padding:34px 0 60px;color:var(--muted);font-size:.84rem;text-align:right}
code{background:var(--track);padding:1px 5px;border-radius:5px;font-size:.86em}
/* --- landing --- */
.hero{padding:64px 0 26px}
.hero h1{font-size:clamp(2rem,5vw,3.4rem);max-width:22ch}
.hero p.lede{font-size:1.12rem;max-width:34em}
.cta{display:flex;gap:14px;flex-wrap:wrap;margin-top:26px}
.btn{display:inline-block;background:var(--red);color:#fff;text-decoration:none;font-weight:700;
padding:13px 22px;border-radius:10px}
.btn:hover{background:#bb3125}
.btn2{display:inline-block;border:1px solid var(--line);color:var(--ink);text-decoration:none;
font-weight:600;padding:13px 20px;border-radius:10px;background:var(--paper)}
.statgrid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin:34px 0 6px}
.stat{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.stat b{display:block;font-size:1.7rem;letter-spacing:-.03em;line-height:1.1}
.stat span{font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.cards{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));margin-top:8px}
.card2{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:20px}
.card2 h3{margin:0 0 8px;font-size:1rem}
.card2 p{margin:0;font-size:.9rem;color:var(--muted)}
.two{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
.ok{color:var(--green)}.ko{color:var(--red-text)}
.up{font-weight:700}.down{font-weight:700}
ul.tight{margin:8px 0 0;padding-left:18px;font-size:.92rem}
ul.tight li{margin:5px 0}
.steps{counter-reset:s;margin:10px 0 0;padding:0;list-style:none}
.steps li{counter-increment:s;position:relative;padding:0 0 14px 44px;font-size:.94rem}
.steps li::before{content:counter(s);position:absolute;left:0;top:-2px;width:30px;height:30px;
border-radius:50%;background:#1d1c17;color:#fff;font-weight:800;display:flex;align-items:center;
justify-content:center;font-size:.9rem}
<!-- Chrono countdown glassmorphism -->
.chrono-glass{text-align:center;padding:18px 14px;margin:14px 0;border-radius:18px;
  background:rgba(255,253,248,.75);border:1px solid rgba(217,210,195,.5);
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 2px 8px rgba(0,0,0,.04)}
.chrono-glass-label{font-size:.82rem;font-weight:600;color:var(--muted);text-transform:uppercase;
  letter-spacing:.04em;margin-bottom:6px;display:block}
.chrono-glass-units{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.chrono-unit{display:flex;flex-direction:column;align-items:center;min-width:64px}
.chrono-num{font-size:1.7rem;font-weight:700;line-height:1.1;color:var(--ink);
  font-variant-numeric:tabular-nums;font-family:'Space Grotesk','JetBrains Mono',monospace}
.chrono-lab{font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.chrono-glass-foot{display:block;margin-top:4px;font-size:.82rem;color:var(--muted)}
html[data-theme="dark"] .chrono-glass{background:rgba(17,24,58,.75);
  border-color:rgba(47,53,80,.5)}
html[data-theme="dark"] .chrono-num{color:#edf0f8}

footer{border-top:1px solid var(--line)}
"""

DARK = """
/* Thème sombre : mêmes noms de variables, valeurs de la palette du site
   (deep-900 #0A1024, deep-800 #11183A, accent-red #C0362C éclairci pour rester lisible).
   Contrastes mesurés sur la carte #11183A : texte 15,2 · atténué 6,9 · rouge 4,8 · vert 7,6 · ambre 7,5. */
html[data-theme="dark"]{
  --bg:#0a1024;--paper:#11183a;--ink:#edf0f8;--muted:#9ba4b8;--line:#2f3550;
  --red:#e4584c;--red-text:#e4584c;--green:#4fbf95;--amber:#c8a84e;--blue:#6fa8dc;
  --track:#1e2747;--topbar:rgba(17,24,58,.9);--bg-top:#0d1430;--excl-bg:#2a2415;
}
/* Les pastilles de famille sont des couleurs de données, plus foncées que le fond sombre. */
html[data-theme="dark"] .chip .dot{filter:brightness(1.5) saturate(1.05)}
html[data-theme="dark"] .p-declare{color:#f0a79f;border-color:#6b3a36;background:#2a1a18}
html[data-theme="dark"] .p-conditionnel{color:#e0c179;border-color:#5c4a1f;background:#2a2415}
html[data-theme="dark"] .p-suspens{color:#b6bdc9;border-color:#3a4257;background:#1b2135}
html[data-theme="dark"] .p-retire{color:#98a0b3;border-color:#333b52;background:#171d31}
html[data-theme="dark"] .p-soutien{color:#9dc0e8;border-color:#2f4a6b;background:#141d2e}
html[data-theme="dark"] tr.retiree td{color:#98a0b3}
html[data-theme="dark"] table.cand tbody tr:hover{background:rgba(228,88,76,.10)}
html[data-theme="dark"] .pb .up{color:#4fbf95}
html[data-theme="dark"] .pb .down{color:#e4584c}
html[data-theme="dark"] .note-legale{background:var(--paper)}
/* blanc sur #e4584c ne donne que 3,6:1 : le bouton plein garde le rouge du site */
html[data-theme="dark"] .btn{background:#c0362c}
"""

# Seul JavaScript de l'observatoire : le sélecteur de thème. Aucune dépendance, aucune requête.
# 1) avant le premier rendu, pour éviter le flash ; 2) au clic, et la préférence est mémorisée
#    dans la même clé que le site (« theme »), pour que le choix suive d'une page à l'autre.
# Suivi d'erreurs — GlitchTip auto-hébergé, projet « Diléviathan ».
# Client @sentry/browser (MIT) servi par notre domaine (/observatoire/vendor/) : aucun appel
# vers sentry.io. La clé du DSN s'écrit SANS tirets, sinon le SDK la refuse.
GLITCH_HEAD = (
    '<script src="/observatoire/vendor/sentry-10.38.0.min.js" defer></script>'
    '<script src="/observatoire/vendor/glitchtip-init.js" defer></script>'
)

THEME_HEAD = """<script>(function(){try{var c=localStorage.getItem("theme");
if(c==="dark"||(!c&&window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches))
{document.documentElement.setAttribute("data-theme","dark");}}catch(e){}})();</script>""" + GLITCH_HEAD

THEME_BTN = """<button type="button" class="themebtn" id="themebtn" aria-label="Changer le thème"
  title="Passer en mode clair ou sombre">&#9681;</button>"""

# Lien vers la page « Workflow » (annexe technique : comment le site se fabrique).
# Défini une seule fois ici, utilisé par les quatre pages — un seul endroit à corriger.
def nav_workflow(lang="fr"):
    return f'<a href="{lien_page("/workflow/", lang)}">Workflow</a>'


def nav_lois(lang="fr"):
    return f'<a href="{lien_page("/lois/", lang)}">{"Legislative watch" if lang == "en" else "Veille législative"}</a>'

# Adresses par langue. L'anglais vit sous /en/observatoire/, cohérent avec /en/veille
# et /en/blog du site : un seul endroit pour l'anglais, et un lien direct entre les
# deux versions de chaque page.
BASE_LANGUE = {"fr": "/observatoire", "en": "/en/observatoire"}

# Pages qui existent réellement en anglais. Tant qu'une page n'y figure pas, le menu
# anglais renvoie vers sa version française : un lien mort serait pire qu'un lien
# vers une page lisible dans une autre langue.
PAGES_EN = {"/", "/sondages/"}


def lien(chemin, lang="fr"):
    """Adresse d'une page de l'observatoire dans la langue demandée.

    `chemin` est relatif à la racine de l'observatoire (« / », « /sondages/ »).
    """
    base = BASE_LANGUE.get(lang, BASE_LANGUE["fr"])
    return base + chemin


def lien_page(chemin, lang="fr"):
    """Adresse d'une page : en anglais seulement si la traduction existe, sinon français."""
    if lang == "en" and chemin not in PAGES_EN:
        return lien(chemin, "fr")
    return lien(chemin, lang)


def nav_lien(chemin, texte_fr, texte_en, lang="fr"):
    return f'<a href="{lien(chemin, lang)}">{texte_en if lang == "en" else texte_fr}</a>'


def toggle_langue(chemin, lang="fr", en_pret=False):
    """Sélecteur FR/EN : la langue courante est marquée, l'autre est le lien.

    Tant qu'une page n'existe pas en anglais, le libellé EN n'est pas un lien :
    un sélecteur qui mène à une 404 est pire que pas de sélecteur. Il annonce ce
    qu'il ne peut pas encore faire.
    """
    morceaux = []
    for i, (code, libelle) in enumerate((("fr", "FR"), ("en", "EN"))):
        if i:
            morceaux.append('<span class="sep" aria-hidden="true">|</span>')
        if code == lang:
            morceaux.append(f'<a href="{lien(chemin, code)}" hreflang="{code}" aria-current="true">{libelle}</a>')
        elif code == "en" and not en_pret:
            morceaux.append('<span class="absente" aria-disabled="true" title="'
                            + ("Version anglaise en préparation" if lang == "fr" else "English version in preparation")
                            + '">EN</span>')
        else:
            morceaux.append(f'<a href="{lien(chemin, code)}" hreflang="{code}">{libelle}</a>')
    return ('<span class="langsw" role="group" aria-label="'
            + ("Langue" if lang == "fr" else "Language") + '">' + "".join(morceaux) + "</span>")

THEME_JS = """<script>(function(){var b=document.getElementById("themebtn");if(!b)return;
b.addEventListener("click",function(){var r=document.documentElement;
var sombre=r.getAttribute("data-theme")==="dark";
if(sombre){r.removeAttribute("data-theme");}else{r.setAttribute("data-theme","dark");}
try{localStorage.setItem("theme",sombre?"light":"dark");}catch(e){}
b.setAttribute("title",sombre?"Passer en mode sombre":"Passer en mode clair");});})();</script>"""

CHRONO_JS = """<script>(function(){var e=document.querySelectorAll(".chrono-num,.chrono");if(!e.length)return;
function pad(n){return n<10?"0"+n:""+n}
function tick(){e.forEach(function(el){
var t=el.getAttribute("data-target");if(!t)return;
var d=Date.parse(t)-Date.now();if(d<0){el.textContent="—";return}
var s=Math.floor(d/1000);var m=Math.floor(s/60);var hh=Math.floor(m/60);var dd=Math.floor(hh/24);
var unit=el.getAttribute("data-unit");
if(unit==="d")el.textContent=dd;
else if(unit==="h")el.textContent=pad(hh%24);
else if(unit==="m")el.textContent=pad(m%60);
else if(unit==="s")el.textContent=pad(s%60);
else el.textContent="J-"+dd;});
} tick(); setInterval(tick,1000);})();</script>"""



from contenu import a_lire_bloc, changelog_bloc   # textes rédigés (content/observatoire.json)


def frnum(x):
    """Nombre avec séparateurs de milliers (espace fine insécable)."""
    try:
        return f"{int(x):,}".replace(",", "\u202f")
    except Exception:
        return "—"


def fr1u(x):
    """Niveau (sans signe), une décimale, virgule française."""
    if x is None:
        return "—"
    return f"{x:.1f}".replace(".", ",")


def fr1(x):
    """Une décimale, virgule française, signe typographique : pour les colonnes de tableau."""
    if x is None:
        return "—"
    return (("+" if x > 0 else "−" if x < 0 else "") + f"{abs(x):.1f}").replace(".", ",")


def dcell(d):
    """Cellule de variation : ▲/▼ au-delà de 1 point, gris en deçà (marge)."""
    if d is None:
        return '<span class="muted">—</span>'
    if abs(d) < 1.0:
        return f'<span class="muted">{fr1(d)}</span>'
    arrow = "▲" if d > 0 else "▼"
    return f'<span class="{"up" if d > 0 else "down"}">{arrow} {f"{abs(d):.1f}".replace(".", ",")}</span>'


def mov_table(movs, lang="fr"):
    """Tableau par candidat : aujourd'hui, il y a 7 jours, il y a 28 jours, tendance."""
    tr = (lambda a, b: b) if lang == "en" else (lambda a, b: a)
    if not movs:
        return '<p class="small muted">' + tr("Série indisponible (pas assez de sondages publiés).",
                                             "Series unavailable (not enough published polls).") + '</p>'
    body = "\n".join(
        f'<tr><td>{m["candidat"]} <span class="muted small">{m["parti"] or ""}</span></td>'
        f'<td class="num"><strong>{fr1u(m["intentions"])}</strong></td>'
        f'<td class="num muted">{fr1u(m["intention7"])}</td>'
        f'<td class="num">{dcell(m["delta7"])}</td>'
        f'<td class="num muted">{fr1u(m["intention28"])}</td>'
        f'<td class="num">{dcell(m["delta28"])}</td>'
        f'<td class="num muted small">'
        f'{"—" if m["mini8"] is None else fr1u(m["mini8"]) + " – " + fr1u(m["maxi8"])}</td>'
        f'<td>{sparkline(m["serie"])}</td></tr>'
        for m in movs)
    return ('<table style="margin-top:10px"><tr><th>' + tr("Candidat", "Candidate") + '</th>'
            '<th class="num">' + tr("Aujourd'hui", "Today") + '</th><th class="num">'
            + tr("Il y a 7 j", "7 days ago") + '</th><th class="num">Δ 7 j</th>'
            '<th class="num">' + tr("Il y a 28 j", "28 days ago") + '</th><th class="num">Δ 28 j</th>'
            '<th class="num">' + tr("8 sem. (min–max)", "8 wks (min–max)") + '</th><th>'
            + tr("8 semaines", "8 weeks") + '</th></tr>'
            + body + '</table>')


def _fiches_candidats():
    """Fiches de data/candidats2027.json (nom, parti, statut, date_declaration…). Vide si illisible."""
    try:
        with open(os.path.join(DATA, "candidats2027.json"), encoding="utf-8") as f:
            return (json.load(f) or {}).get("candidats") or []
    except Exception:
        return []


def hors_scenario(movs, trends, maxi=6, lang="fr"):
    """Les candidats **déclarés** que le tableau du scénario ne peut pas montrer.

    Le tableau « semaine par semaine » suit la liste de noms retenue : un candidat absent de cette
    liste n'y apparaît pas, même suivi depuis des mois. La ligne existe pour qu'une absence de tableau
    ne se lise pas comme un effacement — mais elle ne garde que les candidatures déclarées, recoupées
    avec data/candidats2027.json (statut « declare ») : un nom testé par les instituts n'est pas pour
    autant une candidature. Les valeurs viennent de l'indicateur toutes listes.
    """
    fiches = _fiches_candidats()
    dedans = {m["candidat"] for m in movs}
    absents = [t for t in trends if t["candidat"] not in dedans
               and ((_match_forecast(t["candidat"], fiches) or {}).get("statut") == "declare")]
    if not absents:
        return ""
    montres = " · ".join(f'{t["candidat"]} <strong>{fr1u(t["intentions"])}</strong>' for t in absents[:maxi])
    reste = len(absents) - maxi
    if reste > 0:
        montres += f" et {reste} autre{'s' if reste > 1 else ''}"
    if lang == "en":
        suite = ("These names are not tested in the list used by the most recent questionnaires: "
                 "their tracking is the one in the \u201call lists\u201d table below." if len(absents) > 1 else
                 "It is not tested in the list used by the most recent questionnaires: "
                 "its tracking is the one in the \u201call lists\u201d table below.")
        titre = "Outside the scenario today, among declared candidates:"
    else:
        suite = ("Ces noms ne sont pas testés dans la liste retenue par les questionnaires les plus récents : "
                 "leur suivi est celui du tableau « toutes listes » ci-dessous." if len(absents) > 1 else
                 "Il n'est pas testé dans la liste retenue par les questionnaires les plus récents : "
                 "son suivi est celui du tableau « toutes listes » ci-dessous.")
        titre = "Hors scénario aujourd'hui, parmi les candidats déclarés :"
    return ('<p class="small" style="max-width:none;margin-top:12px">'
            f'<strong>{titre}</strong> {montres}. {suite}</p>')


def mov_line(movs, lang="fr"):
    def pick(field):
        return sorted([m for m in movs if isinstance(m[field], (int, float)) and abs(m[field]) >= 1.0],
                      key=lambda m: -abs(m[field]))

    def fmt(m, field):
        d = m[field]
        return f'{m["candidat"]} {"+" if d > 0 else "−"}{fr1u(abs(d))} pt'

    big7 = pick("delta7")
    if big7:
        return " · ".join(fmt(m, "delta7") for m in big7[:4]) + (" (over 7 days)" if lang == "en" else " (sur 7 jours)")
    big28 = pick("delta28")
    if big28:
        return (("nothing beyond 1 point over 7 days; over 28 days: " if lang == "en"
                 else "rien au-delà de 1 point sur 7 jours ; sur 28 jours : ")
                + " · ".join(fmt(m, "delta28") for m in big28[:3]))
    return ("no gap above 1 point over 7 or 28 days (all within the margin)" if lang == "en"
            else "aucun écart supérieur à 1 point sur 7 ou 28 jours (tous dans la marge)")


def fr(x, lang="fr"):
    """Formatage du nombre : virgule décimale en français, point en anglais, sans ',0' inutile."""
    s = f"{x:.1f}" if isinstance(x, float) else str(x)
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return s if lang == "en" else s.replace(".", ",")


def trend_point(polls, as_of, min_polls=3):
    """Moyenne pondérée par candidat, TOUTES hypothèses confondues : indicateur de tendance.
    Le niveau n'est pas comparable au tableau principal (chaque sondage teste une liste différente) ;
    seule la direction est informative."""
    acc = defaultdict(list)
    for p in polls:
        if (p.get("tour") or "") != "1er Tour":
            continue
        d = parse_date(p.get("fin_enquete") or "")
        if not d or d > as_of:
            continue
        age = (as_of - d).days
        if age > AGG_WINDOW:
            continue
        w = math.exp(-math.log(2) * age / HALF_LIFE) * math.sqrt((p.get("echantillon") or 1000) / 1000.0)
        for c in p.get("candidats", []):
            if isinstance(c.get("intentions"), (int, float)):
                acc[c["candidat"]].append((w, float(c["intentions"]), c.get("parti")))
    out = {}
    for name, vals in acc.items():
        if len(vals) < min_polls:
            continue
        sw = sum(v[0] for v in vals)
        out[name] = dict(candidat=name, parti=vals[-1][2], n=len(vals),
                         intentions=round(sum(w * x for w, x, *_ in vals) / sw, 1))
    return out


def trend_movements(polls, weeks=8, keep=12):
    """Écarts hebdomadaires de l'indicateur toutes listes (les niveaux ne sont pas comparables)."""
    pts = [(TODAY - timedelta(days=7 * k), None) for k in range(weeks, -1, -1)]
    pts = [(d, trend_point(polls, d)) for d, _ in pts]
    cur, p7, p28 = pts[-1][1], pts[-2][1], pts[-5][1]
    rows = []
    for name, r in sorted(cur.items(), key=lambda kv: -kv[1]["intentions"]):
        v7 = p7.get(name, {}).get("intentions")
        v28 = p28.get(name, {}).get("intentions")
        rows.append(dict(candidat=name, parti=r["parti"], intentions=r["intentions"], n=r["n"],
                         intention7=v7, delta7=(None if v7 is None else round(r["intentions"] - v7, 1)),
                         intention28=v28, delta28=(None if v28 is None else round(r["intentions"] - v28, 1)),
                         serie=[pt[1].get(name, {}).get("intentions") for pt in pts]))
    return rows[:keep]


def trend_table(rows, lang="fr"):
    tr = (lambda a, b: b) if lang == "en" else (lambda a, b: a)
    if not rows:
        return '<p class="small muted">' + tr("Indicateur indisponible.", "Indicator unavailable.") + '</p>'
    body = "\n".join(
        f'<tr><td>{m["candidat"]} <span class="muted small">{m["parti"] or ""}</span></td>'
        f'<td class="num"><strong>{fr1u(m["intentions"])}</strong></td>'
        f'<td class="num muted">{fr1u(m["intention7"])}</td>'
        f'<td class="num">{dcell(m["delta7"])}</td>'
        f'<td class="num muted">{fr1u(m["intention28"])}</td>'
        f'<td class="num">{dcell(m["delta28"])}</td>'
        f'<td class="num muted small">{m["n"]}</td>'
        f'<td>{sparkline(m["serie"])}</td></tr>'
        for m in rows)
    return ('<table style="margin-top:10px"><tr><th>' + tr("Candidat", "Candidate") + '</th>'
            '<th class="num">' + tr("Toutes listes", "All lists") + '</th><th class="num">'
            + tr("Il y a 7 j", "7 days ago") + '</th><th class="num">Δ 7 j</th>'
            '<th class="num">' + tr("Il y a 28 j", "28 days ago") + '</th><th class="num">Δ 28 j</th>'
            '<th class="num">' + tr("Sondages", "Polls") + '</th><th>'
            + tr("8 semaines", "8 weeks") + '</th></tr>' + body + '</table>')


def render_sondages(agg, movs=None, trends=None, fc=None, lang="fr"):
    movs = movs or []
    trends = trends or []
    r0 = agg["rows"][0] if agg["rows"] else None
    rows = agg["rows"]
    VALEURS = valeurs_textes(agg, rows)
    m = (lambda a, b: b) if lang == "en" else (lambda a, b: a)

    watch = []
    if len(rows) >= 3:
        gap = round(rows[1]["intentions"] - rows[2]["intentions"], 1)
        watch.append(m(f"Écart entre le 2ᵉ et le 3ᵉ : {fr(gap, lang)} point{'s' if gap >= 1.5 else ''}.",
                       f"Gap between 2nd and 3rd: {fr(gap, lang)} point{'s' if gap >= 1.5 else ''}."))
        if rows[2]["haut"] >= rows[1]["bas"]:
            watch.append(m("Les intervalles du 2ᵉ et du 3ᵉ se recouvrent : l'écart n'est pas significatif au vu des marges.",
                           "The 2nd and 3rd intervals overlap: the gap is not significant given the margins."))
    duo = ""
    if len(rows) >= 2:
        duo = f'''<div class="duo">
      <div class="slot"><span class="tag">{m("1<sup>er</sup> tour · 1<sup>re</sup> place", "1st round · 1st place")}</span>
        <b>{rows[0]["candidat"]}</b>
        <span class="muted small">{rows[0]["parti"] or m("sans étiquette", "no label")} — <span class="sc"><i>{fr(rows[0]["intentions"])} %</i> <span class="small">[{fr(rows[0]["bas"])}–{fr(rows[0]["haut"])}]</span></span></span></div>
      <div class="slot"><span class="tag">{m("1<sup>er</sup> tour · 2<sup>e</sup> place", "1st round · 2nd place")}</span>
        <b>{rows[1]["candidat"]}</b>
        <span class="muted small">{rows[1]["parti"] or m("sans étiquette", "no label")} — <span class="sc"><i>{fr(rows[1]["intentions"])} %</i> <span class="small">[{fr(rows[1]["bas"])}–{fr(rows[1]["haut"])}]</span></span></span></div>
    </div>
    <p class="small muted" style="margin-top:10px"><strong>{m("Second tour théorique", "Theoretical runoff")} : {rows[0]["candidat"]} {m("et", "and")}
    {rows[1]["candidat"]}.</strong> {m("Ce sont les deux premiers de cette moyenne — une lecture mécanique du tableau, pas une prévision. Le second tour dépend des reports de voix, de la participation et des alliances, que nous ne modélisons pas : aucun chiffre de cette page ne dit qui le remporterait.",
    "These are the top two in this average — a mechanical reading of the table, not a forecast. A runoff depends on vote transfers, turnout and alliances, which we do not model: no figure on this page says who would win it.")}</p>'''

    maxv = max((r["intentions"] for r in rows), default=1)
    bars = "\n".join(
        f'<div style="margin:10px 0"><div class="blrow">'
        f'<strong class="bl-name">{r["candidat"]}</strong>'
        f'<span class="bl-val muted">{r["parti"] or ""} — {fr(r["intentions"])} % '
        f'<span class="small">[{fr(r["bas"])}–{fr(r["haut"])}]</span></span></div>'
        f'<div class="bar"><i style="width:{(r["intentions"]/maxv*100):.1f}%"></i>'
        f'<span>{fr(r["intentions"])} %</span></div></div>'
        for r in rows)
    trs = "\n".join(
        f'<tr><td data-label="{m('Candidat', 'Candidate')}">{r["candidat"]}</td>'
        f'<td class="muted small" data-label="{m('Parti', 'Party')}">{r["parti"] or ""}</td>'
        f'<td class="num" data-label="{m('Moyenne', 'Average')}"><strong>{fr(r["intentions"])}</strong></td>'
        f'<td class="num muted" data-label="{m('IC 95 %', '95% CI')}">{fr(r["bas"])} – {fr(r["haut"])}</td>'
        f'<td class="num muted" data-label="{m('Amplitude', 'Range')}">{fr(r["mini"])} – {fr(r["maxi"])}</td>'
        f'<td class="num" data-label="{m('Sondages', 'Polls')}">{r["n"]}</td>'
        f'<td class="num" data-label="{m('n effectif', 'effective n')}">{fr(r["neff"])}</td>'
        f'<td class="num muted small" data-label="{m('Dernier', 'Latest')}">{r["dernier"]}</td></tr>'
        for r in rows)

    t_h1 = m("Ce que disent les sondages de la présidentielle 2027, agrégés et sourcés",
             "What the 2027 presidential polls say, aggregated and sourced")
    t_lede = m("Un seul scénario de candidatures, une moyenne pondérée par la fraîcheur et la taille "
               "d'échantillon, un intervalle publié, et la liste de toutes les limites. Page régénérée le "
               f"{frdate(agg['generated'])} (heure de Paris).",
               "A single candidacy scenario, an average weighted by recency and sample size, a published "
               "interval, and the full list of limits. Page regenerated on "
               f"{frdate(agg['generated'], 'en')} (Paris time).")
    t_tete = m("Tête de course", "Front of the race")
    t_ic95 = m("Intervalle à 95 %", "95% interval")
    t_sondages = m("sondages", "polls")
    t_neff = m("n effectif", "effective n")
    t_lecture = m("Lecture rapide", "Quick read")
    t_pas_assez = m("Pas assez de candidats pour comparer les écarts.",
                    "Not enough candidates to compare gaps.")
    t_total = m("Total des intentions : "
                f"{fr(agg['total_intentions'], lang)} % (les intentions des candidats sous le seuil de "
                f"{agg['min_polls']} sondages ne sont pas affichées ; chaque ligne étant arrondie au "
                "dixième, leur somme peut s'en écarter de quelques dixièmes).",
                "Total of voting intentions: "
                f"{fr(agg['total_intentions'], lang)} % (intentions for candidates below the threshold of "
                f"{agg['min_polls']} polls are not shown; each line being rounded to the tenth, their sum "
                "may differ by a few tenths).")
    t_perim = m("Périmètre", "Scope")
    t_tour1 = m("Premier tour", "First round")
    t_src = m("Sondages dans la source", "Polls in the source")
    t_window = m("derniers jours", "last days")
    t_scenario = m("Scénario retenu", "Scenario used")
    t_cand = m("candidats", "candidates")
    t_scen_j = m("Sondages du scénario", "Scenario polls")
    t_agg_j = m("Sondages agrégés", "Aggregated polls")
    t_periode = m("Période couverte", "Period covered")
    t_instituts = m("Instituts", "Pollsters")
    t_moy = m("Moyennes pondérées", "Weighted averages")
    t_moy_p = m("Les barres sont proportionnelles à la moyenne. IC 95 % : incertitude statistique de la "
                "moyenne. Amplitude : minimum et maximum observés parmi les sondages agrégés — c'est la "
                "dispersion réelle entre instituts, souvent plus parlante que l'intervalle.",
                "Bars are proportional to the average. 95% CI: statistical uncertainty of the average. "
                "Range: minimum and maximum observed among the aggregated polls — the real dispersion "
                "between pollsters, often more telling than the interval.")
    t_evol = m(f"Évolution, semaine par semaine — scénario {agg['scenario']} ({agg['scenario_size']} noms)",
               f"Week-by-week trend — scenario {agg['scenario']} ({agg['scenario_size']} names)")
    t_evol_p = m("Série rétro-calculée : la méthode actuelle appliquée aux sondages publiés à chaque "
                 "échéance hebdomadaire — c'est ce que cette page aurait affiché, pas ce qu'elle "
                 f"affichait. Le scénario est verrouillé sur {agg['scenario']} pour que les lignes restent "
                 "comparables. Un nom absent de cette liste ne disparaît pas de la page : la ligne "
                 "« hors scénario » et le tableau « toutes listes » ci-dessous le suivent. Un écart "
                 "inférieur à 1 point reste dans la marge : nous ne le commentons pas.",
                 "Back-computed series: the current method applied to the polls published at each weekly "
                 "deadline — what this page would have shown, not what it did show. The scenario is "
                 f"locked on {agg['scenario']} so that lines stay comparable. A name missing from this "
                 "list does not vanish from the page: the “outside the scenario” line and the "
                 "“all lists” table below follow it. A gap below 1 point stays within the margin: "
                 "we do not comment on it.")
    t_mov7 = m("Mouvements sur 7 jours :", "Movements over 7 days:")
    t_tendance = m("Tendance, toutes listes confondues", "Trend, all lists combined")
    t_meth_1 = m("Chaque sondage reçoit un poids : <code>w = exp(−ln2 × âge / demi-vie) × √(échantillon / 1000)</code>, "
                 f"avec une demi-vie de {agg['half_life']} jours. La moyenne publiée est la moyenne pondérée ; "
                 "l'intervalle à 95 % vaut <code>1,96 × σ<sub>pondéré</sub> / √n<sub>eff</sub></code>, avec "
                 "<code>n_eff = (Σw)² / Σw²</code> — et il est plancheré à "
                 f"±{fr(agg['ic_floor'], lang)} point, parce qu'un intervalle calculé sur peu de sondages "
                 "donnerait une fausse précision.",
                 "Each poll is given a weight: <code>w = exp(−ln2 × age / half-life) × √(sample / 1000)</code>, "
                 f"with a half-life of {agg['half_life']} days. The published average is the weighted mean; "
                 "the 95% interval is <code>1.96 × σ<sub>weighted</sub> / √n<sub>eff</sub></code>, with "
                 "<code>n_eff = (Σw)² / Σw²</code> — and it is floored at "
                 f"±{fr(agg['ic_floor'], lang)} point, because an interval computed from few polls would "
                 "give false precision.")
    t_meth_2 = m("<strong>Deux fenêtres, pour une raison.</strong> Le <em>scénario</em> est choisi sur les "
                 f"{agg['window']} derniers jours : la liste testée le plus récemment parmi celles qui "
                 f"comptent au moins {agg['min_polls']} enquêtes — c'est elle qui doit être à jour, puisque "
                 "les listes de candidats bougent. Les <em>moyennes</em> sont ensuite calculées sur tous les "
                 f"sondages de ce même scénario dans les {agg['agg_window']} derniers jours "
                 f"({agg['polls_aggregated']} sondages), pondérés par la fraîcheur. Mélanger les scénarios "
                 f"produirait des chiffres faux ; n'utiliser que {agg['window']} jours produirait des "
                 "moyennes trop instables.",
                 "<strong>Two windows, for one reason.</strong> The <em>scenario</em> is chosen over the last "
                 f"{agg['window']} days: the most recently tested list among those with at least "
                 f"{agg['min_polls']} surveys — it must be current, because candidate lists move. The "
                 "<em>averages</em> are then computed over all polls of that same scenario within the last "
                 f"{agg['agg_window']} days ({agg['polls_aggregated']} polls), weighted by recency. Mixing "
                 f"scenarios would produce wrong figures; using only {agg['window']} days would produce "
                 "averages far too unstable.")
    t_meth_3 = m("<strong>Ces deux réglages ont été mesurés, pas choisis.</strong> Un "
                 "<a href=\"/observatoire/backtest/\">rétro-test complet sur la campagne 2022</a> — la même "
                 "méthode rejouée face au résultat réel — a fixé la fenêtre de sélection à "
                 f"{agg['window']} jours (la plus courte qui couvre toutes les échéances testées) et activé "
                 "la correction des effets de maison. Il montre aussi les limites de l'exercice : notre "
                 "pondération par fraîcheur n'apporte rien face à la dernière enquête seule, et les biais "
                 "collectifs des instituts subsistent.",
                 "<strong>Both settings were measured, not chosen.</strong> A "
                 "<a href=\"/en/observatoire/backtest/\">full backtest on the 2022 campaign</a> — the same "
                 "method replayed against the real result — fixed the selection window at "
                 f"{agg['window']} days (the shortest covering every deadline tested) and enabled house-effect "
                 "correction. It also shows the limits of the exercise: our recency weighting adds nothing "
                 "over the latest poll alone, and the pollsters' collective biases remain.")
    t_meth_4 = m("Données : <a href=\"https://github.com/MieuxVoter/presidentielle2027\">MieuxVoter/presidentielle2027</a> "
                 "(licence MIT), flux JSON brut, 1<sup>er</sup> tour uniquement"
                 + (" ; les enquêtes que cette compilation n'a pas encore intégrées sont extraites par nos "
                    "soins des notices de la Commission des sondages et signalées par † dans le tableau des "
                    "sondages" if agg.get("imports") else "")
                 + ". Le document est régénéré par un script, sans retouche manuelle des chiffres ; la "
                 "méthode ci-dessus est la spécification exacte du code qui produit la page.",
                 "Data: <a href=\"https://github.com/MieuxVoter/presidentielle2027\">MieuxVoter/presidentielle2027</a> "
                 "(MIT licence), raw JSON feed, first round only"
                 + (" ; the surveys this compilation has not yet integrated are extracted by us from the "
                    "notices of the Commission des sondages and flagged with † in the polls table"
                    if agg.get("imports") else "")
                 + ". The document is regenerated by a script, with no manual editing of figures; the method "
                 "above is the exact specification of the code producing the page.")
    t_lim_intro = m("<strong>Cette page n'est pas un modèle de prévision.</strong> Elle n'anticipe ni la "
                    "participation, ni les reports de voix, ni les dynamiques de campagne, et ne calcule "
                    "aucune probabilité de victoire.",
                    "<strong>This page is not a forecasting model.</strong> It anticipates neither turnout, "
                    "nor vote transfers, nor campaign dynamics, and computes no probability of victory.")
    t_lim = [
        m("<strong>Effets de maison corrigés, mais biais partagés non</strong> : l'écart moyen de chaque "
          "institut au consensus des autres est estimé puis retranché (rétro-test 2022 : gain réel mais "
          "faible). En revanche, quand <em>tous</em> les instituts se trompent ensemble — en 2022, une "
          "sous-estimation de Mélenchon de près de 14 points — aucune correction d'effet de maison ne peut "
          "rien : nous reproduisons ce biais collectif.",
          "<strong>House effects corrected, shared biases not</strong>: each pollster's average deviation "
          "from the others' consensus is estimated then removed (2022 backtest: a real but small gain). By "
          "contrast, when <em>every</em> pollster is wrong together — in 2022, an underestimation of "
          "Mélenchon by nearly 14 points — no house-effect correction can help: we reproduce that "
          "collective bias."),
        m("<strong>Marges des instituts ignorées</strong> : l'IC affiché est celui de la moyenne "
          f"(plancheré à ±{fr(agg['ic_floor'], lang)} point), plus étroit que la marge d'un sondage isolé. "
          "La colonne « amplitude » montre, elle, l'écart réel entre instituts.",
          "<strong>Pollsters' margins ignored</strong>: the displayed CI is that of the average "
          f"(floored at ±{fr(agg['ic_floor'], lang)} point), narrower than the margin of a single poll. The "
          "\u201crange\u201d column shows the real dispersion between pollsters."),
        m(f"<strong>Peu de sondages par scénario</strong> : {agg['polls_aggregated']} sondages seulement "
          "entrent dans le calcul — les listes de candidats sont encore instables à ce stade.",
          f"<strong>Few polls per scenario</strong>: only {agg['polls_aggregated']} polls enter the "
          "computation — candidate lists are still unstable at this stage."),
        m("<strong>Scénarios écartés</strong> : les sondages testant d'autres listes de candidats ne sont "
          "pas comptés.",
          "<strong>Discarded scenarios</strong>: polls testing other candidate lists are not counted."),
        m("<strong>Candidatures mouvantes</strong> : annonces, retraits et ralliements rendent toute liste "
          f"instable à {agg['window']} jours de l'élection.",
          "<strong>Shifting candidacies</strong>: announcements, withdrawals and endorsements make any list "
          f"unstable {agg['window']} days out from the election."),
        m("<strong>Ne pas confondre</strong> : une moyenne de sondages n'est pas un résultat, et une "
          "intention de vote n'est pas un vote.",
          "<strong>Do not confuse</strong>: an average of polls is not a result, and a voting intention is "
          "not a vote."),
    ]
    t_lim_bullets = "".join(f"<li>{x}</li>" for x in t_lim)
    t_tendance_p = m("Ici, chaque sondage du premier tour compte, quelle que soit la liste testée : c'est "
                     "un indicateur de direction. Les niveaux ne sont pas comparables à ceux du tableau "
                     "ci-dessus (une liste de dix candidats ne suit pas la même arithmétique qu'une liste "
                     "de quinze) — seule l'évolution compte, et elle est plus robuste car elle repose sur "
                     "beaucoup plus d'enquêtes.",
                     "Here every first-round poll counts, whatever the list tested: this is a direction "
                     "indicator. Levels are not comparable with those of the table above (a ten-candidate "
                     "list does not follow the same arithmetic as a fifteen-candidate one) — only the "
                     "movement matters, and it is more robust because it rests on far more surveys.")

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="{meta_description('/observatoire/sondages/', lang)}">
<title>{titre_court('/observatoire/sondages/', lang)}</title>
<link rel="canonical" href="https://dileviathan.fr{lien('/sondages/', lang)}">
<link rel="alternate" hreflang="fr" href="https://dileviathan.fr{lien('/sondages/', 'fr')}">
<link rel="alternate" hreflang="en" href="https://dileviathan.fr{lien('/sondages/', 'en')}">
<link rel="alternate" hreflang="x-default" href="https://dileviathan.fr{lien('/sondages/', 'fr')}">
{meta_social('/observatoire/sondages/', lang)}
{ld_json("/observatoire/sondages/", lang)}
{matomo()}
<style>{CSS}{DARK}</style>
{THEME_HEAD}</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand"><a href="{lien('/', lang)}" style="text-decoration:none">{m("Présidentielle 2027", "2027 presidential election")}</a> <span>· {m("agrégation", "aggregate")}</span></div>
  <div class="navlinks"><a href="{lien('/', lang)}">{m("Accueil", "Home")}</a><a href="{lien_page('/candidats/', lang)}">{m("Les candidats", "Candidates")}</a><a href="{lien_page('/backtest/', lang)}">{m("Rétro-test 2022", "2022 backtest")}</a>{nav_workflow(lang)}{nav_lois(lang)}<a href="#tete">{m("Tête de course", "Front of the race")}</a>
  <a href="#tableau">Tableau</a><a href="#evolution">Évolution</a>
  <a href="#comparaison">Comparaison</a><a href="#methode">Méthode</a>
  <a href="#a-lire">Citer un chiffre</a><a href="#limites">Limites</a>{toggle_langue('/sondages/', lang, en_pret=True)}</div>{THEME_BTN}
</div></div>

<header class="wrap">
  <span class="eyebrow">{m("Observatoire des sondages · présidentielle 2027", "Poll monitor · 2027 presidential election")}</span>
  <h1>{t_h1}</h1>
  <p class="lede">{t_lede}</p>
</header>

<main class="wrap">
<section id="tete" class="card">
  <div>
    <span class="pill b">{t_tete}</span>
    {"" if not r0 else f'''
    <div class="kpi" style="margin-top:14px">
      <span class="big">{fr(r0["intentions"])}</span><span class="unit">%</span>
      <span class="muted">— {r0["candidat"]} ({r0["parti"] or m("sans étiquette", "no label")})</span>
    </div>
    <p class="small muted" style="margin-top:8px">{t_ic95} : <strong>{fr(r0["bas"], lang)} – {fr(r0["haut"], lang)} %</strong>
    · {r0["n"]} {t_sondages} · {t_neff} {fr(r0["neff"], lang)}</p>'''}
    {duo}
    <h3>{t_lecture}</h3>
    <ul class="small muted liste2">
      {"".join(f"<li>{w}</li>" for w in watch) or "<li>" + t_pas_assez + "</li>"}
      <li>{t_total}</li>
    </ul>
  </div>
</section>

<section id="perimetre" class="card">
  <span class="pill a">{t_perim}</span>
  <div class="mets">
    <div class="met"><span>{t_tour1}</span><b>{frd("2027-04-18")} <span class="chrono" data-target="{f"{SCRUTIN_1}T20:00:00" if SCRUTIN_1 else ''}">—</span></b></div>
    <div class="met"><span>{t_src}</span><b>{agg["total_polls_all"]}</b></div>
    <div class="met"><span>{m("1<sup>er</sup> tour", "1st round")}, {agg["window"]} {t_window}</span><b>{agg["polls_in_window"]}</b></div>
    <div class="met"><span>{t_scenario}</span><b>{agg["scenario"]} · {agg["scenario_size"]} {t_cand}</b></div>
    <div class="met"><span>{t_scen_j}, {agg["window"]} {m("j", "d")}</span><b>{agg["polls_in_scenario"]}</b></div>
    <div class="met"><span>{t_agg_j}, {agg["agg_window"]} {m("j", "d")}</span><b>{agg["polls_aggregated"]}</b></div>
    <div class="met"><span>{t_periode}</span><b>{frd(agg["first"])} → {frd(agg["last"])}</b></div>
    <div class="met wide"><span>{t_instituts}</span><b>{", ".join(agg["instituts"])}</b></div>
  </div>
</section>

<section id="tableau" class="card">
  <h2>{t_moy}</h2>
  <p class="small muted" style="max-width:none">{t_moy_p}</p>
  {bars}
  <table class="data" style="margin-top:18px">
    <tr><th>{m("Candidat", "Candidate")}</th><th>{m("Parti", "Party")}</th><th class="num">{m("Moyenne", "Average")}</th>
    <th class="num">{m("IC 95 %", "95% CI")}</th><th class="num">{m("Amplitude", "Range")}</th>
    <th class="num">{m("Sondages", "Polls")}</th><th class="num">{m("n effectif", "effective n")}</th>
    <th class="num">{m("Dernier", "Latest")}</th></tr>
    {trs}
  </table>
</section>

<section id="evolution" class="card">
  <h2>{t_evol}</h2>
  <p class="small muted" style="max-width:none">{t_evol_p}</p>
  {mov_table(movs, lang)}
  {hors_scenario(movs, trends, lang=lang)}
  <p class="small" style="margin-top:14px"><strong>{t_mov7}</strong> {mov_line(movs, lang)}.</p>
  <h3 style="margin-top:26px">{t_tendance}</h3>
  <p class="small muted" style="max-width:none">{t_tendance_p}</p>
  {trend_table(trends, lang)}
  <p class="small" style="margin-top:14px"><strong>{m("Mouvement de fond (toutes listes) :", "Underlying movement (all lists):")}</strong>
  {mov_line(trends, lang)}.</p>
  <p class="small muted">{m("Sondages agrégés par point, de J−56 à J−0 :", "Polls aggregated per point, from D−56 to D−0:")}
  {" · ".join(str(p["polls"]) for p in agg.get("series", []))}. {m("Un tiret signale un candidat absent du scénario à cette date ; la courbe relie les points disponibles. Les premières semaines reposent sur très peu de sondages : un plateau à trois enquêtes ne démontre rien.",
    "A dash marks a candidate absent from the scenario at that date; the curve links the available points. The first weeks rest on very few polls: a plateau of three surveys proves nothing.")}</p>
</section>

<section id="comparaison" class="card">
  <h2>{m("Comparaison : l'agrégation des sondages face à une prévision bayésienne",
        "Comparison: poll aggregation against a Bayesian forecast")}</h2>
  <p class="small" style="max-width:none">{m("Un projet indépendant", "An independent project")}, <a
  href="https://github.com/whyalwaysrose/presidentielle-2027">whyalwaysrose/presidentielle-2027</a>
  {m("(licence MIT), publie une prévision bayésienne hiérarchique de la même élection, nourrie de la même source de sondages, avec le choix inverse du nôtre : il intègre l'incertitude sur la liste des candidats au lieu de verrouiller un scénario. Voici les deux côte à côte, et ce que l'écart nous apprend.",
     "(MIT licence), publishes a hierarchical Bayesian forecast of the same election, fed by the same poll source, with the opposite choice to ours: it folds the uncertainty over the candidate list into the model instead of locking a scenario. Here they are side by side, and what the gap tells us.")}</p>
  {forecast_block(agg, trends, fc, lang)}
  {backtest_block(lang)}
</section>

<section id="methode" class="card">
  <h2>{m("Méthode", "Method")}</h2>
  <p class="small">{t_meth_1}</p>
  <p class="small">{t_meth_2}</p>
  <p class="small">{t_meth_3}</p>
  <p class="small">{t_meth_4}</p>
</section>

{a_lire_bloc(VALEURS, lang)}

<section id="limites" class="card">
  <h2>{m("Limites de la méthode", "Limits of the method")}</h2>
  <div class="excl small" style="max-width:none">
    <p style="margin:0 0 8px">{t_lim_intro}</p>
    <ul style="margin:0">
      {t_lim_bullets}
    </ul>
  </div>
</section>

<section id="mentions" class="card">
  <h2>{m("Sources, traçabilité et mentions légales", "Sources, traceability and legal notices")}</h2>
  <p class="small muted" style="max-width:none">{m("Chaque sondage agrégé est nommé, daté et attribué. Les indications ci-dessous sont celles que la loi exige pour la publication des résultats d'un sondage :",
    "Every aggregated poll is named, dated and attributed. The details below are those the law requires for publishing poll results:")}</p>
  {mentions_table(agg, lang)}
  {legal_block(agg, lang)}
</section>
</main>

<footer class="wrap">
  <p><a href="/fr/mentions-legales">{m("Mentions légales", "Legal notice")}</a></p>
</footer>
{THEME_JS}{CHRONO_JS}</body>
</html>
"""


def mentions_table(agg, lang="fr"):
    tr = (lambda a, b: b) if lang == "en" else (lambda a, b: a)
    """Sondages agrégés avec les indications requises par l'article 2 de la loi du 19 juillet 1977
    (organisme, commanditaire, effectif, dates, marges d'erreur) — telles que fournies par la source."""
    det = agg.get("polls_detail") or []
    if not det:
        return '<p class="small muted">' + tr("Aucun sondage dans la fenêtre d'agrégation.",
                                               "No poll in the aggregation window.") + '</p>'
    trs = "".join(
        f'<tr><td class="small">{d["institut"]}{" †" if d.get("importe") else ""}</td>'
        f'<td class="small">{d["commanditaire"]}</td>'
        f'<td class="num small">{frd(d["debut"])}<br>→ {frd(d["fin"])}</td>'
        f'<td class="num">{fr(d["echantillon"])}</td>'
        f'<td class="num small">± {fpc(d["marge"])}</td>'
        f'<td class="small muted">{d["fichier"]}</td></tr>'
        for d in det)
    return (
        '<table style="margin-top:14px">\n'
        '<tr><th>' + tr("Institut", "Pollster") + '</th><th>' + tr("Commanditaire", "Commissioner") + '</th>'
        '<th class="num">' + tr("Dates", "Dates") + '</th>'
        '<th class="num">' + tr("Interrogés", "Respondents") + '</th>'
        '<th class="num">' + tr("Marge", "Margin") + '</th>'
        '<th>' + tr("Référence de la notice", "Notice reference") + '</th></tr>\n'
        + trs + '</table>\n'
        f'<p class="small muted" style="margin-top:10px">' + tr(
            f"{len(det)} sondages agrégés, du {frd(agg['first'])} au {frd(agg['last'])}. La colonne « marge » "
            "reprend l'écart indiqué par l'institut pour le candidat le mieux placé de son enquête.",
            f"{len(det)} polls aggregated, from {frd(agg['first'])} to {frd(agg['last'])}. The \u201cmargin\u201d "
            "column repeats the interval stated by the pollster for its best-placed candidate.") + '</p>'
        + (('<p class="small muted">' + tr("† enquête extraite par nos soins de la notice publiée par la Commission des sondages, que la compilation amont n'avait pas encore intégrée.",
                                            "† survey extracted by us from the notice published by the Commission des sondages, which the upstream compilation had not yet integrated.") + '</p>')
           if any(d.get("importe") for d in det) else ''))


def legal_block(agg, lang="fr"):
    tr = (lambda a, b: b) if lang == "en" else (lambda a, b: a)
    """Ce que la loi impose, et ce que cette page en fait — sans jamais se dire elle-même « sondage »."""
    n = len(agg.get("polls_detail") or [])
    return f'''  <h3 style="margin-top:24px">{tr("Notre situation au regard de la loi du 19 juillet 1977", "Our position under the law of 19 July 1977")}</h3>
  <p class="small">{tr("Cette page ne réalise aucun sondage et n'interroge personne : elle agrège des sondages publiés par des instituts, en citant pour chacun les indications prévues par l'article 2 de la loi n° 77-808 du 19 juillet 1977 — organisme ayant réalisé l'enquête, commanditaire, nombre de personnes interrogées, dates des interrogations et mention des marges d'erreur. La loi organique n° 2021-335 du 29 mars 2021 impose par ailleurs, pour l'élection du Président de la République, que toute publication de sondage soit accompagnée des marges d'erreur des résultats publiés : elles figurent dans le tableau ci-dessus.",
     "This page conducts no poll and interviews nobody: it aggregates polls published by polling institutes, citing for each the information required by article 2 of law no. 77-808 of 19 July 1977 — the organisation that carried out the survey, the commissioner, the number of people interviewed, the dates of the interviews and the statement of margins of error. Organic law no. 2021-335 of 29 March 2021 further requires, for the election of the President of the Republic, that any publication of a poll be accompanied by the margins of error of the published results: they appear in the table above.")}</p>
  <p class="small">{tr("Les notices déposées par les instituts auprès de la <a href=\"https://www.commission-des-sondages.fr/notices/\">Commission des sondages</a> — questions posées, méthode d'échantillonnage, taux de non-réponse (article 3 de la même loi) — y sont consultables publiquement. Nous ne les reproduisons pas ici, et nous signalons la limite que cela crée : le libellé exact de chaque question n'est pas vérifiable dans nos tableaux.",
     "The notices filed by the institutes with the <a href=\"https://www.commission-des-sondages.fr/notices/\">Commission des sondages</a> — questions asked, sampling method, non-response rate (article 3 of the same law) — are publicly available there. We do not reproduce them here, and we flag the limit this creates: the exact wording of each question cannot be verified in our tables.")}</p>
  <p class="small">{tr("En période électorale, l'article 11 interdit toute publication, diffusion ou commentaire de sondage électoral la veille et le jour du scrutin ; pour l'élection présidentielle, cette interdiction court du samedi précédant le scrutin à zéro heure jusqu'à la fermeture du dernier bureau de vote. Cette page s'y conformera, y compris en cessant de se régénérer le moment venu.",
     "During an election period, article 11 forbids any publication, broadcast or commentary of an electoral poll on the eve and the day of the ballot; for the presidential election, this ban runs from midnight on the Saturday before the ballot until the closing of the last polling station. This page will comply, including by ceasing to regenerate when the time comes.")}</p>
    <p class="small">{tr("La génération quotidienne s'interrompt d'elle-même la veille et le jour de chaque tour de scrutin, dès lors que les dates officielles sont renseignées dans le générateur.",
     "The daily generation stops by itself on the eve and the day of each round of voting, once the official dates are entered in the generator.")}</p>
  <p class="small">{tr("Nous n'employons pas le mot « sondage » pour notre propre calcul : une <em>moyenne de sondages</em> n'est pas une enquête, et la présenter comme telle serait une faute méthodologique — la loi sanctionne d'ailleurs cet usage impropre.",
     "We do not use the word “poll” for our own computation: an <em>average of polls</em> is not a survey, and presenting it as one would be a methodological fault — the law also punishes that improper use.")}</p>'''


def frd(s):
    """'2026-09-09' -> '09/09/2026' (date d'enquête, lecture française)."""
    try:
        y, m, j = str(s).split("-")
        return f"{j}/{m}/{y}"
    except Exception:
        return str(s)


def fpc(x):
    """Nombre à une décimale, virgule française, sans signe : 3.5 -> 3,5."""
    try:
        return f"{float(x):.1f}".replace(".", ",")
    except Exception:
        return str(x)


def frdate(s, lang="fr"):
    """'2026-09-14 15:29' -> '14/09/2026 à 15:29' (date de génération, lecture française)."""
    try:
        d, h = s.split(" ")
        y, m, j = d.split("-")
        return f"{j}/{m}/{y} " + ("at" if lang == "en" else "à") + f" {h}"
    except Exception:
        return s


def valeurs_textes(agg, rows):
    """Valeurs du jour injectées dans les textes rédigés (jetons {{...}} de content/observatoire.json)."""
    v = dict(
        date_maj=frd(TODAY),
        scenario=agg["scenario"],
        scenario_size=agg["scenario_size"],
        polls_aggregated=agg["polls_aggregated"],
        polls_in_window=agg["polls_in_window"],
        window=agg["window"],
        fenetre=agg["window"],
    )
    if rows:
        v.update(
            tete_nom=rows[0]["candidat"],
            tete_val=fr1u(rows[0]["intentions"]),       # 34,0 : l'exemple de citation montre la précision
            tete_ic=f'{fr(rows[0]["bas"])}&ndash;{fr(rows[0]["haut"])}',
        )
    return v


def render_landing(agg, movs=None, trends=None, fc=None, lang="fr"):
    movs = movs or []
    trends = trends or []
    r0 = agg["rows"][0] if agg["rows"] else None
    n_cand = len(agg["rows"])
    VALEURS = valeurs_textes(agg, agg["rows"])
    # `m(français, anglais)` : le texte reste à côté du gabarit qui l'affiche. Les
    # libellés partagés entre plusieurs pages passent par i18n.py ; les phrases propres
    # à cette page restent ici, pour qu'on ne cherche jamais où est la traduction.
    def m(fr_txt, en_txt):
        return en_txt if lang == "en" else fr_txt
    url_fr = "https://dileviathan.fr" + lien("/", "fr")
    url_en = "https://dileviathan.fr" + lien("/", "en")
    url = url_en if lang == "en" else url_fr
    autre = url_fr if lang == "en" else url_en
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="{meta_description('/observatoire/', lang)}">
<title>{titre_court('/observatoire/', lang)}</title>
<link rel="canonical" href="{url}">
<link rel="alternate" hreflang="fr" href="{url_fr}">
<link rel="alternate" hreflang="en" href="{url_en}">
<link rel="alternate" hreflang="x-default" href="{url_fr}">
{meta_social('/observatoire/', lang)}
{ld_json("/observatoire/", lang)}
{matomo()}
<style>{CSS}{DARK}</style>
{THEME_HEAD}</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand">{m("Présidentielle 2027 <span>· observatoire</span>", "2027 presidential election <span>· monitor</span>")}</div>
  <div class="navlinks"><a href="{lien_page('/sondages/', lang)}">{m("Agrégation", "Aggregate")}</a><a href="{lien_page('/candidats/', lang)}">{m("Les candidats", "Candidates")}</a><a href="{lien_page('/backtest/', lang)}">{m("Rétro-test 2022", "2022 backtest")}</a>{nav_workflow(lang)}{nav_lois(lang)}<a href="#evolution">{m("Évolution", "Trend")}</a>
  <a href="#comparaison">{m("Comparaison", "Comparison")}</a><a href="#methode">{m("Méthode", "Method")}</a><a href="#donnees">{m("Données", "Data")}</a><a href="#limites">{m("Limites", "Limits")}</a>{toggle_langue('/', lang, en_pret=True)}</div>{THEME_BTN}
</div></div>

<header class="wrap hero">
  <span class="eyebrow">{m("Observatoire des sondages · présidentielle 2027", "Poll monitor · 2027 presidential election")}</span>
  <h1>{m("Agrégation des sondages de la présidentielle 2027", "Poll aggregation for the 2027 presidential election")}</h1>
  <p class="lede">{m("Nous compilons les sondages publiés par les instituts, <strong>un scénario de candidatures à la fois</strong>, avec la méthode écrite noir sur blanc et les limites affichées à côté des chiffres. Pas de probabilité de victoire : une lecture sourcée, datée, discutable.", "We compile the polls published by the polling institutes, <strong>one candidate scenario at a time</strong>, with the method written out in full and the limits displayed next to the figures. No probability of victory: a sourced, dated, arguable reading.")}</p>
  <div class="cta">
    <a class="btn" href="{lien_page('/sondages/', lang)}">{m("Voir l'agrégation du jour", "See today's aggregate")}</a>
    <a class="btn2" href="#methode">{m("La méthode", "The method")}</a>
  </div>

  <div class="statgrid">
    <div class="stat"><span>{m("Favori du scénario retenu", "Front-runner in the selected scenario")}</span>
      <b>{"" if not r0 else fr(r0["intentions"]) + " %"}</b>
      <span>{"" if not r0 else r0["candidat"]}</span></div>
    <div class="stat"><span>{m("Sondages agrégés", "Polls aggregated")}</span><b>{agg["polls_aggregated"]}</b>
      <span>{m("sur", "over")} {agg["agg_window"]} {m("jours", "days")}</span></div>
    <div class="stat"><span>{m("Instituts couverts", "Institutes covered")}</span><b>{len(agg["instituts"])}</b>
      <span>{", ".join(agg["instituts"][:3])}</span></div>
    <div class="stat"><span>{m("Dernière enquête", "Latest poll")}</span><b>{agg["last"][8:10]}/{agg["last"][5:7]}/{agg["last"][0:4]}</b>
      <span>{m("période", "period")} : {agg["first"][8:10]}/{agg["first"][5:7]}/{agg["first"][0:4]} → {agg["last"][8:10]}/{agg["last"][5:7]}/{agg["last"][0:4]}</span></div>
  </div>
  <div class="chrono-glass">
      <span class="chrono-glass-label">{m("Premier tour", "First round")}</span>
      <div class="chrono-glass-units">
        <div class="chrono-unit"><span class="chrono-num" data-target="{f"{SCRUTIN_1}T20:00:00" if SCRUTIN_1 else ''}" data-unit="d">--</span><span class="chrono-lab">{m("jours", "days")}</span></div>
        <div class="chrono-unit"><span class="chrono-num" data-target="{f"{SCRUTIN_1}T20:00:00" if SCRUTIN_1 else ''}" data-unit="h">--</span><span class="chrono-lab">{m("heures", "hours")}</span></div>
        <div class="chrono-unit"><span class="chrono-num" data-target="{f"{SCRUTIN_1}T20:00:00" if SCRUTIN_1 else ''}" data-unit="m">--</span><span class="chrono-lab">{m("minutes", "minutes")}</span></div>
        <div class="chrono-unit"><span class="chrono-num" data-target="{f"{SCRUTIN_1}T20:00:00" if SCRUTIN_1 else ''}" data-unit="s">--</span><span class="chrono-lab">{m("secondes", "seconds")}</span></div>
      </div>
      <span class="chrono-glass-foot">{m("dimanche 18 avril 2027", "Sunday 18 April 2027")}</span>
    </div>
  <p class="small muted">{m("Scénario retenu", "Scenario used")} : {agg["scenario"]}
  ({agg["scenario_size"]} {m("candidats", "candidates")}) · {n_cand} {m("candidats publiés", "candidates published")} · {m("source", "source")} : {agg["total_polls_all"]}
  {m("sondages compilés, dont", "polls compiled, of which")} {agg["polls_in_window"]} {m("sur les", "over the last")} {agg["window"]} {m("derniers jours.", "days.")}
  {m("Page régénérée le", "Page regenerated on")} {frdate(agg["generated"], lang)}.</p>
</header>

<main class="wrap">
<section id="evolution" class="card">
  <h2>{m("Évolution, semaine par semaine", "Week-by-week trend")} — {m("scénario", "scenario")} {agg["scenario"]} ({agg["scenario_size"]} {m("noms", "names")})</h2>
  <p class="small muted" style="max-width:none">{m("Série <strong>rétro-calculée</strong> par la méthode actuelle, sur les sondages publiés à chaque échéance hebdomadaire (ce que la page aurait affiché, pas ce qu'elle affichait).", "Series <strong>recomputed retrospectively</strong> with the current method, from the polls published at each weekly date (what the page would have shown, not what it did show).")}
  {m("Un nom absent de cette liste ne disparaît pas de la page : la ligne « hors scénario » et le tableau « toutes listes » ci-dessous le suivent. Un écart inférieur à 1 point reste dans la marge et n'est pas commenté.", "A name absent from this list does not disappear from the page: the \"outside the scenario\" line and the \"all lists\" table below follow it. A gap below 1 point stays within the margin and is not commented on.")}</p>
  {mov_table(movs, lang)}
  {hors_scenario(movs, trends, lang=lang)}
  <p class="small" style="margin-top:14px"><strong>{m("Mouvements sur 7 jours (scénario retenu) :", "7-day movements (selected scenario):")}</strong>
  {mov_line(movs, lang)}.</p>
  <h3 style="margin-top:24px">{m("Tendance, toutes listes confondues", "Trend, all lists combined")}</h3>
  <p class="small muted" style="max-width:none">{m("Indicateur de direction : chaque sondage du premier tour compte, quelle que soit la liste testée. Les niveaux ne sont pas comparables à ceux du tableau ci-dessus ; seule l'évolution compte, et elle est plus robuste (beaucoup plus d'enquêtes).", "Direction indicator: every first-round poll counts, whichever list it tested. The levels are not comparable with those in the table above; only the movement matters, and it is more robust (far more surveys).")}
  <a href="{lien_page('/sondages/', lang)}#evolution">{m("Méthode et détail", "Method and detail")}</a>.</p>
  {trend_table(trends, lang)}
  <p class="small" style="margin-top:14px"><strong>{m("Mouvement de fond :", "Underlying movement:")}</strong> {mov_line(trends, lang)}.</p>
</section>

<section class="card">
  <h2>{m("Trois principes", "Three principles")}</h2>
  <div class="cards">
    <div class="card2"><h3>{m("Une source unique, citée", "One source, cited")}</h3>
      <p>{m("Les données viennent de la compilation publique et vérifiable", "The data come from the public, verifiable compilation")}
      <a href="https://github.com/MieuxVoter/presidentielle2027">MieuxVoter/presidentielle2027</a>
      {m("(licence MIT) ; les enquêtes qu'elle n'a pas encore intégrées sont extraites par nos soins des notices officielles de la Commission des sondages. Jamais d'un chiffre repris de seconde main sans origine.", "(MIT licence); surveys it has not yet integrated are extracted by us from the official notices of the Commission des sondages. Never a figure taken second-hand without an origin.")}</p></div>
    <div class="card2"><h3>{m("Un scénario à la fois", "One scenario at a time")}</h3>
      <p>{m("Un sondage ne vaut que pour la liste de candidats qu'il teste. Nous retenons la liste testée le plus récemment", "A poll is worth only for the candidate list it tests. We keep the most recently tested list")}
      — {m("à condition qu'au moins", "provided at least")} {agg["min_polls"]} {m("enquêtes l'aient testée sur les", "surveys tested it over the last")}
      {agg["window"]} {m("derniers jours", "days")} — {m("et nous ignorons les autres, plutôt que de moyenner des configurations différentes et de produire un chiffre qui n'existe nulle part.", "and we ignore the others, rather than averaging different configurations and producing a figure that exists nowhere.")}</p></div>
    <div class="card2"><h3>{m("Les limites avec les chiffres", "Limits alongside the figures")}</h3>
      <p>{m("Intervalle, amplitude observée, instituts, nombre de sondages, et la liste de ce que la méthode ne fait pas : tout est publié sur la même page que les résultats.", "Interval, observed spread, institutes, number of polls, and the list of what the method does not do: everything is published on the same page as the results.")}</p></div>
  </div>
</section>

<section class="card">
  <h2>{m("Ce que ça fait — ce que ça ne fait pas", "What it does — what it does not do")}</h2>
  <div class="two">
    <div class="card2">
      <h3 class="ok">{m("Ce que ça fait", "What it does")}</h3>
      <ul class="tight">
        <li>{m("Une moyenne pondérée par la fraîcheur de l'enquête et la taille de l'échantillon.", "An average weighted by the freshness of the survey and the sample size.")}</li>
        <li>{m("Un intervalle de confiance explicite sur la moyenne, et l'amplitude réelle entre instituts.", "An explicit confidence interval on the average, and the actual spread between institutes.")}</li>
        <li>{m("Le détail par candidat : parti, nombre de sondages, dernière enquête prise en compte.", "Per-candidate detail: party, number of polls, last survey taken into account.")}</li>
        <li>{m("Une page méthode complète et un générateur sans dépendance externe — les chiffres ne sont jamais saisis à la main.", "A complete method page and a generator with no external dependency — the figures are never entered by hand.")}</li>
      </ul>
    </div>
    <div class="card2">
      <h3 class="ko">{m("Ce que ça ne fait pas", "What it does not do")}</h3>
      <ul class="tight">
        <li>{m("Aucune probabilité de victoire, aucun modèle de second tour.", "No probability of victory, no second-round model.")}</li>
        <li>{m("Aucune probabilité de second tour ni de victoire ; aucune anticipation de la participation ou des reports de voix.", "No probability of reaching the second round or of winning; no forecast of turnout or of vote transfers.")}</li>
        <li>{m("Aucune donnée de question : le libellé exact des questions posées n'est pas dans notre source (voir les notices de la Commission des sondages).", "No question data: the exact wording of the questions asked is not in our source (see the notices of the Commission des sondages).")}</li>
        <li>{m("Aucune anticipation de la participation, des reports de voix ou d'un fait de campagne.", "No forecast of turnout, vote transfers or a campaign event.")}</li>
        <li>{m("Aucune reprise de sondages testant d'autres listes de candidats.", "No reuse of polls testing other candidate lists.")}</li>
      </ul>
    </div>
  </div>
</section>

<section id="methode" class="card">
  <h2>{m("La méthode, en clair", "The method, plainly")}</h2>
  <ol class="steps">
    <li><strong>{m("Collecte.", "Collection.")}</strong> {m("Nous lisons le flux public de la compilation MieuxVoter (CSV et JSON), premier tour uniquement. Quand une notice publiée par la Commission des sondages n'y figure pas encore, nous l'extrayons nous-mêmes et la fusionnons sans doublon — même institut, mêmes dates de terrain, même ensemble de candidats testés ; la compilation reste prioritaire, et l'apport disparaît d'elle-même dès qu'elle rattrape l'enquête.", "We read the public feed of the MieuxVoter compilation (CSV and JSON), first round only. When a notice published by the Commission des sondages is not yet there, we extract it ourselves and merge it without duplication — same institute, same fieldwork dates, same set of tested candidates; the compilation keeps priority, and our addition disappears by itself as soon as it catches up with the survey.")}</li>
    <li><strong>{m("Choix du scénario.", "Choosing the scenario.")}</strong> {m("Le scénario retenu est la liste testée le plus récemment sur les", "The scenario used is the list tested most recently over the last")} {agg["window"]} {m("derniers jours, parmi celles qui comptent au moins", "days, among those with at least")} {agg["min_polls"]}
    {m("enquêtes — les listes de candidats bougent encore, et une liste que plus aucun institut ne teste ne doit pas rester en tête.", "surveys — candidate lists are still moving, and a list no institute tests any more must not stay at the top.")}</li>
    <li><strong>{m("Pondération.", "Weighting.")}</strong> {m("Chaque sondage pèse selon son âge (demi-vie de", "Each poll is weighted by its age (half-life of")}
    {agg["half_life"]} {m("jours) et la racine de son échantillon.", "days) and the square root of its sample.")}</li>
    <li><strong>{m("Incertitude.", "Uncertainty.")}</strong> {m("L'intervalle à 95 % de la moyenne est plancheré à", "The 95% interval on the average has a floor of")}
    ±{fr(agg["ic_floor"], lang)} {m("point, pour ne pas fabriquer de fausse précision sur peu de sondages.", "point, so as not to manufacture false precision from few polls.")}</li>
    <li><strong>{m("Publication.", "Publication.")}</strong> {m("Un candidat n'apparaît qu'à partir de", "A candidate appears only from")} {agg["min_polls"]} {m("sondages.", "polls.")}</li>
  </ol>
  <div class="excl small" style="margin-top:14px">
    <code>poids w = exp(−ln2 × âge_jours / {agg["half_life"]}) × √(échantillon / 1000)</code><br>
    <code>moyenne = Σ(w·x) / Σw</code> &nbsp;·&nbsp;
    <code>IC 95 % = max( 1,96 × σ_pondéré / √n_eff , {fr(agg["ic_floor"], lang)} )</code> {m("avec", "with")}
    <code>n_eff = (Σw)² / Σw²</code>
  </div>
  <p class="small muted" style="margin-top:12px">{m("Le détail des calculs, les valeurs par candidat et les limites complètes sont sur la page", "The details of the calculations, the per-candidate values and the full limits are on the")}
  <a href="{lien_page('/sondages/', lang)}">{m("Agrégation", "Aggregate")}</a>.</p>
</section>

<section id="donnees" class="card">
  <h2>{m("Les données", "The data")}</h2>
  <div class="cards">
    <div class="card2"><h3>{m("Source", "Source")}</h3><p><a href="https://github.com/MieuxVoter/presidentielle2027">MieuxVoter/presidentielle2027</a>
      — {m("compilation ouverte des sondages de la présidentielle 2027 (CSV + JSON), licence MIT. L'attribution est obligatoire et figure sur chaque page.", "open compilation of the 2027 presidential election polls (CSV + JSON), MIT licence. Attribution is mandatory and appears on every page.")}</p></div>
    <div class="card2"><h3>{m("Fraîcheur", "Freshness")}</h3><p>{agg["total_polls_all"]} {m("sondages compilés à ce jour,", "polls compiled to date,")}
      {agg["polls_in_window"]} {m("sur les", "over the last")} {agg["window"]} {m("derniers jours. La page est régénérée par script ; les données sont mises en cache 12 heures maximum.", "days. The page is regenerated by script; the data are cached for 12 hours at most.")}</p></div>
  </div>
</section>

<section id="comparaison" class="card">
  <h2>{m("Comparaison avec une prévision bayésienne", "Comparison with a Bayesian forecast")}</h2>
  <p class="small muted" style="max-width:none">{m("Un projet MIT indépendant prévoit la même élection à partir des <strong>mêmes sondages</strong>, mais en intégrant l'incertitude sur la liste des candidats au lieu de verrouiller un scénario. En résumé : les deux lectures se rejoignent désormais sur tout le haut du tableau (aucun écart supérieur à 0,3 point sous le quatrième), et leurs intervalles restent dix fois plus larges que les nôtres — donc plus honnêtes. Analyse complète sur la page", "An independent MIT project forecasts the same election from the <strong>same polls</strong>, but folds in the uncertainty over the candidate list instead of locking a scenario. In short: the two readings now agree across the top of the table (no gap above 0.3 point below fourth place), and their intervals remain ten times wider than ours — hence more honest. Full analysis on the")}
  <a href="{lien_page('/sondages/', lang)}#comparaison">{m("Agrégation", "Aggregate")}</a>.</p>
  {forecast_block(agg, trends, fc, lang)}
  {backtest_block(lang)}
</section>

<section id="limites" class="card">
  <h2>{m("À lire avant de citer un chiffre", "Read before citing a figure")}</h2>
  <div class="excl small" style="max-width:none">
    <p style="margin:0 0 8px"><strong>{m("Cette page n'est pas un modèle de prévision.", "This page is not a forecasting model.")}</strong> {m("Elle décrit ce que disent les sondages publiés, agrémenté d'une incertitude explicite — rien de plus.", "It describes what the published polls say, with an explicit uncertainty attached — nothing more.")}</p>
    <p style="margin:0">{m("Une moyenne de sondages n'est pas un résultat, et une intention de vote n'est pas un vote. La méthode est versionnée : chaque changement est daté dans le journal ci-dessous, et le détail de ce qui peut être cité — sous quelle forme et à quelles conditions — se trouve dans la section", "An average of polls is not a result, and a voting intention is not a vote. The method is versioned: every change is dated in the log below, and the detail of what may be cited — in what form and under what conditions — is in the section")}
    <a href="{lien_page('/sondages/', lang)}#a-lire">{m("Citer un chiffre", "Citing a figure")}</a>.</p>
  </div>
  <ul class="tight small" style="max-width:none">
    <li><strong>{m("Citez la moyenne, jamais un sondage", "Cite the average, never a single poll")}</strong> : {m("« moyenne des sondages publiés au", "\"average of the polls published as of")}
    {VALEURS["date_maj"]}, {m("scénario", "scenario")} {VALEURS["scenario"]} ({VALEURS["scenario_size"]} {m("candidats", "candidates")}),
    {VALEURS["polls_aggregated"]} {m("enquêtes agrégées »", "surveys aggregated\"")}.</li>
    <li><strong>{m("Citez l'intervalle avec le niveau", "Cite the interval with the level")}</strong> : {VALEURS["tete_nom"]}
    {VALEURS["tete_val"]} % [{VALEURS["tete_ic"]}]. {m("Un chiffre nu laisse croire à une précision que la moyenne n'a pas.", "A bare figure suggests a precision the average does not have.")}</li>
    <li><strong>{m("Sous un point d'écart, nous ne commentons pas", "Below one point of difference, we do not comment")}</strong> — {m("l'écart est dans la marge, et il ne doit pas être commenté davantage ailleurs.", "the gap is within the margin, and it should not be commented on further elsewhere.")}</li>
  </ul>
</section>

{changelog_bloc(3, m("Dernières mises à jour", "Latest updates"), m("Résumé des trois dernières. Le journal complet, avec les sources et le cadre légal, est dans la section Citer un chiffre de la page Agrégation.", "Summary of the last three. The full log, with sources and the legal framework, is in the Citing a figure section of the Aggregate page."), VALEURS, lang)}
</main>

<footer class="wrap">
  <p><a href="/fr/mentions-legales">{m("Mentions légales", "Legal notice")}</a></p>
</footer>
{THEME_JS}{CHRONO_JS}</body>
</html>
"""

def ecrire_dataset(agg):
    """Jeux de données machine de l'agrégation (19/10/2026, audit GEO).

    Pour citer un chiffre, un agent devait télécharger 76 Ko de HTML et reconstruire le
    tableau. Ces deux fichiers disent exactement la même chose que la page, avec leur date
    de calcul, l'unité de chaque colonne et le lien vers la méthode : c'est ce qui rend le
    chiffre citable sans scraping. Le CSV a une ligne par candidat, séparateur virgule.
    """
    lignes = [dict(
        nom=r["candidat"], parti=r["parti"],
        moyenne_pct=r["intentions"], ic95_bas_pct=r["bas"], ic95_haut_pct=r["haut"],
        min_pct=r["mini"], max_pct=r["maxi"], amplitude_pct=r["amplitude"],
        sondages=r["n"], n_effectif=r["neff"], dernier_sondage=r["dernier"],
        instituts=r.get("instituts") or [],
    ) for r in agg["rows"]]
    doc = dict(
        genere_le=TODAY.isoformat(),
        calcule_le=agg["generated"],
        page_html=SITE_URL + "/observatoire/sondages/",
        methode_url=SITE_URL + "/observatoire/workflow/",
        limites_url=SITE_URL + "/observatoire/sondages/",
        unites="points de pourcentage (sauf sondages et n_effectif) ; n_effectif = effectif "
               "corrigé des poids ; sondages = nombre d'enquêtes agrégées pour ce candidat",
        scenario=agg["scenario"], fenetre_jours=agg["agg_window"],
        demi_vie_jours=agg["half_life"], sondages_agreges=agg["polls_aggregated"],
        premier_sondage=agg["first"], dernier_sondage=agg["last"],
        candidats=lignes,
    )
    dossier = os.path.join(SITE, "sondages")
    os.makedirs(dossier, exist_ok=True)
    with open(os.path.join(dossier, "donnees.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    colonnes = ["nom", "parti", "moyenne_pct", "ic95_bas_pct", "ic95_haut_pct",
                "min_pct", "max_pct", "amplitude_pct", "sondages", "n_effectif",
                "dernier_sondage", "calcule_le", "instituts"]
    with open(os.path.join(dossier, "donnees.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(colonnes)
        for l in lignes:
            w.writerow([l["nom"], l["parti"], l["moyenne_pct"], l["ic95_bas_pct"],
                        l["ic95_haut_pct"], l["min_pct"], l["max_pct"], l["amplitude_pct"],
                        l["sondages"], l["n_effectif"], l["dernier_sondage"],
                        agg["generated"], "; ".join(l["instituts"])])
    print(f"  -> {os.path.join(dossier, 'donnees.json')} et donnees.csv ({len(lignes)} candidats)")


def main():
    sus = suspension_legale()
    if sus:
        page = ("<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
                "<meta name=\"robots\" content=\"noindex\"><title>Publication suspendue</title></head>"
                "<body style=\"font-family:system-ui;max-width:40em;margin:12vh auto;padding:0 1.2em;"
                "line-height:1.6\"><h1>Publication suspendue</h1>"
                "<p>Conformément à l'article 11 de la loi du 19 juillet 1977, aucun sondage électoral ne"
                " peut être publié, diffusé ou commenté la veille et le jour du scrutin.</p>"
                f"<p>Le scrutin a lieu le {frd(str(sus))}. Cette page reprendra sa mise à jour après la"
                " fermeture du dernier bureau de vote.</p></body></html>")
        for rel in (os.path.join(SITE, "index.html"), os.path.join(SITE, "sondages", "index.html")):
            os.makedirs(os.path.dirname(rel), exist_ok=True)
            open(rel, "w", encoding="utf-8").write(page)
        print(f"publication suspendue (scrutin du {sus}) : aucune donnée écrite.")
        return
    polls = fetch(force="--force" in os.sys.argv)
    agg = aggregate(polls)
    if not agg:
        raise SystemExit("Aucun sondage exploitable dans la fenêtre.")
    series = weekly_series(polls, weeks=8, base=agg)
    movs = movements(series)
    trends = trend_movements(polls, weeks=8)
    # Lecture « toutes listes » complète (le tableau de tendance n'en affiche que douze) :
    # sert à la comparaison avec la prévision bayésienne, candidat par candidat.
    agg["all_lists"] = {k: v["intentions"] for k, v in trend_point(polls, TODAY).items()}
    # Nombre d'enquêtes de la couche locale réellement utilisées (celles que l'amont n'a pas).
    agg["imports_total"] = len(IDS_IMPORTES)
    json.dump(dict(generated=agg["generated"], scenario=agg["scenario"], window=agg["window"],
                   polls_window=agg["polls_in_window"], polls_agg=agg["polls_aggregated"],
                   last=agg["last"], movs=movs, trends=trends),
              open(os.path.join(DATA, "movements.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    fc = fetch_forecast(force="--force" in os.sys.argv)
    n_hist = save_history(agg)
    agg["series"] = [dict(date=p["date"], weeks_ago=p["weeks_ago"], polls=p["polls"],
                          rows={k: v["intentions"] for k, v in p["rows"].items()}) for p in series]
    os.makedirs(SITE, exist_ok=True)
    os.makedirs(os.path.join(SITE, "sondages"), exist_ok=True)
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(render_landing(agg, movs, trends, fc))
    # Version anglaise : mêmes données, mêmes chiffres, autre langue. Une page n'est
    # écrite que si sa traduction est complète — le sélecteur ne pointe que sur elle.
    en_dir = os.path.join(SITE, "en", "observatoire")
    os.makedirs(os.path.join(en_dir, "sondages"), exist_ok=True)
    open(os.path.join(en_dir, "index.html"), "w", encoding="utf-8").write(
        render_landing(agg, movs, trends, fc, lang="en"))
    open(os.path.join(en_dir, "sondages", "index.html"), "w", encoding="utf-8").write(
        render_sondages(agg, movs, trends, fc, lang="en"))
    open(os.path.join(SITE, "sondages", "index.html"), "w", encoding="utf-8").write(
        render_sondages(agg, movs, trends, fc))
    json.dump(agg, open(os.path.join(DATA, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ecrire_dataset(agg)
    print(f"sondages source : {agg['total_polls_all']} | fenêtre : {agg['polls_in_window']} | "
          f"scénario {agg['scenario']} : {agg['polls_in_scenario']} sondages")
    for m in movs:
        d7 = "  n/a" if m["delta7"] is None else f"{m['delta7']:+5.1f}"
        print(f"  {m['candidat']:26} {m['intentions']:5} %  Δ7j={d7}   "
              f"(J-7 : {m['intention7'] if m['intention7'] is not None else '—'})")
    print("mouvement de fond (toutes listes) : " + mov_line(trends))
    print("prévision bayésienne : " + (f"arrêtée au {fc.get('as_of')}, "
          f"{len([c for c in fc['candidats'] if (c.get('share') or {}).get('q50')])} candidats"
          if fc else "indisponible"))
    print(f"série : {len(series)} points hebdo | archive quotidienne : {n_hist} jour(s) "
          f"-> {os.path.join(DATA, 'history.jsonl')}")


if __name__ == "__main__":
    main()
