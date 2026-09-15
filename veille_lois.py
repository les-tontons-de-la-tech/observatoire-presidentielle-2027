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
from datetime import datetime
from collections import defaultdict, Counter

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
        out.append({
            "ref": g.get("organeRef"),
            "membres": int(g.get("nombreMembresGroupe") or 0),
            "position": (vote.get("positionMajoritaire") or "").lower(),
            "pour": int(dec.get("pour") or 0),
            "contre": int(dec.get("contre") or 0),
            "abst": int(dec.get("abstentions") or 0),
            "nv": int(dec.get("nonVotants") or 0),
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


def pill(sort):
    if "adopt" in sort:
        return '<span class="pill adopte">Adopté</span>'
    if "rejet" in sort:
        return '<span class="pill rejete">Rejeté</span>'
    return f'<span class="pill">{sort or "—"}</span>'


def render(textes, refs, n_total_cur, n_total_ref, gmap):
    nb_scrutins = sum(t["nb"] for t in textes)
    periodes = [t["date_max"] for t in textes if t["date_max"]]
    p_max = max(periodes) if periodes else ""
    periodes_min = [t["date_min"] for t in textes if t["date_min"]]
    p_min = min(periodes_min) if periodes_min else ""

    POS = {
        "pour": ("pos-pour", "Pour"),
        "contre": ("pos-contre", "Contre"),
        "abstention": ("pos-abst", "Abstention"),
        "nonvotant": ("pos-nv", "Non votant"),
        "non-votant": ("pos-nv", "Non votant"),
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
            info = gmap.get(g["ref"]) or {}
            sigle = info.get("sigle") or "—"
            nom = info.get("nom") or ""
            coul = info.get("couleur") or "#8D949A"
            cls, lab = POS.get(g["position"], ("pos-nv", g["position"] or "—"))
            exprime = g["pour"] + g["contre"] + g["abst"]
            participe = exprime + g["nv"]

            def pc(x):
                return round(100 * x / exprime) if exprime else 0

            barre = (f'<span class="bar">'
                     f'<i class="p" style="width:{pc(g["pour"])}%"></i>'
                     f'<i class="c" style="width:{pc(g["contre"])}%"></i>'
                     f'<i class="a" style="width:{pc(g["abst"])}%"></i></span>')
            lignes += (
                f'<tr><td class="grp" style="border-left-color:{coul}">'
                f'<b>{sigle}</b> <span class="small muted">{nom}</span></td>'
                f'<td><span class="pill {cls}">{lab}</span></td>'
                f'<td class="num">{participe} <span class="muted">/ {g["membres"]}</span></td>'
                f'<td class="num">{g["pour"] or "—"}</td>'
                f'<td class="num">{g["contre"] or "—"}</td>'
                f'<td class="num">{g["abst"] or "—"}</td>'
                f'<td class="barcell">{barre}</td></tr>\n')

        return f"""
  <details open class="gv">
    <summary>Vote par groupe politique</summary>
    <p class="small muted" style="max-width:none;margin:8px 0 6px">
      {quoi}, du {fr_date(gv["date"])}. Position majoritaire de chaque groupe et décompte
      de ses voix. La colonne « votants » rapporte les membres du groupe ayant pris part
      au vote à son effectif : les députés absents ne figurent dans aucun décompte.</p>
    <table>
      <tr><th>Groupe</th><th>Position</th><th class="num">Votants</th><th class="num">Pour</th>
      <th class="num">Contre</th><th class="num">Abst.</th><th>Répartition</th></tr>
      {lignes}
    </table>
    <p class="small muted" style="max-width:none;margin-top:8px">
      Position majoritaire = position dominante du groupe, sans préjuger des voix
      divergentes, visibles dans les colonnes de décompte.</p>
  </details>"""

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
<title>Veille législative — les textes « technologie et pouvoir » | Observatoire 2027</title>
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
<section class="card">
  <h2>Législature en cours (depuis juillet 2024)</h2>
  <p class="small muted" style="max-width:none">Scrutins publics de la 17<sup>e</sup> législature
  rattachés au périmètre ci-dessous, regroupés par texte de loi.</p>
  <div class="stat">
    <div><b>{len(textes)}</b>textes suivis</div>
    <div><b>{nb_scrutins}</b>scrutins publics</div>
    <div><b>{n_total_cur}</b>scrutins au total dans la législature</div>
    <div><b>{fr_date(p_min)} → {fr_date(p_max)}</b>période couverte</div>
  </div>
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
  Page régénérée automatiquement chaque semaine.</p>
</section>
</main>

<footer class="wrap small muted">
  <p>Observatoire de la présidentielle 2027 · <a href="/observatoire/">dileviathan.fr/observatoire</a></p>
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

    print(f"  → {len(textes)} textes suivis, {sum(t['nb'] for t in textes)} scrutins (L{LEG_CUR})")
    print(f"  → {len(refs)} textes de référence (L{LEG_REF})")

    render(textes, refs, n_total_cur, n_total_ref, gmap)

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