#!/usr/bin/env python3
"""Veille législative — Assemblée nationale.

Télécharge les scrutins de la législature en cours (17e, juillet 2024 →),
les filtre sur le périmètre Diléviathan (numérique, IA, données, surveillance,
cyber, médias) et génère la page /observatoire/lois/.

Modèle identique à l'observatoire sondages : source unique publique,
génération statique, cron hebdomadaire.

Sources : data.assemblee-nationale.fr (licence ouverte / Etalab).
"""

import json, os, re, urllib.request, zipfile, io
import sys
from datetime import datetime
from collections import defaultdict, Counter

# Réutilise les helpers partagés de l'observatoire (données structurées, mesure d'audience) :
# une seule définition pour les six pages. Le chemin est ajouté explicitement pour que le
# script fonctionne quel que soit le répertoire d'appel — le cron, lui, tourne depuis le dépôt.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as G

# ---------- chemins ----------
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
SITE = os.path.join(BASE, "site", "lois")
CACHE = os.path.join(DATA, "lois")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(SITE, exist_ok=True)

# ---------- sources ----------
# 17e législature = juillet 2024 → aujourd'hui : la législature en cours.
# 16e législature (2022-2024) : citée en référence (loi SREN, majorité numérique).
LEG_CUR = "17"
LEG_REF = "16"
URL_SCRUTINS = "https://data.assemblee-nationale.fr/static/openData/repository/{L}/loi/scrutins/Scrutins.json.zip"
# Référentiel des organes (groupes politiques) : donne le nom et la couleur
# officielle de chaque groupe, que les scrutins ne portent pas (organeRef seul).
URL_ORGANES = ("https://data.assemblee-nationale.fr/static/openData/repository/{L}/amo/"
               "deputes_actifs_mandats_actifs_organes/"
               "AMO10_deputes_actifs_mandats_actifs_organes.json.zip")

# ---------- situation du Parlement (faits datés, vérifiés) ----------
# Relevé du 16/09/2026 : les scrutins publiés en données ouvertes s'arrêtent au
# 21/07/2026, dernière séance de la session ordinaire 2025-2026. Le gouvernement a
# renoncé à une session extraordinaire en septembre, et la session ordinaire 2026-2027
# ouvre le 1er octobre 2026 (Le Monde, 3 septembre 2026). Contrôle effectué : le fichier
# amont, réédité le 16/09/2026 à 10 h 26 GMT, est identique octet pour octet à celui de
# la veille — la veille n'est donc pas en retard, le Parlement ne vote simplement pas.
DERNIERE_SEANCE = "2026-07-21"
OUVERTURE_SESSION = "2026-10-01"
SOURCE_INTERSESSION = ("Le Monde, « Assemblée nationale : le gouvernement renonce à une "
                       "session extraordinaire en septembre », 3 septembre 2026")

# ---------- périmètre éditorial ----------
# Chaque thème : libellé + expression régulière appliquée au nom du texte de loi.
# Les scrutins sont ensuite regroupés par texte, pas listés en vrac.
THEMES = [
    ("Numérique & plateformes",
     r"numériqu|internet|en ligne|plateformes?|services numériques|commerce électronique"),
    ("Réseaux sociaux & protection des mineurs",
     r"réseaux? sociaux|mineurs.{0,90}(écran|réseau|numériq|en ligne|internet)"),
    ("IA & algorithmes",
     r"\bIA\b|intelligence artificielle|algorith"),
    ("Données & vie privée",
     r"données|vie privée|fichier|traitement automatisé|RGPD|CNIL|identité numérique"),
    ("Surveillance & biométrie",
     r"surveill|vidéosurveillance|biométr|reconnaissance faciale|géolocalisation|drones?"),
    ("Cyber & sécurité numérique",
     r"cyber|sécurité des systèmes|informatiqu|logiciel|télécom|chiffrement"),
    ("Médias & souveraineté informationnelle",
     r"médias|audiovisuel|presse|droits voisins|radiodiffusion|publicité"),
]

# Extraction du nom du texte de loi depuis le titre d'un scrutin.
# Ex. « l'amendement n° 80 de Mme Belluco ... de la proposition de loi visant à
# protéger les mineurs ... (première lecture). » → « proposition de loi visant à
# protéger les mineurs ... »
LAW_PAT = re.compile(
    r"\b(du|de la|d'une|de l')\s+(projet|proposition)\s+de\s+loi\s+(organique\s+)?(.{6,160})",
    re.I)
# Fin de nom : parenthèse de lecture, ou fin de phrase.
READING_PAT = re.compile(r"\s*\((?:première|deuxième|nouvelle|troisième|lecture|texte|"
                         r"projet|proposition|commission)[^)]*\)", re.I)
FINAL_VOTE_PAT = re.compile(r"^l['’]ensemble\b", re.I)


def _clean(s):
    """Normalise apostrophes et espaces."""
    return re.sub(r"\s+", " ", (s or "").replace("’", "'").replace("\u00a0", " ")).strip()


def law_name(titre):
    """Retourne (nom du texte, nature) ou (None, None)."""
    m = LAW_PAT.search(titre)
    if not m:
        return None, None
    nature = m.group(2).lower()  # projet | proposition
    organique = " organique" if m.group(3) else ""
    suite = m.group(4)
    suite = READING_PAT.sub("", suite)
    suite = suite.split("(")[0].strip(" .,;:")
    if len(suite) < 6:
        return None, None
    return f"{nature} de loi{organique} {suite}", nature


def vote_kind(titre):
    """Type de vote : ensemble, article, amendement, motion, autre."""
    t = titre.lstrip()
    if FINAL_VOTE_PAT.match(t):
        return "ensemble"
    if re.match(r"^la motion\b", t, re.I):
        return "motion"
    if re.match(r"^l['’]article\b", t, re.I):
        return "article"
    if re.match(r"^l['’]amendement|^le sous-amendement", t, re.I):
        return "amendement"
    return "autre"


def short_objet(titre):
    """Formule courte pour le tableau (retire le nom du texte, déjà en titre de carte)."""
    t = _clean(titre)
    t = READING_PAT.sub("", t).rstrip(" .")
    t = re.sub(r"\s+(du|de la|de l')?\s*(projet|proposition) de loi.*$", "", t, flags=re.I)
    return t[:130]


# ---------- téléchargement ----------
def load_scrutins(leg):
    """Télécharge et parse tous les scrutins d'une législature (cache 24 h)."""
    cache_file = os.path.join(CACHE, f"scrutins_L{leg}.json")
    if os.path.exists(cache_file):
        age_h = (datetime.now().timestamp() - os.path.getmtime(cache_file)) / 3600
        if age_h < 24:
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)

    url = URL_SCRUTINS.format(L=leg)
    try:
        print(f"  Téléchargement des scrutins L{leg}…")
        req = urllib.request.Request(url, headers={"User-Agent": "observatoire-2027/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        scrutins, err = [], 0
        for n in z.namelist():
            if not n.endswith(".json"):
                continue
            try:
                s = json.load(z.open(n)).get("scrutin")
                if s:
                    scrutins.append(s)
            except Exception:
                err += 1
        if err:
            print(f"  ⚠️  {err} fichiers illisibles (ignorés)")
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(scrutins, f, ensure_ascii=False)
        print(f"  ✅ {len(scrutins)} scrutins L{leg}")
        return scrutins
    except Exception as e:
        print(f"  ❌ Échec téléchargement L{leg} : {e}")
        if os.path.exists(cache_file):
            print("  ↪ repli sur le cache existant")
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)
        return []


def load_groupes(leg):
    """Référentiel des groupes politiques d'une législature : organeRef → nom + couleur.

    Les scrutins ne portent que des `organeRef` (PO845401) ; ce fichier donne le
    libellé, le sigle et la couleur officielle associée par l'Assemblée.
    """
    cache_file = os.path.join(CACHE, f"groupes_L{leg}.json")
    if os.path.exists(cache_file):
        age_h = (datetime.now().timestamp() - os.path.getmtime(cache_file)) / 3600
        if age_h < 24:
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)

    url = URL_ORGANES.format(L=leg)
    try:
        print(f"  Téléchargement des groupes politiques L{leg}…")
        req = urllib.request.Request(url, headers={"User-Agent": "observatoire-2027/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        groupes = {}
        for n in z.namelist():
            if "/organe/" not in n:
                continue
            try:
                o = json.load(z.open(n)).get("organe", {})
            except Exception:
                continue
            if o.get("codeType") != "GP" or str(o.get("legislature")) != str(leg):
                continue
            groupes[o["uid"]] = {
                "sigle": o.get("libelleAbrege") or "",
                "nom": o.get("libelle") or "",
                # Couleur officielle fournie par l'Assemblée nationale.
                "couleur": o.get("couleurAssociee") or "#8D949A",
            }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(groupes, f, ensure_ascii=False)
        print(f"  ✅ {len(groupes)} groupes politiques L{leg}")
        return groupes
    except Exception as e:
        print(f"  ❌ Échec groupes L{leg} : {e}")
        if os.path.exists(cache_file):
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)
        return {}


# Groupes absents du référentiel courant : organes dissous puis recréés sous un
# autre identifiant. L'Assemblée ne conserve que les organes actifs dans AMO10,
# mais les scrutins antérieurs référencent l'ancien identifiant.
# Vérifié le 15/09/2026 sur la page officielle du scrutin n° 447 (16 membres).
ALIAS_GROUPES = {
    "PO847173": {"sigle": "UDR", "nom": "Union des droites pour la République",
                 "couleur": "#3367A7"},
}


def dominante(pour, contre, abst):
    """Position dominante d'un groupe, calculée sur ses voix exprimées.

    Le champ `positionMajoritaire` publié par l'Assemblée est volontairement
    écarté : il contredit ses propres décomptes nominatifs. Vérifié le 15/09/2026
    sur le scrutin n° 8431, où le groupe Écologiste et Social y est donné
    « contre » avec 19 voix pour, 7 contre et 7 abstentions — alors que la page
    officielle du même scrutin l'affiche en « Pour ».
    """
    vals = [("pour", pour), ("contre", contre), ("abstention", abst)]
    top = max(n for _, n in vals)
    if top == 0:
        return None
    gagnants = [k for k, n in vals if n == top]
    return gagnants[0] if len(gagnants) == 1 else "partage"


def group_votes(s):
    """Vote de chaque groupe politique sur un scrutin (position + décompte)."""
    v = (s.get("ventilationVotes") or {}).get("organe") or {}
    groupes = (v.get("groupes") or {}).get("groupe") or []
    if isinstance(groupes, dict):
        groupes = [groupes]
    out = []
    for g in groupes:
        vote = g.get("vote") or {}
        dec = vote.get("decompteVoix") or {}
        pour = int(dec.get("pour") or 0)
        contre = int(dec.get("contre") or 0)
        abst = int(dec.get("abstentions") or 0)
        nv = int(dec.get("nonVotants") or 0)
        membres = int(g.get("nombreMembresGroupe") or 0)
        out.append({
            "ref": g.get("organeRef"),
            "membres": membres,
            "position_an": (vote.get("positionMajoritaire") or "").lower(),
            "dominante": dominante(pour, contre, abst),
            "pour": pour,
            "contre": contre,
            "abst": abst,
            "nv": nv,
            # Députés du groupe qui n'apparaissent dans aucun décompte du scrutin :
            # c'est ce reste qui répond à « où sont les autres ? ».
            "absents": max(0, membres - (pour + contre + abst + nv)),
        })
    out.sort(key=lambda x: -x["membres"])
    return out


def theme_of(name):
    for libelle, pat in THEMES:
        if re.search(pat, name, re.I):
            return libelle
    return None


def build(scrutins):
    """Regroupe les scrutins par texte de loi, sur le périmètre éditorial."""
    par_texte = defaultdict(list)
    n_total = len(scrutins)

    for s in scrutins:
        titre = _clean(s.get("titre"))
        if not titre:
            continue
        name, nature = law_name(titre)
        if not name:
            continue
        if not theme_of(name):
            continue
        decompte = (s.get("syntheseVote") or {}).get("decompte") or {}
        par_texte[name].append({
            "uid": s.get("uid"),
            "numero": s.get("numero"),
            "date": s.get("dateScrutin") or "",
            "titre": titre,
            "objet": short_objet(titre),
            "kind": vote_kind(titre),
            "sort": ((s.get("sort") or {}).get("code") or "").lower(),
            "pour": int(decompte.get("pour") or 0),
            "contre": int(decompte.get("contre") or 0),
            "abst": int(decompte.get("abstentions") or 0),
            "votants": int((s.get("syntheseVote") or {}).get("nombreVotants") or 0),
            "lien": (f"https://www.assemblee-nationale.fr/dyn/{LEG_CUR}/scrutins/"
                     f"{s.get('numero')}") if s.get("numero") else "",
            "groupes": group_votes(s),
        })

    textes = []
    for name, votes in par_texte.items():
        votes.sort(key=lambda v: v["date"], reverse=True)
        dates = [v["date"] for v in votes if v["date"]]
        final = next((v for v in votes if v["kind"] == "ensemble"), None)
        # Vote retenu pour la ventilation par groupe : le vote sur l'ensemble s'il
        # existe, sinon le scrutin le plus récent qui porte une ventilation.
        groupe_vote = final or next((v for v in votes if v["groupes"]), None)
        textes.append({
            "nom": name,
            "theme": theme_of(name),
            "nature": "projet" if name.startswith("projet") else "proposition",
            "nb": len(votes),
            "date_min": min(dates) if dates else "",
            "date_max": max(dates) if dates else "",
            "final": final,
            "groupe_vote": groupe_vote,
            "votes": votes,
        })

    # Les textes avec un vote final d'abord, du plus récent au plus ancien.
    textes.sort(key=lambda t: (t["date_max"] or "", t["nb"]), reverse=True)
    return textes, n_total


def reference_texts(scrutins):
    """Textes de la législature précédente, en référence (nom + vote final)."""
    par_texte = defaultdict(list)
    for s in scrutins:
        titre = _clean(s.get("titre"))
        name, _ = law_name(titre)
        if not name or not theme_of(name):
            continue
        par_texte[name].append(s)
    out = []
    for name, votes in par_texte.items():
        final = None
        for s in votes:
            if vote_kind(_clean(s.get("titre"))) == "ensemble":
                decompte = (s.get("syntheseVote") or {}).get("decompte") or {}
                final = {
                    "sort": ((s.get("sort") or {}).get("code") or "").lower(),
                    "pour": int(decompte.get("pour") or 0),
                    "contre": int(decompte.get("contre") or 0),
                    "date": s.get("dateScrutin") or "",
                    "numero": s.get("numero"),
                }
                break
        out.append({"nom": name, "theme": theme_of(name), "nb": len(votes), "final": final})
    out.sort(key=lambda t: t["nb"], reverse=True)
    return out


# ========================================================================
# RENDU
# ========================================================================

THEME_HEAD = """<script>(function(){try{var c=localStorage.getItem("theme");
if(c==="dark"||(!c&&window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches))
{document.documentElement.setAttribute("data-theme","dark");}}catch(e){}})();</script>"""

THEME_BTN = """<button type="button" class="themebtn" id="themebtn" aria-label="Changer le thème"
  title="Passer en mode clair ou sombre">&#9681;</button>"""

THEME_JS = """<script>(function(){var b=document.getElementById("themebtn");if(!b)return;
b.addEventListener("click",function(){var r=document.documentElement;
var sombre=r.getAttribute("data-theme")==="dark";
if(sombre){r.removeAttribute("data-theme");}else{r.setAttribute("data-theme","dark");}
try{localStorage.setItem("theme",sombre?"light":"dark");}catch(e){}
b.setAttribute("title",sombre?"Passer en mode sombre":"Passer en mode clair");});})();</script>"""

CSS = """
:root{--bg:#f3efe5;--paper:#fffdf8;--ink:#171713;--muted:#676459;--line:#d9d2c3;
--red:#d73d2f;--red-text:#c53325;--green:#166b4e;--amber:#a05a0d;--blue:#245d8c;
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
.navlinks a{white-space:nowrap}
@media(max-width:760px){
  .nav{min-height:auto;flex-wrap:wrap;gap:4px;padding:10px 0 6px;position:relative}
  .themebtn{position:absolute;right:0;top:8px}
  .brand{width:100%}
  .navlinks{flex-wrap:nowrap;overflow-x:auto;width:100%;gap:16px;padding-bottom:4px;
    scrollbar-width:none}
  .navlinks::-webkit-scrollbar{display:none}
}
.hero{text-align:center;padding:38px 0 18px}
.hero h1{font-size:1.8rem;font-weight:800;letter-spacing:-.04em;margin:0;line-height:1.25}
.hero .lede{font-size:.95rem;color:var(--muted);max-width:40em;margin:10px auto 0}
.card{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:26px;
  margin-top:16px}
.card h2{margin:0 0 6px;font-size:1.05rem;font-weight:700;letter-spacing:-.02em}
.card p{margin:6px 0}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 16px}
.chip{font-size:.72rem;padding:4px 11px;border-radius:999px;border:1px solid var(--line);
  color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.74rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
th.num{text-align:right;letter-spacing:normal}
td.date{white-space:nowrap;color:var(--muted)}
.small{font-size:.85rem}
.muted{color:var(--muted)}
.pill{display:inline-block;font-size:.7rem;padding:3px 10px;border-radius:999px;
  border:1px solid var(--line);color:var(--muted);text-transform:uppercase;letter-spacing:.06em;
  white-space:nowrap}
.pill.adopte{background:color-mix(in srgb,var(--green) 12%,var(--paper));border-color:var(--green);color:var(--green)}
.pill.rejete{background:color-mix(in srgb,var(--red) 12%,var(--paper));border-color:var(--red);color:var(--red)}
.pill.pos-pour{background:color-mix(in srgb,var(--green) 14%,var(--paper));border-color:var(--green);color:var(--green)}
.pill.pos-contre{background:color-mix(in srgb,var(--red) 14%,var(--paper));border-color:var(--red);color:var(--red)}
.pill.pos-abst{background:color-mix(in srgb,var(--amber) 16%,var(--paper));border-color:var(--amber);color:var(--amber)}
.pill.pos-nv{background:color-mix(in srgb,var(--muted) 10%,var(--paper));border-color:var(--line);color:var(--muted)}
td.grp{border-left:4px solid var(--line);padding-left:10px}
td.barcell{width:130px}
.bar{display:flex;height:9px;border-radius:5px;overflow:hidden;background:var(--track);min-width:84px}
.bar i{display:block;height:100%}
.bar i.p{background:var(--green)}
.bar i.c{background:var(--red)}
.bar i.a{background:var(--amber)}
.bar i.n{background:var(--blue)}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin:10px 0 0;max-width:none}
.legend .sw{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;
  vertical-align:middle}
.legend .sw.p{background:var(--green)}
.legend .sw.c{background:var(--red)}
.legend .sw.a{background:var(--amber)}
.legend .sw.n{background:var(--blue)}
.legend .sw.abs{background:var(--track);border:1px solid var(--line)}
details.gv{border-top:none;padding-top:0;margin-top:14px}
details.gv summary{color:var(--ink);font-weight:600}
@media(max-width:899px){.card{overflow-x:auto}}
details{margin-top:14px;border-top:1px solid var(--line);padding-top:10px}
summary{cursor:pointer;font-size:.85rem;color:var(--muted);list-style:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸ ";color:var(--muted)}
details[open] summary::before{content:"▾ "}
summary:hover{color:var(--ink)}
.stat{display:flex;gap:26px;flex-wrap:wrap;margin:4px 0 0}
.stat div{font-size:.82rem;color:var(--muted)}
.stat b{display:block;font-size:1.2rem;color:var(--ink);font-variant-numeric:tabular-nums}
.etat{background:var(--excl-bg);border:1px solid var(--line);border-left:4px solid var(--amber);
  border-radius:12px;padding:14px 18px;margin:16px 0 0}
.etat.ok{border-left-color:var(--green)}
.etat>p{margin:0 0 8px;font-size:.9rem}
.etat>p:last-child{margin-bottom:0}
html[data-theme="dark"]{
  --bg:#0a1024;--paper:#11183a;--ink:#edf0f8;--muted:#9ba4b8;--line:#2f3550;
  --red:#e4584c;--red-text:#e4584c;--green:#4fbf95;--amber:#c8a84e;--blue:#6fa8dc;
  --track:#1e2747;--topbar:rgba(17,24,58,.9);--bg-top:#0d1430;--excl-bg:#2a2415;
}
.themebtn{background:none;border:1px solid var(--line);border-radius:50%;width:34px;height:34px;
  cursor:pointer;font-size:16px;color:var(--muted);display:flex;align-items:center;justify-content:center;
  transition:color .2s,border-color .2s}
.themebtn:hover{color:var(--ink);border-color:var(--muted)}
.tag{display:inline-block;font-size:.72rem;color:var(--muted);border:1px solid var(--line);
  border-radius:6px;padding:2px 7px;margin-right:6px}
footer{padding:34px 0 60px;color:var(--muted);font-size:.84rem;text-align:right}
"""


def fr_date(iso):
    if not iso or len(iso) < 10:
        return iso or ""
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


MOIS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre")


def fr_date_longue(iso):
    """« 2026-10-01 » → « 1er octobre 2026 ». Pour la prose ; fr_date reste la forme courte."""
    if not iso or len(iso) < 10:
        return iso or ""
    try:
        jour, mois = int(iso[8:10]), int(iso[5:7])
        return f"{'1er' if jour == 1 else jour} {MOIS_FR[mois - 1]} {iso[:4]}"
    except (ValueError, IndexError):
        return fr_date(iso)


def pill(sort):
    if "adopt" in sort:
        return '<span class="pill adopte">Adopté</span>'
    if "rejet" in sort:
        return '<span class="pill rejete">Rejeté</span>'
    return f'<span class="pill">{sort or "—"}</span>'


def bandeau_etat(dernier, auj=None, date_controle=""):
    """État de la veille : dernier scrutin publié et situation du Parlement.

    Sans ce bandeau, une période couverte qui s'arrête net se lit comme une veille en
    panne. Entre deux sessions, la page doit dire que l'Assemblée ne siège pas, et
    jusqu'à quand.
    """
    if not dernier:
        return ""
    try:
        d = datetime.strptime(dernier[:10], "%Y-%m-%d").date()
        ouv = datetime.strptime(OUVERTURE_SESSION, "%Y-%m-%d").date()
    except ValueError:
        return ""
    today = auj or datetime.now().date()
    jours = (today - d).days
    depuis = ("aujourd'hui" if jours == 0
              else "hier" if jours == 1
              else "il y a %d jours" % jours)

    if today < ouv:
        classe = "etat"
        situation = f"""
  <p>Le Parlement ne siège pas. La session ordinaire 2025-2026 s'est achevée le
  {fr_date_longue(DERNIERE_SEANCE)}, le gouvernement a renoncé à convoquer une session
  extraordinaire en septembre, et la session ordinaire 2026-2027 ouvre le
  {fr_date_longue(OUVERTURE_SESSION)}. Entre ces deux dates, aucun scrutin public n'est prononcé :
  il n'y a donc rien à ajouter ici. Les commissions peuvent se réunir hors session, mais
  leurs travaux ne donnent pas lieu à des scrutins publics.</p>
  <p class="small muted">Situation : {SOURCE_INTERSESSION}.</p>"""
    else:
        classe, situation = "etat ok", ""

    return f"""
<section class="{classe}">
  <p><b>Dernier scrutin publié : {fr_date(dernier)}</b> ({depuis}).</p>{situation}
  <p class="small muted">Données ouvertes de l'Assemblée nationale{f", relevées le {fr_date(date_controle)}" if date_controle else ""}.
  Le premier scrutin de la rentrée apparaîtra ici automatiquement, sans intervention.</p>
</section>"""


def render(textes, refs, n_total_cur, n_total_ref, gmap, dernier_scrutin=None,
           date_controle=""):
    nb_scrutins = sum(t["nb"] for t in textes)
    periodes = [t["date_max"] for t in textes if t["date_max"]]
    p_max = max(periodes) if periodes else ""
    periodes_min = [t["date_min"] for t in textes if t["date_min"]]
    p_min = min(periodes_min) if periodes_min else ""

    POS = {
        "pour": ("pos-pour", "Pour"),
        "contre": ("pos-contre", "Contre"),
        "abstention": ("pos-abst", "Abstention"),
        "partage": ("pos-nv", "Partagé"),
    }

    def groupe_block(t):
        """Ventilation du vote retenu par groupe politique."""
        gv = t.get("groupe_vote")
        if not gv or not gv.get("groupes"):
            return ""
        quoi = ("vote sur l'ensemble du texte" if gv["kind"] == "ensemble"
                else "dernier scrutin enregistré")
        lignes = ""
        for g in gv["groupes"]:
            info = gmap.get(g["ref"]) or ALIAS_GROUPES.get(g["ref"]) or {}
            sigle = info.get("sigle") or (g["ref"] or "—")
            nom = info.get("nom") or ""
            coul = info.get("couleur") or "#8D949A"
            cls, lab = POS.get(g["dominante"], ("pos-nv", "—"))
            m = g["membres"] or 1

            def pc(x, m=m):
                return round(100 * x / m, 1)

            def val(x):
                return x if x else "—"

            titre = (f'{g["pour"]} pour, {g["contre"]} contre, {g["abst"]} abstentions, '
                     f'{g["nv"]} non-votants, {g["absents"]} absents')
            barre = (f'<span class="bar" title="{titre}">'
                     f'<i class="p" style="width:{pc(g["pour"])}%"></i>'
                     f'<i class="c" style="width:{pc(g["contre"])}%"></i>'
                     f'<i class="a" style="width:{pc(g["abst"])}%"></i>'
                     f'<i class="n" style="width:{pc(g["nv"])}%"></i></span>')
            lignes += (
                f'<tr><td class="grp" style="border-left-color:{coul}">'
                f'<b>{sigle}</b> <span class="small muted">{nom}</span></td>'
                f'<td><span class="pill {cls}">{lab}</span></td>'
                f'<td class="num">{val(g["pour"])}</td>'
                f'<td class="num">{val(g["contre"])}</td>'
                f'<td class="num">{val(g["abst"])}</td>'
                f'<td class="num">{val(g["nv"])}</td>'
                f'<td class="num">{val(g["absents"])}</td>'
                f'<td class="num muted">{g["membres"]}</td>'
                f'<td class="barcell">{barre}</td></tr>\n')

        return f"""
  <details open class="gv">
    <summary>Vote par groupe politique</summary>
    <p class="small muted" style="max-width:none;margin:8px 0 6px">
      {quoi}, du {fr_date(gv["date"])}. Chaque député du groupe est compté une fois :
      pour + contre + abstentions + non-votants + absents = effectif.</p>
    <table>
      <tr><th>Groupe</th><th>Position dominante</th><th class="num">Pour</th>
      <th class="num">Contre</th><th class="num">Abst.</th><th class="num">Non-vot.</th>
      <th class="num">Absents</th><th class="num">Effectif</th><th>Répartition</th></tr>
      {lignes}
    </table>
    <p class="legend small muted">
      <span class="sw p"></span>pour
      <span class="sw c"></span>contre
      <span class="sw a"></span>abstention
      <span class="sw n"></span>non-votant (présent, sans vote)
      <span class="sw abs"></span>absent (dans aucun décompte du scrutin)
    </p>
    <p class="small muted" style="max-width:none;margin-top:8px">
      « Position dominante » est calculée sur les voix exprimées du groupe (partagée en cas
      d'égalité) — et non reprise du champ « position majoritaire » publié par l'Assemblée,
      qui contredit ses propres décomptes. Un groupe qui se divise reste donc lisible ligne
      par ligne. Un député absent, ou présent sans voter, ne soutient ni ne rejette le texte :
      ne pas lire les colonnes « absents » et « non-votants » comme un vote.</p>
  </details>"""

    bandeau = bandeau_etat(dernier_scrutin, date_controle=date_controle)

    cards = ""
    for t in textes:
        final = t["final"]
        if final:
            entete = f'{pill(final["sort"])} <span class="small muted">vote final du ' \
                     f'{fr_date(final["date"])} — {final["pour"]} pour, {final["contre"]} contre</span>'
        else:
            entete = '<span class="small muted">aucun vote sur l\'ensemble enregistré</span>'

        lignes = ""
        for v in t["votes"]:
            lien = f'<a href="{v["lien"]}">{v["objet"]}</a>' if v["lien"] else v["objet"]
            kind = {"ensemble": "ensemble", "motion": "motion", "article": "article",
                    "amendement": "amendement", "autre": "vote"}[v["kind"]]
            lignes += (f'<tr><td class="date">{fr_date(v["date"])}</td>'
                       f'<td><span class="tag">{kind}</span>{lien}</td>'
                       f'<td>{pill(v["sort"])}</td>'
                       f'<td class="num">{v["pour"]}</td>'
                       f'<td class="num">{v["contre"]}</td>'
                       f'<td class="num">{v["abst"]}</td></tr>\n')

        cards += f"""
<section class="card">
  <h2>{t["nom"]}</h2>
  <div class="chips"><span class="chip">{t["theme"]}</span>
    <span class="chip">{t["nb"]} scrutin{"s" if t["nb"] > 1 else ""}</span></div>
  <p style="margin:0">{entete}</p>
  {groupe_block(t)}
  <details>
    <summary>Voir les {t["nb"]} scrutins ({fr_date(t["date_min"])} → {fr_date(t["date_max"])})</summary>
    <table>
      <tr><th>Date</th><th>Objet du vote</th><th>Sort</th>
      <th class="num">Pour</th><th class="num">Contre</th><th class="num">Abst.</th></tr>
      {lignes}
    </table>
  </details>
</section>"""

    refs_html = ""
    for r in refs:
        f = r["final"]
        if f:
            outcome = (f'{pill(f["sort"])} <span class="small muted">vote final du '
                       f'{fr_date(f["date"])} — {f["pour"]} pour, {f["contre"]} contre</span>')
        else:
            outcome = '<span class="small muted">—</span>'
        refs_html += (f'<tr><td>{r["nom"]}<br><span class="small muted">{r["theme"]}</span></td>'
                      f'<td class="num">{r["nb"]}</td><td>{outcome}</td></tr>\n')

    themes_chips = "".join(f'<span class="chip">{lib}</span>' for lib, _ in THEMES)

    html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="{G.meta_description('/observatoire/lois/')}">
<title>Veille législative — les textes « technologie et pouvoir » | Observatoire 2027</title>
<link rel="canonical" href="https://dileviathan.fr/observatoire/lois/">
{G.ld_json("/observatoire/lois/")}
{G.matomo()}
<style>{CSS}</style>
{THEME_HEAD}</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand"><a href="/observatoire/" style="text-decoration:none">Présidentielle 2027</a> <span>· veille législative</span></div>
  <div class="navlinks">
    <a href="/observatoire/">Accueil</a>
    <a href="/observatoire/sondages/">Agrégation</a>
    <a href="/observatoire/candidats/">Les candidats</a>
    <a href="/observatoire/workflow/">Workflow</a>
    <a href="/observatoire/backtest/">Rétro-test 2022</a>
    <a href="/observatoire/lois/" style="font-weight:700;color:var(--ink)">Veille législative</a>
  </div>{THEME_BTN}
</div></div>

<header class="wrap hero">
  <h1>Ce que le Parlement vote</h1>
  <p class="lede">Les textes de loi qui touchent au numérique, à l'intelligence artificielle,
  aux données, à la surveillance et à la souveraineté informationnelle — suivis dans les
  données ouvertes de l'Assemblée nationale, scrutins publics compris.</p>
</header>

<main class="wrap">
{bandeau}
<section class="card">
  <h2>Législature en cours (depuis juillet 2024)</h2>
  <p class="small muted" style="max-width:none">Scrutins publics de la 17<sup>e</sup> législature
  rattachés au périmètre ci-dessous, regroupés par texte de loi.</p>
  <div class="stat">
    <div><b>{len(textes)}</b>textes suivis</div>
    <div><b>{nb_scrutins}</b>scrutins publics</div>
    <div><b>{n_total_cur}</b>scrutins au total dans la législature</div>
    <div><b>{fr_date(p_min)} → {fr_date(date_controle or p_max)}</b>période couverte</div>
  </div>
  <p class="small muted" style="max-width:none;margin-top:12px">
  La période couverte s'arrête à la date du dernier contrôle de la source, et non à celle du dernier
  vote : elle dit jusqu'où les données ont été vérifiées. La date du dernier scrutin publié, elle,
  figure dans le bandeau ci-dessus — quand le Parlement ne siège pas, les deux ne coïncident pas.</p>
  <div class="chips" style="margin-top:14px">{themes_chips}</div>
</section>
{cards}

<section class="card">
  <h2>Textes de référence de la législature précédente</h2>
  <p class="small muted" style="max-width:none">Les scrutins de la 16<sup>e</sup> législature
  (2022-2024) ne sont plus au centre de la veille, mais deux textes continuent de structurer le
  droit du numérique : ils restent listés ici pour mémoire.</p>
  <table>
    <tr><th>Texte</th><th class="num">Scrutins</th><th>Vote final</th></tr>
    {refs_html}
  </table>
</section>

<section class="card" id="methode">
  <h2>Méthode</h2>
  <p class="small muted" style="max-width:none">
  Source unique : les scrutins publics publiés en données ouvertes par l'Assemblée nationale
  (<a href="https://data.assemblee-nationale.fr">data.assemblee-nationale.fr</a>, licence Etalab).
  Chaque scrutin est rattaché au texte de loi qu'il modifie ; les textes hors périmètre
  technopolitique sont écartés. Aucun chiffre n'est repris d'une source secondaire.<br>
  Sélection thématique, appliquée à l'intitulé des textes : numérique et plateformes, réseaux
  sociaux et protection des mineurs, intelligence artificielle et algorithmes, données et vie
  privée, surveillance et biométrie, cybersécurité, médias et souveraineté informationnelle.<br>
  <strong>Limite assumée :</strong> un texte dont l'intitulé ne dit rien du numérique peut contenir
  des dispositions qui le concernent — il échappe alors à cette veille. Le filtre porte sur le titre,
  pas sur le contenu article par article.<br>
  <strong>Votes par groupe :</strong> ils viennent des décomptes nominatifs du scrutin, croisés avec
  le référentiel des organes de l'Assemblée (noms et couleurs officielles des groupes). La position
  affichée pour chaque groupe est recalculée à partir de ses voix exprimées : le champ « position
  majoritaire » publié par l'Assemblée a été écarté après vérification, il contredit ses propres
  décomptes nominatifs.<br>
  Page régénérée automatiquement chaque semaine.</p>
</section>
</main>

<footer class="wrap">
  <p><a href="/fr/mentions-legales">Mentions légales</a></p>
</footer>
{THEME_JS}</body>
</html>"""

    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  → {os.path.join(SITE, 'index.html')} ({len(html)} caractères)")


# ========================================================================
if __name__ == "__main__":
    print("=== Veille législative — Assemblée nationale ===")
    cur = load_scrutins(LEG_CUR)
    ref = load_scrutins(LEG_REF)
    gmap = load_groupes(LEG_CUR)

    textes, n_total_cur = build(cur)
    refs = reference_texts(ref)
    n_total_ref = len(ref)

    # ------------------------------------------------------------------
    # Garde-fou : ne jamais écraser une page correcte par une page vide.
    # Si la source est injoignable ET le cache absent, on sort en erreur sans
    # régénérer — la page précédente reste en ligne, et le cron alerte.
    # ------------------------------------------------------------------
    echecs = []
    if not cur:
        echecs.append(f"scrutins L{LEG_CUR} indisponibles (source et cache)")
    if not textes:
        echecs.append("aucun texte retenu après filtrage")
    if echecs:
        print("  ❌ ÉCHEC — page non régénérée, la version précédente reste en ligne")
        for e in echecs:
            print(f"     · {e}")
        raise SystemExit(1)

    print(f"  → {len(textes)} textes suivis, {sum(t['nb'] for t in textes)} scrutins (L{LEG_CUR})")
    print(f"  → {len(refs)} textes de référence (L{LEG_REF})")

    # Avertissements non bloquants : ils s'affichent dans la sortie du cron.
    if not gmap:
        print("  ⚠️  référentiel des groupes indisponible — noms de groupes manquants")
    connus = set(gmap) | set(ALIAS_GROUPES)
    inconnus = {g["ref"] for t in textes for v in t["votes"]
                for g in v.get("groupes", []) if g["ref"] and g["ref"] not in connus}
    if inconnus:
        print(f"  ⚠️  groupes non résolus : {sorted(inconnus)} — compléter ALIAS_GROUPES")

    dates_cur = [s.get("dateScrutin", "") for s in cur if isinstance(s, dict)]
    dates_cur = [d for d in dates_cur if d]
    dernier_scrutin = max(dates_cur) if dates_cur else ""

    # Date du dernier contrôle RÉEL de la source : celle du cache téléchargé. Si le cache a
    # moins de 24 h, rien n'a été re-téléchargé — annoncer la date du jour serait faux.
    cache_l17 = os.path.join(CACHE, f"scrutins_L{LEG_CUR}.json")
    date_controle = (datetime.fromtimestamp(os.path.getmtime(cache_l17)).strftime("%Y-%m-%d")
                     if os.path.exists(cache_l17) else "")

    render(textes, refs, n_total_cur, n_total_ref, gmap, dernier_scrutin, date_controle)
    print(f"  → dernier scrutin publié par la source : {dernier_scrutin or 'inconnu'}")
    print(f"  → période couverte jusqu'au contrôle du : {date_controle or 'inconnu'}")

    with open(os.path.join(DATA, "veille_lois.json"), "w", encoding="utf-8") as f:
        json.dump({
            "legislature": LEG_CUR,
            "date_generation": datetime.now().isoformat()[:19],
            "scrutins_total": n_total_cur,
            "groupes": gmap,
            "textes": [{k: v for k, v in t.items() if k != "votes"} for t in textes],
            "texte_detail": {t["nom"]: t["votes"] for t in textes},
            "references": refs,
        }, f, ensure_ascii=False, indent=1)
    print("Terminé.")