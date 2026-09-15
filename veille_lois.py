#!/usr/bin/env python3
"""Veille législative — Assemblée nationale
Télécharge les données open data, filtre par mots-clés « tech/pouvoir »
et génère une page statique pour /observatoire/lois/.

Calqué sur le modèle de l'observatoire sondages :
- Une source unique (data.assemblee-nationale.fr)
- Un générateur qui produit du HTML statique
- Un cron quotidien
"""

import json, os, urllib.request, zipfile, io, re
from datetime import datetime, date
from collections import defaultdict

# ---------- chemins ----------
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
SITE = os.path.join(BASE, "site", "lois")
CACHE = os.path.join(DATA, "lois")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(SITE, exist_ok=True)

# ---------- sources ----------
SRC_SCRUTINS = "https://data.assemblee-nationale.fr/static/openData/repository/16/loi/scrutins/Scrutins.json.zip"
SRC_DOSSIERS = "https://data.assemblee-nationale.fr/static/openData/repository/16/loi/dossiers_legislatifs/DossiersLegislatifs.json.zip"

# Mots-clés Diléviathan : ce qui touche à la surveillance, l'IA, les données, le pouvoir numérique
MOTS_CLEFS = [
    "intelligence artificielle", "algorithme", "données personne",
    "surveillance", "vidéosurveillance", "reconnaissance faciale",
    "biométrique", "cybersécurité", "cyber", "sécuriser et réguler l'espace numérique",
    "plateforme numérique", "réseau social",
    "contenu en ligne", "désinformation", "neutralité",
    "donnée publique", "open data",
    "haine en ligne", "modération",
    "souveraineté numérique", "cloud",
    "RGPD", "protection des données",
    "IA générative", "deepfake", "infrastructure numérique",
    "données sensibles", "cryptographie", "chiffrement",
    "numérique", "score social",
    "loi numérique", "régulation numérique",
    "criminalité numérique", "espace numérique",
    "tech", "Big Data", "identité numérique",
    "jeux vidéo", "plateforme en ligne",
    "commerce électronique", "économie numérique",
]


def _load_scrutins(url):
    """Télécharge et parse tous les scrutins depuis le zip de l'AN.
    Le zip contient ~4000 fichiers JSON individuels (un par scrutin).
    """
    cache_file = os.path.join(CACHE, "scrutins_cache.json")
    
    if os.path.exists(cache_file):
        age_h = (datetime.now().timestamp() - os.path.getmtime(cache_file)) / 3600
        if age_h < 24:
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)
    
    try:
        print(f"  Téléchargement {url}…")
        req = urllib.request.Request(url, headers={"User-Agent": "observatoire-2027/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
        
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = [n for n in z.namelist() if n.endswith(".json")]
        
        scrutins = []
        errors = 0
        for n in names:
            try:
                data = json.load(z.open(n))
                scr = data.get("scrutin")
                if scr:
                    scrutins.append(scr)
            except Exception:
                errors += 1
        
        if errors:
            print(f"  ⚠️  {errors} fichiers ignorés (erreur parse)")
        
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"scrutins": scrutins, "nb": len(scrutins)}, f, ensure_ascii=False)
        print(f"  ✅ {len(scrutins)} scrutins chargés")
        return scrutins
    except Exception as e:
        print(f"  ❌ Échec téléchargement: {e}")
        if os.path.exists(cache_file):
            print(f"  ↪ Fallback cache")
            with open(cache_file, encoding="utf-8") as f:
                d = json.load(f)
                return d.get("scrutins", [])
        return []


def match_keyword(text):
    """Vérifie si le texte contient l'un des mots-clés."""
    if not text:
        return False
    text_lower = text.lower()
    for kw in MOTS_CLEFS:
        if kw in text_lower:
            return kw  # on retourne le mot-clé pour debug
    return False


def fetch_and_filter():
    """Télécharge les données et filtre par mots-clés."""
    scrutins = _load_scrutins(SRC_SCRUTINS)
    
    resultats = {
        "scrutins": [],
        "date_generation": datetime.now().isoformat()[:19],
        "total_scrutins": len(scrutins),
    }
    
    matched = []
    for s in scrutins:
        titre = (s.get("titre") or "") + " " + ((s.get("objet") or {}).get("libelle") or "")
        kw = match_keyword(titre)
        if kw:
            sort_code = s.get("sort", {}).get("code", "")
            matched.append({
                "uid": s.get("uid"),
                "numero": s.get("numero"),
                "date": s.get("dateScrutin", ""),
                "titre": s.get("titre", ""),
                "sort_code": sort_code,
                "sort_label": s.get("sort", {}).get("libelle", ""),
                "pour": (s.get("syntheseVote", {}) . get("decompte", {}) . get("pour", 0)),
                "contre": (s.get("syntheseVote", {}) . get("decompte", {}) . get("contre", 0)),
                "mot_clef": kw,
                "source": f"https://www.assemblee-nationale.fr/dyn/16/scrutins/{s.get('numero')}" if s.get("numero") else ""
            })
    
    matched.sort(key=lambda x: x["date"], reverse=True)
    resultats["scrutins"] = matched
    
    print(f"     → {len(matched)} scrutins filtrés (sur {len(scrutins)})")
    
    return resultats


# ========================================================================
# RENDU HTML (calqué sur les pages existantes de l'observatoire)
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
.hero{text-align:center;padding:40px 0 20px}
.hero h1{font-size:1.8rem;font-weight:800;letter-spacing:-.04em;margin:0;line-height:1.25;color:var(--ink)}
.hero .lede{font-size:.95rem;color:var(--muted);max-width:36em;margin:10px auto 0}
.card{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:26px;
  margin-top:16px}
.card h2{margin:0 0 14px;font-size:1.15rem;font-weight:700;letter-spacing:-.02em}
.card p{margin:6px 0}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:middle}
th{font-size:.76rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
th.num{text-align:right;letter-spacing:normal}
td.date{white-space:nowrap}
.small{font-size:.85rem}
.muted{color:var(--muted)}
.pill{display:inline-block;font-size:.7rem;padding:3px 10px;border-radius:999px;
  border:1px solid var(--line);color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.pill.adopte{background:color-mix(in srgb,var(--green) 10%,var(--paper));border-color:var(--green);color:var(--green)}
.pill.rejete{background:color-mix(in srgb,var(--red) 10%,var(--paper));border-color:var(--red);color:var(--red)}
html[data-theme="dark"]{
  --bg:#0a1024;--paper:#11183a;--ink:#edf0f8;--muted:#9ba4b8;--line:#2f3550;
  --red:#e4584c;--red-text:#e4584c;--green:#4fbf95;--amber:#c8a84e;--blue:#6fa8dc;
  --track:#1e2747;--topbar:rgba(17,24,58,.9);--bg-top:#0d1430;--excl-bg:#2a2415;
}
.themebtn{background:none;border:1px solid var(--line);border-radius:50%;width:34px;height:34px;
  cursor:pointer;font-size:16px;color:var(--muted);display:flex;align-items:center;justify-content:center;
  transition:color .2s,border-color .2s}
.themebtn:hover{color:var(--ink);border-color:var(--muted)}
footer{padding:34px 0 60px;color:var(--muted);font-size:.84rem;text-align:right}
"""


def render_page(resultats):
    """Génère la page HTML statique."""
    scrutins = resultats.get("scrutins", [])
    total = resultats.get("total_scrutins", 0)
    n = len(scrutins)
    
    def pill_sort(code):
        if "adopt" in str(code).lower():
            return '<span class="pill adopte">Adopté</span>'
        elif "rejet" in str(code).lower():
            return '<span class="pill rejete">Rejeté</span>'
        else:
            return f'<span class="pill">{code}</span>'
    
    lignes = ""
    for s in scrutins:
        src = s.get("source", "")
        titre = s.get("titre", "")[:100]
        date = s.get("date", "")
        
        titre_html = f'<a href="{src}">{titre}…</a>' if len(s.get("titre",""))>100 else f'<a href="{src}">{titre}</a>'
        if not src:
            titre_html = titre
        
        lignes += (
            f'<tr><td class="date">{date}</td>'
            f'<td>{titre_html}</td>'
            f'<td>{pill_sort(s.get("sort_code",""))}</td>'
            f'<td class="num">{s.get("pour",0)}</td>'
            f'<td class="num">{s.get("contre",0)}</td></tr>\n'
        )
    
    if not lignes:
        lignes = '<tr><td colspan="5" style="text-align:center;padding:30px 0;color:var(--muted)">Aucun scrutin correspondant aux mots-clés pour le moment.</td></tr>'
    
    html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<title>Veille législative — textes « tech et pouvoir » | Observatoire 2027</title>
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
  <h1>Ce que le Parlement prépare</h1>
  <p class="lede">Scrutins, amendements et dossiers législatifs qui touchent à la
  surveillance, à l'intelligence artificielle, aux données personnelles et à la
  souveraineté numérique — extraits des données ouvertes de
  l'Assemblée nationale.</p>
</header>

<main class="wrap">
<section class="card">
  <h2>Scrutins repérés <span class="muted small">({n} sur {total})</span></h2>
  <table>
    <tr><th>Date</th><th>Texte</th><th>Sort</th><th class="num">Pour</th><th class="num">Contre</th></tr>
    {lignes}
  </table>
</section>

<section class="card">
  <h2>Méthode et mots-clés</h2>
  <p class="small muted" style="max-width:none">
  Les scrutins sont filtrés dans les données ouvertes (licence Etalab) de l'Assemblée
  nationale — <a href="https://data.assemblee-nationale.fr">data.assemblee-nationale.fr</a>.
  Mots-clés retenus : IA, algorithme, surveillance, données personnelles, cyber,
  espace numérique, plateforme, reconnaissance faciale, biométrie, désinformation,
  souveraineté numérique, RGPD, cryptographie, deepfake — tout ce qui touche au
  périmètre Diléviathan.<br>
  Page régénérée automatiquement.</p>
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
    print("=== Veille législative ===")
    resultats = fetch_and_filter()
    render_page(resultats)
    
    out = os.path.join(DATA, "veille_lois.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=1)
    print(f"  → {out}")
    print("Terminé.")