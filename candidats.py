#!/usr/bin/env python3
"""Page « Les candidats » — tableau des candidatures déclarées, conditionnelles et écartées.

Source unique de vérité : data/candidats2027.json (chaque ligne porte sa source et sa date de
vérification). Ce script ne fait que rendre : aucune donnée n'est saisie ici.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as G   # CSS et helpers de format partagés avec les autres pages

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
SITE = os.path.join(BASE, "site")

STATUTS = [
    ("declare", "Déclarés", "La candidature a été annoncée publiquement, par le candidat ou par son parti."),
    ("conditionnel", "Déclarés sous condition", "La candidature est posée mais dépend d'une étape interne : "
     "une primaire, une investiture, le jugement d'un parti."),
    ("suspens", "Ni candidats, ni absents", "Ils entretiennent le doute et n'ont pas renoncé."),
    ("retire", "Annoncés puis retirés", "Un retrait reste une information : la ligne reste, barrée."),
    ("soutien", "Cités mais non candidats", "Ils ont dit ne pas être candidats — ou soutenir quelqu'un d'autre."),
]
FAMILLES = {
    "extreme-gauche": ("Extrême gauche", "#6b1f26"),
    "gauche": ("Gauche", "#8c2f39"),
    "centre": ("Centre", "#8a6a1f"),
    "droite": ("Droite", "#2b4a7a"),
    "extreme-droite": ("Extrême droite", "#4a2f6b"),
    "divers": ("Divers", "#5c6773"),
}
PILLS = {"declare": "Déclaré", "conditionnel": "Sous condition", "suspens": "En suspens",
         "retire": "Retiré", "soutien": "Non candidat"}

CSS_PAGE = """
.tblwrap{overflow-x:auto;margin-top:16px;border:1px solid var(--line);border-radius:10px;background:var(--paper)}
table.cand{border-collapse:separate;border-spacing:0;width:100%;font-size:.9rem;min-width:860px}
table.cand thead th{position:sticky;top:0;z-index:2;background:var(--paper);text-align:left;
  font-size:.72rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
  padding:12px 14px;border-bottom:2px solid var(--line);white-space:nowrap}
table.cand td{padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}
table.cand tbody tr:hover{background:rgba(215,61,47,.045)}
table.cand tbody tr:last-child td{border-bottom:0}
.nom{font-weight:600;color:var(--ink);white-space:nowrap}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:.74rem;color:var(--muted);white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.td-date{white-space:nowrap;font-variant-numeric:tabular-nums}
.td-src a{font-size:.78rem}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.74rem;font-weight:600;
  white-space:nowrap;border:1px solid}
.p-declare{color:#8c2f2a;border-color:#e3c3bf;background:#fbefee}
.p-conditionnel{color:#7a5a12;border-color:#e6d7ae;background:#fbf5e6}
.p-suspens{color:#5c6773;border-color:#d9d2c3;background:#f6f4ee}
.p-retire{color:#6b6b6b;border-color:#ded8cb;background:#f4f2ec}
.p-soutien{color:#2b4a7a;border-color:#c3d1e3;background:#eef2f8}
tr.retiree td{color:#6b6b6b}
tr.retiree .nom{text-decoration:line-through;text-decoration-thickness:1px}
.compteurs{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:18px}
.compteur{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:14px}
.compteur b{display:block;font-size:1.6rem;line-height:1.1;color:var(--ink)}
.compteur span{font-size:.8rem;color:var(--muted)}
.pbars{margin-top:14px}
.pb{display:grid;grid-template-columns:minmax(110px,24%) 1fr 84px 58px;align-items:center;
  gap:10px;padding:4px 0}
.pb .lab{font-size:.85rem;font-weight:600;color:var(--ink);text-align:right;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pb .track{position:relative;height:13px;border-radius:7px;background:var(--line);overflow:hidden}
.pb .fill{position:absolute;left:0;top:0;bottom:0;border-radius:7px;background:var(--red)}
.pb .val{font-size:.8rem;color:var(--ink);font-variant-numeric:tabular-nums;
  text-align:right;line-height:1.15}
.pb .val .muted{font-size:.72rem}
.pb .delta{text-align:right;font-variant-numeric:tabular-nums}
.pb .up{color:#2f6b3f}.pb .down{color:#8c2f2a}
@media(max-width:640px){.pb{grid-template-columns:minmax(84px,36%) 1fr 62px;gap:8px}
  .pb .delta{display:none}}
@media(max-width:900px){
  /* Un tableau de sept colonnes ne se lit pas sur un téléphone : chaque ligne devient une fiche.
     Mesuré avant correction : 938 px de tableau pour 294 px disponibles, soit 644 px de défilement. */
  .tblwrap{border:0;overflow:visible;background:transparent}
  table.cand{min-width:0;display:block;font-size:.92rem}
  table.cand thead{display:none}
  table.cand tbody{display:block}
  table.cand tr{display:block;background:var(--paper);border:1px solid var(--line);
    border-radius:12px;padding:12px 14px;margin-bottom:12px}
  table.cand tbody tr:hover{background:var(--paper)}
  table.cand td{display:grid;grid-template-columns:118px 1fr;gap:10px;align-items:start;
    padding:5px 0;border-bottom:0;position:static}
  table.cand td::before{content:attr(data-label);font-size:.68rem;letter-spacing:.07em;
    text-transform:uppercase;color:var(--muted);padding-top:2px}
  table.cand td[data-label="Candidat"]{grid-template-columns:1fr;margin-bottom:4px}
  table.cand td[data-label="Candidat"]::before{display:none}
  table.cand td[data-label="Candidat"] .nom{font-size:1.02rem}
  table.cand tr.retiree{background:var(--bg)}
}
.note-legale{background:var(--paper);border-left:3px solid var(--red);padding:14px 16px;border-radius:0 8px 8px 0}
"""


def date_affichage(c):
    """Date de déclaration en clair, sans fausse précision : le mois quand le jour n'est pas établi."""
    if not c["date_declaration"]:
        return '<span class="muted">—</span>'
    y, m, j = c["date_declaration"].split("-")
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
            "septembre", "octobre", "novembre", "décembre"][int(m) - 1]
    if c["precision"] == "jour":
        return f"{j}/{m}/{y}"
    return f"<span class='muted'>≈</span> {mois} {y}"


def ligne(c):
    fam, col = FAMILLES.get(c["famille"], FAMILLES["divers"])
    cls = ' class="retiree"' if c["statut"] == "retire" else ""
    off = ('<span class="muted">non</span>' if c["statut"] != "soutien"
           else '<span class="muted">—</span>')
    return (
        f'<tr{cls}>'
        f'<td data-label="Candidat"><span class="nom">{c["nom"]}</span></td>'
        f'<td data-label="Parti">{c["parti"]}<br><span class="chip">'
        f'<span class="dot" style="background:{col}"></span>{fam}</span></td>'
        f'<td class="td-date" data-label="Déclaration">{date_affichage(c)}</td>'
        f'<td data-label="Statut"><span class="pill p-{c["statut"]}">{PILLS[c["statut"]]}</span></td>'
        f'<td data-label="Officialisation JO">{off}</td>'
        f'<td class="small" data-label="Commentaire">{c["commentaire"]}</td>'
        f'<td class="td-src small" data-label="Source"><a href="{c["source"]}">'
        f'{c["source_label"]}</a></td>'
        f'</tr>')


def _iso(s):
    """Date ISO -> date."""
    import datetime as _dt
    y, m, j = map(int, s[:10].split("-"))
    return _dt.date(y, m, j)


FENETRE = 90          # jours : fenêtre de référence (celle de l'agrégation)


def presence_block():
    """« Qui sera sur le bulletin ? » — mesuré, jamais modélisé.

    Ce que la source permet de compter : dans chaque sondage publié, la liste des noms réellement
    testés. Un taux de présence n'est pas une probabilité de candidature — c'est la trace de ce que
    les instituts jugent plausible, et cela se déplace vite (voir la bascule Le Pen / Bardella).
    """
    import datetime as dt
    import collections
    import itertools

    P = json.load(open(os.path.join(DATA, "polls.json"), encoding="utf-8"))
    tour1 = [p for p in P if str(p.get("tour", "")).lower().startswith("1")]
    if not tour1:
        return ""
    today = dt.date.today()

    def fenetre(debut, fin):
        return [p for p in tour1
                if debut <= (today - _iso(p["fin_enquete"])).days < fin]

    cur, prec = fenetre(0, FENETRE), fenetre(FENETRE, 2 * FENETRE)
    if len(cur) < 10:
        return ""

    def presence(sondages):
        c = collections.Counter()
        for p in sondages:
            for cand in p["candidats"]:
                c[cand["candidat"]] += 1
        return c

    pc, pp = presence(cur), presence(prec)
    n, nprev = len(cur), len(prec)
    presence_tri = pc.most_common()
    nb_candidats = len(presence_tri)
    hypo = len({p.get("hypothese", "") for p in cur})
    seuil = max(1, round(0.02 * n))

    # --- lignes du classement (les noms cités au moins une fois, les plus présents d'abord)
    lignes = ""
    for nom, k in presence_tri:
        taux = k / n
        delta = (taux - (pp.get(nom, 0) / nprev)) if nprev else None
        if delta is None:
            fleche = '<span class="muted">—</span>'
        elif abs(delta) < 0.005:
            fleche = '<span class="muted">=</span>'
        else:
            fleche = (f'<span class="up">▲ {G.fr1u(abs(delta) * 100)}</span>' if delta > 0
                      else f'<span class="down">▼ {G.fr1u(abs(delta) * 100)}</span>')
        lignes += (f'<div class="pb"><span class="lab" title="{nom}">{nom}</span>'
                   f'<span class="track"><span class="fill" style="width:{max(1.2, taux * 100):.2f}%"></span></span>'
                   f'<span class="val">{G.fr(round(taux * 100, 1))} %<br>'
                   f'<span class="muted">{k}/{n}</span></span>'
                   f'<span class="delta small">{fleche}</span></div>')

    # --- paires « un siège, deux noms » : jamais ensemble, et à elles deux tout le champ
    # Un siège occupé par alternance = une partition du champ, pas une simple somme :
    # il faut que chaque nom apparaisse SEUL dans au moins trois questionnaires, qu'ils ne se
    # croisent presque jamais, et qu'ensemble ils couvrent tout le champ. Sans la condition
    # « chacun apparaît seul », n'importe quel nom rare s'apparie à un nom universel.
    paires = []
    couples = {}
    for a, b in itertools.combinations([x for x, _ in presence_tri], 2):
        if min(pc[a], pc[b]) < seuil:
            continue
        a_seul = b_seul = commun = aucun = 0
        for p in cur:
            da = any(c["candidat"] == a for c in p["candidats"])
            db = any(c["candidat"] == b for c in p["candidats"])
            if da and db:
                commun += 1
            elif da:
                a_seul += 1
            elif db:
                b_seul += 1
            else:
                aucun += 1
        tol = max(1, round(0.02 * n))
        if a_seul >= 3 and b_seul >= 3 and commun <= tol and aucun <= tol:
            paires.append((a, b, commun, a_seul, b_seul, aucun))
            couples[(a, b)] = (a_seul, b_seul, commun, aucun)

    bloc_paires = ""
    if paires:
        lignes_p = ""
        for a, b, commun, a_seul, b_seul, aucun in paires:
            lignes_p += (f'<tr><td class="nom">{a}</td><td class="nom">{b}</td>'
                         f'<td class="num">{a_seul}</td>'
                         f'<td class="num">{b_seul}</td>'
                         f'<td class="num">{commun}</td>'
                         f'<td class="num">{aucun}</td>'
                         f'<td class="num">{G.fr(round(100 * (a_seul + b_seul) / n, 1))} %</td></tr>')
        bloc_paires = f'''<h3 style="margin-top:26px">Un siège, deux noms</h3>
  <p class="small muted" style="max-width:none">Trois conditions, mesurées et non supposées : chaque nom est testé
  <strong>seul</strong> dans au moins trois questionnaires, ils ne se croisent
  <strong>presque jamais</strong>, et à eux deux ils couvrent <strong>tout le champ</strong> de la
  fenêtre. C'est la signature d'un même siège occupé par alternance dans les scénarios des instituts.
  Une simple addition ne suffirait pas : un nom rare s'additionnerait à n'importe quel nom universel,
  d'où la condition « chacun apparaît seul ».</p>
  <div class="tblwrap"><table>
    <thead><tr><th>Nom A</th><th>Nom B</th><th class="num">A seul</th>
    <th class="num">B seul</th><th class="num">Les deux</th><th class="num">Ni l'un ni l'autre</th>
    <th class="num">Champ couvert</th></tr></thead>
    <tbody>{lignes_p}</tbody>
  </table></div>
  <p class="small muted" style="margin-top:12px;max-width:none">Sur {n} questionnaires de la fenêtre,
  <strong>{'une paire remplit' if len(paires) == 1 else str(len(paires)) + ' paires remplissent'}
  </strong> ces trois conditions.</p>'''
    else:
        bloc_paires = ('<h3 style="margin-top:26px">Un siège, deux noms</h3>'
                       '<p class="small muted" style="max-width:none">Aucune paire ne remplit aujourd\'hui les trois '
                       'conditions : deux noms testés seuls chacun de leur côté, presque jamais '
                       'ensemble, <em>et</em> couvrant tout le '
                       'champ. La situation peut changer au prochain sondage — la page est régénérée '
                       'chaque jour.</p>')

    # --- bascule : ce que les deux noms faisaient il y a un an (3 fenêtres de 90 j)
    bascule = ""
    if paires:
        a, b = paires[0][0], paires[0][1]
        lignes_b = ""
        for debut, libelle in ((0, "Aujourd'hui"), (FENETRE, "Il y a 3 mois"),
                               (2 * FENETRE, "Il y a 6 mois"), (3 * FENETRE, "Il y a 9 mois")):
            f = fenetre(debut, debut + FENETRE)
            if len(f) < 5:
                continue
            c = presence(f)
            lignes_b += (f'<tr><td>{libelle}</td><td class="num">{len(f)}</td>'
                         f'<td class="num">{G.fr(round(100 * c[a] / len(f), 1))} %</td>'
                         f'<td class="num">{G.fr(round(100 * c[b] / len(f), 1))} %</td></tr>')
        bascule = f'''<h3 style="margin-top:26px">{a} et {b} : ce que la mesure raconte</h3>
  <p class="small muted" style="max-width:none">Même fenêtre de 90 jours, quatre dates. Une « probabilité de candidature »
  ne bougerait pas comme cela ; une mesure de ce que les instituts testent, si.</p>
  <div class="tblwrap"><table>
    <thead><tr><th>Fenêtre</th><th class="num">Questionnaires</th>
    <th class="num">{a}</th><th class="num">{b}</th></tr></thead>
    <tbody>{lignes_b}</tbody>
  </table></div>'''

    return f'''<section class="card" id="bulletin">
  <h2>Qui sera sur le bulletin ?</h2>
  <p class="lede" style="font-size:1rem">La question n'est pas qui gagne, mais qui sera sur le
  bulletin. En France, la liste est arrêtée par le <strong>Conseil constitutionnel</strong> et publiée
  au <em>Journal officiel</em> quelques semaines avant le premier tour : rien d'autre, juridiquement,
  ne fait une candidature. D'ici là, un seul observable existe — les noms que les instituts testent
  réellement dans leurs questionnaires. Nous le comptons, nous ne le modélisons pas.</p>
  <div class="statgrid">
    <div class="stat"><span>Questionnaires dépouillés</span><b>{n}</b>
      <span>premier tour, {FENETRE} derniers jours</span></div>
    <div class="stat"><span>Noms testés</span><b>{nb_candidats}</b><span>au moins une fois</span></div>
    <div class="stat"><span>Hypothèses distinctes</span><b>{hypo}</b><span>listes de candidats</span></div>
    <div class="stat"><span>Liste officielle</span><b>0</b><span>aucune avant 2027</span></div>
  </div>

  <h3 style="margin-top:26px">Part des questionnaires où le nom est testé</h3>
  <div class="pbars">{lignes}</div>
  <p class="small muted" style="margin-top:10px;max-width:none">Lecture : sur les {n} questionnaires de premier tour
  publiés dans les {FENETRE} derniers jours, <strong>{presence_tri[0][0]}</strong> figure dans
  {presence_tri[0][1]}. La colonne de droite compare à la fenêtre de {FENETRE} jours précédente
  ({nprev} questionnaires).</p>
  {bloc_paires}
  {bascule}

  <div class="note-legale small" style="margin-top:24px">
    <p style="margin:0 0 8px"><strong>Ce que ce chiffre n'est pas.</strong></p>
    <ul class="tight" style="margin:0">
      <li><strong>Pas une probabilité de candidature.</strong> Un institut teste un nom parce qu'il le
      juge plausible à un instant donné. Un nom testé dans 9 % des questionnaires peut être une
      candidature très sérieuse ; un nom testé dans 100 % peut ne jamais se déclarer.</li>
      <li><strong>Pas la liste officielle.</strong> Seuls le recueil des parrainages et la décision du
      Conseil constitutionnel font foi. Aucun institut ne dispose d'une information que le Conseil
      constitutionnel n'a pas encore publiée.</li>
      <li><strong>Pas comparable à la « probabilité de figurer sur le bulletin » d'un modèle
      bayésien.</strong> Cette page ne contient aucun modèle : elle rapporte un décompte, avec son
      dénominateur, et rien d'autre.</li>
      <li><strong>Une limite connue :</strong> le nombre bouge avec la spéculation autant qu'avec la
      politique. Il mesure l'état du champ tel que la presse et les instituts le construisent — ce
      n'est pas un jugement sur les personnes.</li>
    </ul>
    <p style="margin:8px 0 0" class="muted">Source : même compilation que l'agrégation
    (MieuxVoter, licence MIT), champ « premier tour ». Recalcul automatique à chaque régénération,
    au moins une fois par jour.</p>
  </div>
</section>'''


def render(d):
    par_statut = {s: [c for c in d["candidats"] if c["statut"] == s] for s, _, _ in STATUTS}
    sc = d["scrutins"]
    t1, t2 = G.frd(sc["premier_tour"]), G.frd(sc["second_tour"])

    sommaire = "".join(
        f'<a class="btn2" href="#{s}" style="margin:0 8px 8px 0">{titre} '
        f'<strong>{len(par_statut[s])}</strong></a>' for s, titre, _ in STATUTS)

    sections = ""
    for s, titre, intro in STATUTS:
        rows = "".join(ligne(c) for c in sorted(par_statut[s], key=lambda c: c["nom"].split()[-1]))
        sections += f'''<section id="{s}" class="card">
  <h2>{titre} <span class="muted" style="font-size:.8em">({len(par_statut[s])})</span></h2>
  <p class="small muted" style="max-width:none">{intro}</p>
  <div class="tblwrap"><table class="cand">
    <thead><tr><th>Candidat</th><th>Parti</th><th>Déclaration</th><th>Statut</th>
    <th>Officialisation<br>Journal officiel</th><th>Commentaire</th><th>Source</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</section>'''

    bulletin = presence_block()

    demi = ""
    for src in d["sources_reference"]:
        lien = f' — <a href="{src["url"]}">{src["url"].split("/")[2]}</a>' if src["url"] else ""
        demi += f'<li><strong>{src["niveau"]}</strong> : {src["quoi"]}{lien}. {src["note"]}</li>'

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="{G.meta_description('/observatoire/candidats/')}">
<title>{G.titre_court('/observatoire/candidats/')}</title>
<link rel="canonical" href="https://dileviathan.fr/observatoire/candidats/">
{G.meta_social('/observatoire/candidats/')}
{G.ld_json("/observatoire/candidats/")}
{G.matomo()}
<style>{G.CSS}{CSS_PAGE}{G.DARK}</style>
{G.THEME_HEAD}</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand"><a href="/observatoire/" style="text-decoration:none">Présidentielle 2027</a> <span>· les candidats</span></div>
  <div class="navlinks"><a href="/observatoire/">Accueil</a><a href="/observatoire/sondages/">Agrégation</a>
  <a href="/observatoire/backtest/">Rétro-test 2022</a>{G.NAV_WORKFLOW}{G.NAV_LOIS}<a href="#bulletin">Qui sera sur le bulletin ?</a></div>{G.THEME_BTN}
</div></div>

<header class="wrap">
  <span class="eyebrow">Observatoire des sondages · présidentielle 2027</span>
  <h1>Qui est candidat, qui ne l'est pas, et ce qu'il reste à franchir</h1>
  <p class="lede">Une déclaration de candidature n'est pas une candidature. Le scrutin aura lieu les
  <strong>{t1}</strong> et <strong>{t2}</strong> 2027 ; la liste officielle des candidats sera arrêtée
  par le Conseil constitutionnel et publiée au Journal officiel quelques semaines avant le premier
  tour. D'ici là, tout est déclaratif — et nous le disons ligne par ligne.</p>
  <div class="statgrid">
    <div class="stat"><span>Déclarés</span><b>{len(par_statut["declare"])}</b><span>candidature annoncée</span></div>
    <div class="stat"><span>Sous condition</span><b>{len(par_statut["conditionnel"])}</b>
      <span>primaire ou investiture</span></div>
    <div class="stat"><span>Déclarés en 2022</span><b>12</b><span>pour comparaison</span></div>
    <div class="stat"><span>Officialisations</span><b>0</b><span>aucune avant 2027</span></div>
  </div>
  <p class="small muted" style="margin-top:14px;max-width:none">Vérifié le {G.frd(d["verifie_le"])} sur les sources
  listées en bas de page ({len(d["candidats"])} personnes recensées). Deux règles : jamais de date sans
  source, et un retrait reste affiché.</p>
</header>

<main class="wrap">
<section class="card">
  <h2>Par où commencer</h2>
  <p class="small muted" style="max-width:none">Les groupes ci-dessous ne sont pas des jugements : ils décrivent ce qui manque
  à chaque candidature pour devenir une candidature au sens du Conseil constitutionnel.</p>
  <p style="margin-top:12px">{sommaire}</p>
  <div class="note-legale small" style="margin-top:18px">
    <p style="margin:0"><strong>Ce qu'exige la loi.</strong> Pour figurer sur le bulletin, il faut
    <strong>500 parrainages</strong> d'élus venant d'au moins <strong>30 départements ou
    collectivités</strong>, sans que plus d'un dixième vienne du même département. Les parrainages sont
    adressés au Conseil constitutionnel, qui arrête la liste des candidats et la publie au
    <em>Journal officiel</em> — en 2022, cette publication a eu lieu le 7 mars, un mois avant le
    premier tour. La colonne « officialisation » restera donc vide pour tout le monde jusqu'à cette
    publication, et nous ne l'anticiperons pas.</p>
  </div>
</section>

{sections}

{bulletin}

<section class="card">
  <h2>Sources, méthode de mise à jour et limites</h2>
  <ul class="tight small">{demi}</ul>
  <h3 style="margin-top:20px">Comment cette page est mise à jour</h3>
  <ul class="tight small">
    <li><strong>Un fichier, pas une saisie manuelle de page</strong> : toutes les lignes vivent dans
    <code>data/candidats2027.json</code>, chacune avec sa source et sa date de déclaration. La page est
    régénérée par script ; elle ne peut pas dériver du fichier.</li>
    <li><strong>Rythme</strong> : vérification hebdomadaire de la liste de référence, et mise à jour
    immédiate à chaque événement — déclaration, retrait, résultat de primaire, investiture. Le premier
    jalon connu est la primaire socialiste des 10 et 11 octobre 2026.</li>
    <li><strong>Jalons suivants</strong> : décret de convocation des électeurs, ouverture du recueil des
    parrainages, publication de la liste par le Conseil constitutionnel — c'est à ce moment que la
    colonne « officialisation » se remplira, pour de bon, sur tout le tableau.</li>
    <li><strong>Ce que cette page ne fait pas</strong> : elle ne juge pas les chances, ne classe pas les
    candidats par popularité et n'anticipe aucune investiture. Les sondages sont sur la page
    <a href="/observatoire/sondages/">Agrégation</a>, où ils sont agrégés séparément.</li>
    <li><strong>Limites assumées</strong> : pour plusieurs candidatures, la presse n'a pas établi de date
    précise — la colonne affiche alors le mois (« ≈ avril 2026 ») plutôt qu'un jour inventé ; et huit
    personnes de la liste de référence n'ont, à ce jour, aucune date documentée.</li>
  </ul>
</section>
</main>
<footer class="wrap">
  <p><a href="/fr/mentions-legales">Mentions légales</a></p>
</footer>
{G.THEME_JS}</body>
</html>
"""


def main():
    d = json.load(open(os.path.join(DATA, "candidats2027.json"), encoding="utf-8"))
    os.makedirs(os.path.join(SITE, "candidats"), exist_ok=True)
    html = render(d)
    open(os.path.join(SITE, "candidats", "index.html"), "w", encoding="utf-8").write(html)
    par = {s: sum(1 for c in d["candidats"] if c["statut"] == s) for s, _, _ in STATUTS}
    print(f"page candidats : {len(d['candidats'])} personnes " + " · ".join(f"{k}={v}" for k, v in par.items()))
    print(f"  -> {os.path.join(SITE, 'candidats', 'index.html')} ({len(html)} caractères)")


if __name__ == "__main__":
    main()
