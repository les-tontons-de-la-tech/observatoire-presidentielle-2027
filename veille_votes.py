#!/usr/bin/env python3
"""Lois votées — la structure de la page de référence, appliquée à tous les textes.

Ce que Christophe a demandé, dans ses mots : « ajouter à la fin de chaque proposition de loi
l'ensemble des scrutins votés ». On ne se limite donc plus au vote sur l'ensemble : chaque
texte porte TOUS ses scrutins, repliés, avec date, objet, sort et décompte — comme la page
de production de l'observatoire.

Corrections par rapport à la version précédente :
  - fraîcheur : la source est lue jusqu'au dernier scrutin publié, tous types confondus
    (l'ancienne version annonçait le 29/10 quand l'Assemblée avait voté le 30/10) ;
  - présentation identique à la prod : titre, puces, pastille de sort, tableau par groupe,
    puis la liste des scrutins dans un <details> ;
  - le tableau par groupe porte sur le vote d'ensemble s'il existe, sinon sur le dernier
    scrutin enregistré, et le dit explicitement.

Les positions par groupe sont recalculées (veille_lois.group_votes), jamais reprises du
champ `positionMajoritaire` de l'Assemblée qui contredit ses propres décomptes.
"""
import gzip
import html as _html
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

sys.path.insert(0, "/root/presidentielle2027")
import veille_lois as V
from grille import GRILLE, TITRE

LEG = 17
RACINE = os.path.dirname(os.path.abspath(__file__))
DONNEES = os.path.join(RACINE, "data", "lois_votes")
OUT = DONNEES
SITE = os.environ.get("SITE", os.path.join(RACINE, "site", "lois"))
BASE = os.environ.get("BASE", "/observatoire/lois")
# En production, la page est publique et indexable. Le mode recette s'obtient avec
# NOINDEX=1 et un BASE différent.
NOINDEX = os.environ.get("NOINDEX") == "1"
SITE_URL = "https://dileviathan.fr"
URL_SCRUTIN = "https://www.assemblee-nationale.fr/dyn/{leg}/scrutins/{num}"

POS = {"pour": ("pos-pour", "Pour"), "contre": ("pos-contre", "Contre"),
       "abstention": ("pos-abst", "Abstention"), "partage": ("pos-nv", "Partagé")}

TAGS = {"ensemble": "ensemble", "amendement": "amendement", "article": "article",
        "motion": "motion", "autre": "scrutin"}


def norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slug(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:80]


def theme_de(titre, strict=False):
    """Thèmes d'un intitulé ou d'un dispositif.

    `strict` sert pour les dispositifs d'amendement : on n'y emploie QUE la grille
    d'expressions du domaine. Le vocabulaire de titre (où « données », « région », « mer »
    désignent vraiment le sujet) produit du bruit sur 2 500 caractères de droit : il y
    faisait entrer dans Numérique des textes sur la restitution de biens culturels.
    """
    t = norm(titre)
    scores = Counter()
    # Les deux couches sont additionnées : la grille stricte pèse double (une expression
    # du domaine est un signal fort), le vocabulaire de titre pèse simple. Les opposer
    # faisait perdre le sujet : un dispositif sur la « taxe sur les producteurs de données
    # numériques » sortait en Travail parce que le mot « primes » y figurait.
    for theme, grille in GRILLE.items():
        for sujet, pat in grille.items():
            if re.search(pat, t, re.I):
                scores[theme] += 2
    if not strict:
        for theme, pat in TITRE.items():
            if re.search(pat, t, re.I):
                scores[theme] += 1
    return [th for th, _ in scores.most_common(2)]


def tableau_groupes(groupes, gmap, quoi):
    lignes = ""
    for g in groupes:
        info = gmap.get(g["ref"]) or V.ALIAS_GROUPES.get(g["ref"]) or {}
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
            f'<b>{esc(sigle)}</b> <span class="small muted">{esc(nom)}</span></td>'
            f'<td><span class="pill {cls}">{lab}</span></td>'
            f'<td class="num">{val(g["pour"])}</td><td class="num">{val(g["contre"])}</td>'
            f'<td class="num">{val(g["abst"])}</td><td class="num">{val(g["nv"])}</td>'
            f'<td class="num">{val(g["absents"])}</td>'
            f'<td class="num muted">{g["membres"]}</td>'
            f'<td class="barcell">{barre}</td></tr>\n')
    return f"""<details open class="gv">
    <summary>Vote par groupe politique</summary>
    <p class="small muted" style="max-width:none;margin:8px 0 6px">
      {quoi}. Chaque député du groupe est compté une fois : pour + contre + abstentions +
      non-votants + absents = effectif.</p>
    <table>
      <tr><th>Groupe</th><th>Position dominante</th><th class="num">Pour</th>
      <th class="num">Contre</th><th class="num">Abst.</th><th class="num">Non-vot.</th>
      <th class="num">Absents</th><th class="num">Effectif</th><th>Répartition</th></tr>
      {lignes}</table>
    <p class="legend small muted"><span class="sw p"></span>pour <span class="sw c"></span>contre
    <span class="sw a"></span>abstention <span class="sw n"></span>non-votant (présent, sans vote)
    <span class="sw abs"></span>absent (dans aucun décompte du scrutin)</p>
    <p class="small muted" style="max-width:none;margin-top:8px">
      « Position dominante » est calculée sur les voix exprimées du groupe (partagée en cas
      d'égalité) — et non reprise du champ « position majoritaire » publié par l'Assemblée,
      qui contredit ses propres décomptes.</p>
  </details>"""


def liste_scrutins(textes, gmap=None):
    lignes = ""
    # Du plus récent au plus ancien : on lit un historique de vote en partant de la fin.
    for s in sorted(textes, key=lambda x: (x["date"], x["numero"] or 0), reverse=True):
        kind = V.vote_kind(s["titre"])
        pill = ("adopte" if s["code"] == "adopté" else
                "rejete" if s["code"] == "rejeté" else "")
        badge = (f'<span class="pill {pill}">{esc(s["code"].capitalize())}</span>' if pill
                 else f'<span class="pill">{esc(s["code"] or "—")}</span>')
        lien = URL_SCRUTIN.format(leg=LEG, num=s["numero"]) if s.get("numero") else ""
        objet = (f'<a href="{lien}">{esc(s["objet"])}</a>' if lien else esc(s["objet"]))
        lignes += (f'<tr><td class="date">{V.fr_date(s["date"])}</td>'
                   f'<td><span class="tag">{TAGS.get(kind, "scrutin")}</span>{objet}</td>'
                   f'<td>{badge}</td><td class="num">{s["pour"] or "—"}</td>'
                   f'<td class="num">{s["contre"] or "—"}</td>'
                   f'<td class="num">{s["abst"] or "—"}</td></tr>\n')
    return lignes


PAR_PAGE = 20


def pager(page_courante, total, base):
    """Barre de pagination numérotée, avec fenêtre autour de la page courante."""
    if total <= 1:
        return ""

    def lien(n, libelle=None, gras=False):
        cible = f"{base}/" if n == 1 else f"{base}/page/{n}/"
        style = "font-weight:700;border-color:var(--ink)" if gras else ""
        return (f'<a class="chip" href="{cible}" style="{style};text-decoration:none">'
                f'{libelle if libelle is not None else n}</a>')

    morceaux = []
    if page_courante > 1:
        morceaux.append(lien(page_courante - 1, "← Précédent"))
    fenetre = {1, total} | set(range(max(1, page_courante - 2), min(total, page_courante + 2) + 1))
    precedent = 0
    for n in sorted(fenetre):
        if precedent and n - precedent > 1:
            morceaux.append('<span class="chip" style="border:0;background:none">…</span>')
        morceaux.append(lien(n, gras=(n == page_courante)))
        precedent = n
    if page_courante < total:
        morceaux.append(lien(page_courante + 1, "Suivant →"))
    return f'<nav class="chips" style="margin:18px 0 6px" aria-label="Pagination">{"".join(morceaux)}</nav>'


def page(titre, h1, lede, corps, chemin, fil=""):
    robot = '<meta name="robots" content="noindex,nofollow">' if NOINDEX else ""
    url = SITE_URL + chemin
    nav = f"""<div class="topbar"><div class="wrap nav">
  <div class="brand"><a href="/observatoire/" style="text-decoration:none">Présidentielle 2027</a> <span>· veille législative</span></div>
  <div class="navlinks">
    <a href="/observatoire/">Accueil</a>
    <a href="/observatoire/sondages/">Agrégation</a>
    <a href="/observatoire/candidats/">Les candidats</a>
    <a href="/observatoire/workflow/">Workflow</a>
    <a href="/observatoire/backtest/">Rétro-test 2022</a>
    <a href="{BASE}/" style="font-weight:700;color:var(--ink)">Veille législative</a>
  </div>
  <button type="button" class="themebtn" id="themebtn" aria-label="Changer le thème"
    title="Passer en mode clair ou sombre">&#9681;</button>
</div></div>"""
    return f"""<!doctype html><html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(titre)}</title>
<meta name="description" content="{esc(lede)[:180]}">
{robot}
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Diléviathan">
<meta property="og:locale" content="fr_FR">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{esc(titre)}">
<meta property="og:description" content="{esc(lede)[:200]}">
<meta property="og:image" content="{SITE_URL}/images/og.jpg">
<meta name="twitter:card" content="summary_large_image">
<script>try{{var c=localStorage.getItem("theme");if(c==="dark"||(!c&&window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches)){{document.documentElement.setAttribute("data-theme","dark")}}}}catch(e){{}}</script>
<style>{V.CSS}</style>
</head><body>
{nav}
<header class="wrap hero">
  {f'<p class="small muted" style="margin:0 0 8px">{fil}</p>' if fil else ''}
  <h1>{h1}</h1>
  <p class="lede">{lede}</p>
</header>
<main class="wrap">
{corps}
</main>
<footer class="wrap">
  <p class="small muted">Source : scrutins publics de l'Assemblée nationale
  (<a href="https://data.assemblee-nationale.fr">data.assemblee-nationale.fr</a>, licence Etalab).
  Chaque objet de vote renvoie à la page officielle du scrutin. Les positions par groupe sont
  recalculées depuis les décomptes nominatifs.</p>
</footer>
<script>(function(){{var b=document.getElementById("themebtn");if(!b)return;
b.addEventListener("click",function(){{var r=document.documentElement;
var sombre=r.getAttribute("data-theme")==="dark";
if(sombre){{r.removeAttribute("data-theme");localStorage.setItem("theme","light")}}
else{{r.setAttribute("data-theme","dark");localStorage.setItem("theme","dark")}}}})}})();</script>
</body></html>"""


def main():
    scrutins = V.load_scrutins(LEG)
    gmap = V.load_groupes(LEG)
    # Notices rédigées à partir du texte officiel (sources.py puis rediger.py).
    # Un texte sans notice n'en reçoit pas d'inventée.
    notices_scrutin = {}
    f_ns_plain = os.path.join(DONNEES, "notices_scrutins.json")
    f_ns = f_ns_plain if os.path.exists(f_ns_plain) else os.path.join(DONNEES, "notices_scrutins.json.gz")
    if os.path.exists(f_ns):
        if f_ns.endswith(".gz"):
            with gzip.open(f_ns, "rt", encoding="utf-8") as fh:
                notices_scrutin = {k: v for k, v in json.load(fh).items() if v}
        else:
            notices_scrutin = {k: v for k, v in json.load(open(f_ns, encoding="utf-8")).items() if v}
    resumes = {}
    f_exp_plain = os.path.join(DONNEES, "explications.json")
    f_exp = f_exp_plain if os.path.exists(f_exp_plain) else os.path.join(DONNEES, "explications.json.gz")
    if os.path.exists(f_exp):
        if f_exp.endswith(".gz"):
            with gzip.open(f_exp, "rt", encoding="utf-8") as fh:
                entrees = json.load(fh)
        else:
            entrees = json.load(open(f_exp, encoding="utf-8"))
        for e in entrees:
            if e.get("resume"):
                # On garde le numéro du scrutin que la notice décrit : sur une page de
                # thème, la carte n'affiche qu'une partie des scrutins, et une notice
                # portant sur un autre vote serait un contresens.
                resumes[e["titre"]] = (e["resume"], str((e.get("vote") or {}).get("numero")))
        print(f"  {len(resumes)} notices disponibles")

    # Thèmes déduits du contenu réel des amendements (harvest.py). Un texte n'est donc
    # plus classé sur son seul titre : le projet de loi de finances contient un amendement
    # sur la taxe des données, et doit apparaître dans Numérique pour cette raison.
    themes_vote = defaultdict(Counter)
    # Le fichier courant (alimenté chaque jour) prime sur l'instantané versionné.
    f_disp_plain = os.path.join(DONNEES, "dispositifs.jsonl")
    f_disp = f_disp_plain if os.path.exists(f_disp_plain) else os.path.join(DONNEES, "dispositifs.jsonl.gz")
    if os.path.exists(f_disp) and f_disp.endswith(".gz"):
        with gzip.open(f_disp, "rt", encoding="utf-8") as fh:
            lignes_disp = list(fh)
    elif os.path.exists(f_disp):
        lignes_disp = open(f_disp, encoding="utf-8").readlines()
    else:
        lignes_disp = []
    if lignes_disp:
        for ligne in lignes_disp:
            try:
                d = json.loads(ligne)
            except Exception:
                continue
            if d.get("dispositif"):
                # Les pages de l'Assemblée encodent les accents en entités HTML :
                # sans décodage, « imp&#x00F4;ts » ne correspond à aucun motif.
                for th in theme_de(_html.unescape(d["dispositif"]), strict=True):
                    # Les numéros de scrutin sont des chaînes côté Assemblée : on
                    # normalise, sinon une entrée ajoutée avec un entier ne correspond
                    # plus à rien et le scrutin disparaît sans erreur.
                    themes_vote[str(d["numero"])][th] += 1
        print(f"  {len(themes_vote)} scrutins avec contenu classable")

    groupes = defaultdict(list)
    sans_nom = 0
    for s in scrutins:
        titre = V._clean(s.get("titre") or "")
        nom, _ = V.law_name(titre)
        if not nom:
            sans_nom += 1
            continue
        dec = ((s.get("syntheseVote") or {}).get("decompte")) or {}
        groupes[nom].append({
            "date": (s.get("dateScrutin") or "")[:10],
            "code": (s.get("sort") or {}).get("code") or "",
            "titre": titre,
            "objet": V.short_objet(titre) or titre[:140],
            "numero": s.get("numero"),
            "kind": V.vote_kind(titre),
            "pour": int(dec.get("pour") or 0),
            "contre": int(dec.get("contre") or 0),
            "abst": int(dec.get("abstentions") or 0),
            "groupes": V.group_votes(s),
        })

    textes = []
    for nom, votes in groupes.items():
        votes.sort(key=lambda v: (v["date"], v["numero"] or 0))
        ens = [v for v in votes if v["kind"] == "ensemble"]
        # Un texte garde ses thèmes de titre, et gagne ceux que ses scrutins désignent
        # au moins trois fois — un seul amendement numériques ne fait pas un texte numérique.
        themes_titre = theme_de(nom)
        par_scrutin = Counter()
        for v in votes:
            for th, n in themes_vote.get(str(v["numero"]), {}).items():
                par_scrutin[th] += n
        themes = list(themes_titre)
        for th, n in par_scrutin.most_common():
            if n >= 3 and th not in themes and len(themes) < 3:
                themes.append(th)
        textes.append({
            "titre": nom, "votes": votes, "ensemble": ens[-1] if ens else None,
            "themes": themes, "themes_votes": dict(par_scrutin),
            "debut": votes[0]["date"], "fin": votes[-1]["date"],
        })
    # Thème de CHAQUE scrutin : son dispositif s'il a été lu, sinon ceux du texte qui le
    # porte. C'est le scrutin qui est classé, pas seulement le texte — un projet de loi de
    # finances contient des amendements qui ne relèvent pas des finances.
    themes_scrutin = {}
    for t in textes:
        for v in t["votes"]:
            th = list(themes_vote.get(str(v["numero"]), {}))
            if not th:
                th = t["themes"]
            themes_scrutin[v["numero"]] = th

    textes.sort(key=lambda t: t["fin"], reverse=True)
    dernier = max(t["fin"] for t in textes)
    n_scrutins = sum(len(t["votes"]) for t in textes)
    n_ensemble = sum(1 for t in textes if t["ensemble"])
    adoptes = sum(1 for t in textes if t["ensemble"] and t["ensemble"]["code"] == "adopté")
    rejetes = sum(1 for t in textes if t["ensemble"] and t["ensemble"]["code"] == "rejeté")
    print(f"  {len(scrutins)} scrutins · {len(textes)} textes · {n_scrutins} scrutins rattachés "
          f"· {sans_nom} hors texte nominal")

    par_theme = defaultdict(list)
    for t in textes:
        par_scrutin = defaultdict(list)
        for v in t["votes"]:
            for th in (themes_scrutin.get(v["numero"]) or ["Autres textes"]):
                par_scrutin[th].append(v)
        for th, vs in par_scrutin.items():
            par_theme[th].append((t, vs))

    def carte(t, scr=None):
        # scr : les scrutins à montrer. Sur une page de thème, ce sont ceux du thème ;
        # sur la fiche du texte, tous. Le vote mis en avant est le dernier vote sur
        # l'ensemble s'il y en a un dans la sélection, sinon le dernier scrutin.
        scr = scr if scr is not None else t["votes"]
        ens = [v for v in scr if v["kind"] == "ensemble"]
        ens = ens[-1] if ens else None
        if ens:
            pill = ("adopte" if ens["code"] == "adopté" else
                    "rejete" if ens["code"] == "rejeté" else "")
            etat = (f'<span class="pill {pill}">{esc(ens["code"].capitalize())}</span> '
                    f'<span class="small muted">vote final du {V.fr_date(ens["date"])} — '
                    f'{ens["pour"]} pour, {ens["contre"]} contre</span>')
            ref = ens
            quoi = f"vote sur l'ensemble du texte, du {V.fr_date(ens['date'])}"
        else:
            ref = scr[-1]
            etat = ('<span class="small muted">Pas encore de vote sur l\'ensemble — '
                    'le scrutin présenté est le dernier voté sur ce texte</span>')
            quoi = f"dernier scrutin enregistré, du {V.fr_date(ref['date'])}"
        puces = []
        for x in (t["themes"] or ["thème non identifié"]):
            n = (t.get("themes_votes") or {}).get(x, 0)
            if x not in theme_de(t["titre"]) and n:
                puces.append(f'<span class="chip">{esc(x)} · {n} scrutin{"s" if n > 1 else ""}</span>')
            else:
                puces.append(f'<span class="chip">{esc(x)}</span>')
        # Notice du scrutin affiché d'abord : elle décrit exactement le vote qu'on voit.
        # À défaut, celle du texte — et seulement si elle porte sur le même scrutin.
        texte_notice = notices_scrutin.get(str(ref.get("numero")))
        if not texte_notice:
            _r = resumes.get(t["titre"])
            if _r and str(ref.get("numero")) == _r[1]:
                texte_notice = _r[0]
        if texte_notice:
            # Le modèle termine parfois par une phrase creuse (« Le résultat du vote est
            # l'ensemble »). On la retire et on écrit le résultat avec les chiffres du
            # scrutin : c'est déterministe, donc toujours juste.
            texte_notice = re.sub(r"\s*Le résultat du vote est[^.]*\.?\s*$", "", texte_notice).strip()
            if not texte_notice.endswith("."):
                texte_notice += "."
            issue = ("Adopté" if ref["code"] == "adopté"
                     else "Rejeté" if ref["code"] == "rejeté" else "Voté")
            texte_notice += (f' {issue} le {V.fr_date_longue(ref["date"])} par '
                             f'{ref["pour"]} voix pour, {ref["contre"]} contre et '
                             f'{ref["abst"]} abstentions.')
        notice = (f'<p class="small muted" style="max-width:none">{esc(texte_notice)}</p>'
                  if texte_notice else "")
        chips = "".join(puces)
        chips += f'<span class="chip">{len(scr)} scrutin{"s" if len(scr) > 1 else ""}</span>'
        if len(scr) == 1:
            chips += '<span class="chip">suivi éditorial</span>'
        return f"""<section class="card">
  <h2><a href="{BASE}/texte/{slug(t["titre"])}/" style="text-decoration:none">{esc(t["titre"])}</a></h2>
  <div class="chips">{chips}</div>
  <p style="margin:0">{etat}</p>
  {notice}
  {tableau_groupes(ref["groupes"], gmap, quoi)}
  <details>
    <summary>Voir les {len(scr)} scrutins ({V.fr_date(scr[0]["date"])} → {V.fr_date(scr[-1]["date"])})</summary>
    <table>
      <tr><th>Date</th><th>Objet du vote</th><th>Sort</th>
      <th class="num">Pour</th><th class="num">Contre</th><th class="num">Abst.</th></tr>
      {liste_scrutins(scr)}
    </table>
  </details>
</section>"""

    os.makedirs(SITE, exist_ok=True)
    cartes = "".join(
        f'<a href="{BASE}/{slug(th)}/" class="chip" style="text-decoration:none">'
        f'{esc(th)} <span class="small muted">{len(par_theme[th])}</span></a>'
        for th in sorted(par_theme, key=lambda x: -len(par_theme[x])))

    n_pages_accueil = (len(textes) + PAR_PAGE - 1) // PAR_PAGE
    corps = f"""<section class="etat ok">
  <p><b>Dernier scrutin publié : {V.fr_date(dernier)}</b>.</p>
  <p class="small muted">Scrutins publics de l'Assemblée nationale, 17<sup>e</sup> législature.
  Chaque texte porte tous ses scrutins — votes sur l'ensemble, articles et amendements.</p>
</section>
<section class="card">
  <h2>Ce que le Parlement a voté</h2>
  <p class="small muted" style="max-width:none">Pour chaque texte : le vote sur l'ensemble quand
  il existe, la ventilation par groupe politique du scrutin décisif, puis la liste complète des
  scrutins avec leur objet et leur sort.</p>
  <div class="stat"><div><b>{len(textes)}</b>textes suivis</div>
    <div><b>{n_scrutins}</b>scrutins publics</div>
    <div><b>{n_ensemble}</b>textes avec vote final</div>
    <div><b>{adoptes}</b>adoptés</div>
    <div><b>{rejetes}</b>rejetés</div>
    <div><b>{V.fr_date(min(t['debut'] for t in textes))} → {V.fr_date(dernier)}</b>période couverte</div></div>
  <div class="chips" style="margin-top:16px">{cartes}</div>
</section>
{''.join(carte(t) for t in textes[0:PAR_PAGE])}
{pager(1, n_pages_accueil, BASE)}"""
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(page(
        "Veille législative — les lois votées",
        "Ce que le Parlement vote",
        f"{len(textes)} textes suivis dans les données ouvertes de l'Assemblée nationale, "
        f"{n_scrutins} scrutins publics, vote par groupe politique et liste complète des votes.",
        corps, f"{BASE}/"))

    # Pages 2, 3, … : l'ensemble des textes suivis, dans le même ordre.
    for n in range(2, n_pages_accueil + 1):
        tranche = textes[(n - 1) * PAR_PAGE:n * PAR_PAGE]
        corps_p = ("".join(carte(t) for t in tranche)
                   + pager(n, n_pages_accueil, BASE))
        dd = os.path.join(SITE, "page", str(n))
        os.makedirs(dd, exist_ok=True)
        open(os.path.join(dd, "index.html"), "w", encoding="utf-8").write(page(
            f"Veille législative — les lois votées — page {n}",
            "Ce que le Parlement vote",
            f"Textes {((n - 1) * PAR_PAGE) + 1} à {min(n * PAR_PAGE, len(textes))} "
            f"sur {len(textes)}.",
            corps_p, f"{BASE}/page/{n}/",
            fil=f'<a href="{BASE}/">Tous les thèmes</a>'))

    for th, ts in par_theme.items():
        ts.sort(key=lambda p: p[1][-1]["date"], reverse=True)
        d = os.path.join(SITE, slug(th))
        os.makedirs(d, exist_ok=True)
        n_pages = (len(ts) + PAR_PAGE - 1) // PAR_PAGE
        for n in range(1, n_pages + 1):
            tranche = ts[(n - 1) * PAR_PAGE:n * PAR_PAGE]
            corps = ("".join(carte(tt, vs) for tt, vs in tranche)
                     + pager(n, n_pages, f"{BASE}/{slug(th)}"))
            dd = d if n == 1 else os.path.join(d, "page", str(n))
            os.makedirs(dd, exist_ok=True)
            chemin = (f"{BASE}/{slug(th)}/" if n == 1
                      else f"{BASE}/{slug(th)}/page/{n}/")
            open(os.path.join(dd, "index.html"), "w", encoding="utf-8").write(page(
                f"Veille législative — {th}" + (f" — page {n}" if n > 1 else ""), esc(th),
                f"{len(ts)} textes — {sum(len(vs) for _, vs in ts)} scrutins publics.",
                corps, chemin, fil=f'<a href="{BASE}/">Tous les thèmes</a>'))

    for t in textes:
        d = os.path.join(SITE, "texte", slug(t["titre"]))
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(page(
            t["titre"], esc(t["titre"]),
            f"{len(t['votes'])} scrutins — vote par groupe politique.",
            carte(t), f"{BASE}/texte/{slug(t['titre'])}/",
            fil=f'<a href="{BASE}/">Tous les thèmes</a>'))

    n = sum(len(f) for _, _, f in os.walk(SITE))
    print(f"  {n} pages · dernier scrutin {dernier} · thèmes : "
          + ", ".join(f"{k} {len(v)}" for k, v in sorted(par_theme.items(), key=lambda x: -len(x[1]))[:8]))
    print(f"  → {SITE}")


if __name__ == "__main__":
    main()
