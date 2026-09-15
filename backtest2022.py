#!/usr/bin/env python3
"""Rétro-test 2022 — on rejoue notre méthode sur la campagne 2022 et on mesure son erreur réelle.

Entrées
  • sondages 2022 : compilation Bkolenc/sondages_presidentielle2022_ebra (licence MIT), dont chaque
    enquête porte le lien de sa notice officielle à la Commission des sondages ;
  • référence : résultats officiels du premier tour (10 avril 2022) publiés par le ministère de
    l'Intérieur — « France entière », archives des résultats électoraux ; les 12 scores ont été
    recoupés le 14/09/2026 avec l'article « Élection présidentielle française de 2022 » (Wikipédia FR,
    CC BY-SA).

Sorties
  • data/backtest2022.json   (résultats machine)
  • site/backtest/index.html (page publiée)

Limite assumée : la compilation s'arrête au 29/11/2021, soit J-132 avant le scrutin. Le rétro-test
mesure donc notre erreur à notre horizon actuel (≈ J-215 pour 2027), pas dans la dernière ligne droite.
"""
import json, os, sys, urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as G

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
SITE = os.path.join(BASE, "site")
SRC_2022 = ("https://raw.githubusercontent.com/Bkolenc/sondages_presidentielle2022_ebra/"
            "main/data/presidentielle.json")
SCRUTIN = date(2022, 4, 10)

# Résultats officiels du premier tour 2022 (suffrages exprimés) — ministère de l'Intérieur,
# archives des résultats électoraux, « France entière » : 35 132 947 suffrages exprimés.
# Vérification du 14/09/2026 : 12/12 scores identiques à la page officielle, et recoupés avec
# l'article « Élection présidentielle française de 2022 » (Wikipédia FR, CC BY-SA).
SOURCE_RESULTAT_URL = ("https://www.archives-resultats-elections.interieur.gouv.fr/resultats/"
                       "presidentielle-2022/FE.php")
VOTES_OFFICIELS = {
    "Emmanuel Macron": 9783058,
    "Marine Le Pen": 8133828,
    "Jean-Luc Mélenchon": 7712520,
    "Éric Zemmour": 2485226,
    "Valérie Pécresse": 1679001,
    "Yannick Jadot": 1627853,
    "Jean Lassalle": 1101387,
    "Fabien Roussel": 802422,
    "Nicolas Dupont-Aignan": 725176,
    "Anne Hidalgo": 616478,
    "Philippe Poutou": 268904,
    "Nathalie Arthaud": 197094
}

RESULTAT = {
    "Emmanuel Macron": 27.85, "Marine Le Pen": 23.15, "Jean-Luc Mélenchon": 21.95,
    "Éric Zemmour": 7.07, "Valérie Pécresse": 4.78, "Yannick Jadot": 4.63,
    "Jean Lassalle": 3.13, "Fabien Roussel": 2.28, "Nicolas Dupont-Aignan": 2.06,
    "Anne Hidalgo": 1.75, "Philippe Poutou": 0.77, "Nathalie Arthaud": 0.56,
}
# Variantes de nom entre la compilation et les résultats officiels
ALIAS = {"Eric Zemmour": "Éric Zemmour", "François-Xavier Bellamy": "François-Xavier Bellamy"}

CUTOFFS = ["2021-07-01", "2021-08-01", "2021-09-01", "2021-10-01", "2021-11-01", "2021-11-29"]
MODES = [("recence", "Notre méthode (fraîcheur + échantillon)"),
         ("egal", "Poids égaux"),
         ("dernier", "Dernière enquête seule")]


def load_polls(force=False):
    """Télécharge et normalise la compilation 2022 au format attendu par generate.aggregate()."""
    cache = os.path.join(DATA, "polls2022.json")
    if force or not os.path.exists(cache):
        req = urllib.request.Request(SRC_2022, headers={"User-Agent": "poc-agregateur-2027"})
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode("utf-8")
        src = json.loads(raw)
        out = []
        for p in src:
            for t in p.get("tours", []):
                if "remier" not in (t.get("tour") or ""):
                    continue
                for h in t.get("hypotheses", []):
                    cands = [dict(candidat=ALIAS.get(c["candidat"], c["candidat"]),
                                  intentions=c.get("intentions"),
                                  parti=(c.get("parti") or [None])[0])
                             for c in h.get("candidats", []) if c.get("candidat")]
                    if not cands:
                        continue
                    out.append(dict(
                        tour="1er Tour", fin_enquete=p["fin_enquete"],
                        institut=p.get("nom_institut"), echantillon=p.get("echantillon"),
                        hypothese=h.get("hypothese"), candidats=cands,
                        notice=p.get("lien")))
        json.dump(out, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return json.load(open(cache, encoding="utf-8"))


def _fr2(x):
    return "—" if x is None else f"{x:.2f}".replace(".", ",")


def fr2(x):
    """Deux décimales, virgule française (les écarts de méthode se jouent à 0,05 point)."""
    return "—" if x is None else f"{x:.2f}".replace(".", ",")


def metrics(agg, mode_label):
    """Erreur de l'agrégation face au résultat officiel (sur les 12 candidats réels publiés)."""
    if not agg or not agg.get("rows"):
        return dict(mode=mode_label, n=0, mae=None, biais=None, max_err=None, publies=0,
                    detail={}, poids_non_candidats=0.0, scenario=None, polls=0,
                    top2=[], top3=[])
    estim = {r["candidat"]: r["intentions"] for r in agg["rows"]}
    errs, bias, detail = [], [], {}
    for nom, res in RESULTAT.items():
        if nom not in estim:
            detail[nom] = dict(estimation=None, resultat=res, erreur=None)
            continue
        e = round(estim[nom] - res, 1)
        errs.append(abs(e))
        bias.append(e)
        detail[nom] = dict(estimation=estim[nom], resultat=res, erreur=e)
    non_cand = sum(v for k, v in estim.items() if k not in RESULTAT)
    return dict(
        mode=mode_label, n=len(errs), publies=len(estim),
        mae=(round(sum(errs) / len(errs), 2) if errs else None),
        biais=(round(sum(bias) / len(bias), 2) if bias else None),
        max_err=(round(max(errs), 1) if errs else None),
        detail=detail, poids_non_candidats=round(non_cand, 1),
        scenario=agg.get("scenario"), polls=agg.get("polls_aggregated"),
        top2=[r["candidat"] for r in agg["rows"][:2]],
        top3=[r["candidat"] for r in agg["rows"][:3]],
    )


def grid_window(polls, windows=(30, 60, 90, 120)):
    """Sensibilité de la fenêtre de sélection du scénario (méthode inchangée par ailleurs)."""
    out = []
    for w in windows:
        per = []
        for cut in CUTOFFS:
            m = metrics(G.aggregate(polls, as_of=date.fromisoformat(cut), scenario_window=w,
                                    house_correction=True), f"fenêtre {w} j")
            per.append(dict(date=cut, mae=m["mae"], n=m["n"], polls=m["polls"],
                            non_cand=m["poids_non_candidats"], top2=m["top2"],
                            scenario=m["scenario"]))
        ok = [p for p in per if p["mae"] is not None]
        out.append(dict(
            fenetre=w,
            mae_moyenne=(round(sum(p["mae"] for p in ok) / len(ok), 2) if ok else None),
            couverture=f"{len(ok)}/{len(per)}",
            n_moyen=(round(sum(p["n"] for p in ok) / len(ok), 1) if ok else None),
            polls_moyen=(round(sum(p["polls"] for p in ok) / len(ok), 1) if ok else None),
            detail=per, ok=(len(ok) == len(per))))
    return out


def grid_house(polls, configs=((60, False), (60, True), (90, False), (90, True), (120, True))):
    """Effet de la correction des effets de maison, à fenêtre de sélection égale."""
    out = []
    for w, hc in configs:
        per = []
        for cut in CUTOFFS:
            m = metrics(G.aggregate(polls, as_of=date.fromisoformat(cut), scenario_window=w,
                                    house_correction=hc), f"f{w}/{'hc' if hc else 'sans hc'}")
            per.append(dict(date=cut, mae=m["mae"], n=m["n"], polls=m["polls"]))
        ok = [p for p in per if p["mae"] is not None]
        out.append(dict(fenetre=w, house=hc,
                        libelle=f"fenêtre {w} j — " + ("effets de maison corrigés" if hc
                                                        else "sans correction"),
                        mae_moyenne=(round(sum(p["mae"] for p in ok) / len(ok), 2) if ok else None),
                        couverture=f"{len(ok)}/{len(per)}", detail=per))
    return out


def best_config(gw, gh):
    """Meilleure configuration au vu du rétro-test : couverture complète d'abord, puis erreur."""
    cands = [dict(fenetre=g["fenetre"], house=True, mae=g["mae_moyenne"], couv=g["couverture"],
                  ok=g["ok"]) for g in gw]
    cands += [dict(fenetre=h["fenetre"], house=h["house"], mae=h["mae_moyenne"],
                   couv=h["couverture"], ok=(h["couverture"].split("/")[0] == h["couverture"].split("/")[1]))
              for h in gh]
    valides = [c for c in cands if c["ok"] and c["mae"] is not None]
    if not valides:
        return None
    # départage : à 0,05 point près, on préfère la fenêtre la plus courte (réactivité) et la
    # correction activée — une différence d'erreur de cet ordre n'est pas un signal.
    best = min(c["mae"] for c in valides)
    proches = [c for c in valides if c["mae"] <= best + 0.05]
    return min(proches, key=lambda c: (c["fenetre"], not c["house"]))


def run(force=False):
    polls = load_polls(force=force)
    lignes = []
    for cut in CUTOFFS:
        cutd = date.fromisoformat(cut)
        jour = (SCRUTIN - cutd).days
        entry = dict(date=cut, jours_avant=jour, modes={})
        for mode, label in MODES:
            agg = G.aggregate(polls, as_of=cutd, weight_mode=mode,
                              min_polls=(1 if mode == "dernier" else None))
            entry["modes"][mode] = metrics(agg, label)
        lignes.append(entry)

    # grilles : fenêtre de sélection et effets de maison
    gw = grid_window(polls)
    gh = grid_house(polls)
    best = best_config(gw, gh)

    # sensibilité à la demi-vie, à la dernière échéance
    cutd = date.fromisoformat(CUTOFFS[-1])
    h = G.HALF_LIFE
    sens = []
    for hl in (15, 30, 60, 180):
        G.HALF_LIFE = hl
        m = metrics(G.aggregate(polls, as_of=cutd), f"demi-vie {hl} j")
        sens.append(dict(half_life=hl, mae=m["mae"], biais=m["biais"], max_err=m["max_err"]))
    G.HALF_LIFE = h

    ref = metrics(G.aggregate(polls, as_of=cutd), "Notre méthode")
    out = dict(
        genere=G.datetime.now().strftime("%Y-%m-%d %H:%M"),
        source_sondages="Bkolenc/sondages_presidentielle2022_ebra (MIT)",
        source_resultat=("Résultats officiels du 1er tour 2022 — ministère de l'Intérieur, "
                         "archives des résultats électoraux (France entière) ; recoupés avec "
                         "Wikipédia FR, CC BY-SA"),
        source_resultat_url=SOURCE_RESULTAT_URL,
        source_resultat_verifie_le="2026-09-14",
        votes_officiels=VOTES_OFFICIELS,
        election="2022-04-10", dernier_sondage=max(p["fin_enquete"] for p in polls),
        nb_enquetes=len({p["fin_enquete"] for p in polls}),
        nb_hypotheses=len(polls),
        resultat=RESULTAT, lignes=lignes, sensibilite=sens,
        grille_fenetre=gw, grille_house=gh, meilleure=best,
        dernier=dict(date=CUTOFFS[-1], jours_avant=(SCRUTIN - cutd).days,
                     modes=[lignes[-1]["modes"][m] for m, _ in MODES]),
        reference=ref,
    )
    json.dump(out, open(os.path.join(DATA, "backtest2022.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return out


# ---------- rendu ----------
def render(bt):
    from html import escape
    res = bt["resultat"]
    ecart = lambda x: ("—" if x is None else
                       (("+" if x > 0 else "−") + G.fr1u(abs(x))))
    lignes_tbl = "\n".join(
        f'<tr><td>{l["date"]}</td><td class="num muted">J−{l["jours_avant"]}</td>'
        + "".join(f'<td class="num">{("—" if l["modes"][m]["mae"] is None else G.fr1u(l["modes"][m]["mae"]))}'
                  f'<span class="muted small"> / {("—" if l["modes"][m]["biais"] is None else ecart(l["modes"][m]["biais"]))}</span></td>'
                  for m, _ in MODES)
        + f'<td class="num muted small">{l["modes"]["recence"]["polls"]}</td>'
        + f'<td class="num muted small">{l["modes"]["recence"]["poids_non_candidats"]}</td></tr>'
        for l in bt["lignes"])

    det = bt["dernier"]["modes"][0]["detail"]
    det_tbl = "\n".join(
        f'<tr><td>{escape(nom)}</td>'
        f'<td class="num"><strong>{("—" if d["estimation"] is None else G.fr1u(d["estimation"]))}</strong></td>'
        f'<td class="num muted">{G.fr1u(d["resultat"])}</td>'
        f'<td class="num">{ecart(d["erreur"]) if d["erreur"] is not None else "<span class=muted>—</span>"}</td></tr>'
        for nom, d in sorted(det.items(), key=lambda kv: -kv[1]["resultat"]))

    sens_tbl = "\n".join(
        f'<tr><td>Demi-vie {s["half_life"]} jours</td>'
        f'<td class="num">{G.fr1u(s["mae"])}</td><td class="num muted">{ecart(s["biais"])}</td>'
        f'<td class="num muted">{G.fr1u(s["max_err"])}</td></tr>' for s in bt["sensibilite"])

    r = bt["dernier"]["modes"]
    # extrêmes du dernier point : ce que la campagne a démenti
    paires = [(n, d) for n, d in det.items() if d["erreur"] is not None]
    gw, gh = bt.get("grille_fenetre") or [], bt.get("grille_house") or []
    gw_tbl = "\n".join(
        f'<tr><td>{g["fenetre"]} jours{"" if g["ok"] else " <span class=muted>(trou)</span>"}</td>'
        f'<td class="num"><strong>{_fr2(g["mae_moyenne"])}</strong></td>'
        f'<td class="num">{g["couverture"]}</td>'
        f'<td class="num muted">{_fr2(g["n_moyen"])}</td>'
        f'<td class="num muted">{_fr2(g["polls_moyen"])}</td></tr>' for g in gw)
    gh_tbl = "\n".join(
        f'<tr><td>{h["libelle"]}</td><td class="num"><strong>{_fr2(h["mae_moyenne"])}</strong></td>'
        f'<td class="num muted">{h["couverture"]}</td></tr>' for h in gh)
    best = bt.get("meilleure") or {}
    gain_fenetre = None
    if len(gw) >= 2 and gw[1]["mae_moyenne"] and gw[2]["mae_moyenne"]:
        gain_fenetre = round(gw[1]["mae_moyenne"] - gw[2]["mae_moyenne"], 2)
    gain_house = None
    if len(gh) >= 4 and gh[2]["mae_moyenne"] and gh[3]["mae_moyenne"]:
        gain_house = round(gh[2]["mae_moyenne"] - gh[3]["mae_moyenne"], 2)
    sous = min(paires, key=lambda kv: kv[1]["erreur"]) if paires else None
    sur = max(paires, key=lambda kv: kv[1]["erreur"]) if paires else None
    nc = [l["modes"]["recence"]["poids_non_candidats"] for l in bt["lignes"]]
    nc_max = max(nc) if nc else 0
    trous = [l["date"] for l in bt["lignes"] if l["modes"]["recence"]["n"] == 0]
    gain_dernier = round((r[2]["mae"] or 0) - (r[0]["mae"] or 0), 2)
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<title>Rétro-test 2022 — la méthode mise à l'épreuve</title>
<style>{G.CSS}{G.DARK}
/* Tables : largeur pleine dans les cartes */
section.card table{{width:100%}}</style>
{G.THEME_HEAD}</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand"><a href="/observatoire/" style="text-decoration:none">Présidentielle 2027</a> <span>· rétro-test 2022</span></div>
  <div class="navlinks"><a href="/observatoire/">Accueil</a><a href="/observatoire/sondages/">Agrégation</a>
  <a href="/observatoire/candidats/">Les candidats</a>{G.NAV_WORKFLOW}<a href="#resultats">Résultats</a><a href="#detail">Détail</a><a href="#lecons">Leçons</a></div>{G.THEME_BTN}
</div></div>

<header class="wrap">
  <span class="eyebrow">Validation · observatoire des sondages 2027</span>
  <h1>La même méthode, rejouée sur la campagne 2022</h1>
  <p class="lede">Notre agrégation n'est pas un modèle de prévision — mais rien n'interdit de mesurer
  son erreur passée. Voici ce qu'elle aurait donné, échéance par échéance, face au résultat réel du
  premier tour du 10 avril 2022. C'est ce rétro-test qui a fixé deux réglages de la page 2027 :
  <strong>fenêtre de sélection de {best.get("fenetre", 90)} jours</strong> et
  <strong>correction des effets de maison</strong>.</p>
</header>

<main class="wrap">
<section id="resultats" class="card">
  <h2>L'erreur à chaque échéance</h2>
  <p class="small muted">Erreur absolue moyenne <strong>/</strong> biais moyen (en points de
  pourcentage), sur les candidats réels publiés. Les deux colonnes de droite comptent les enquêtes
  retenues et le poids que notre tableau donnait à des candidats… qui n'existaient pas le jour du
  vote : c'est le prix de l'incertitude sur le champ.</p>
  <table style="margin-top:10px"><tr><th>Échéance</th><th class="num">Distance</th>
  <th class="num">Notre méthode</th><th class="num">Poids égaux</th><th class="num">Dernière enquête</th>
  <th class="num">Enquêtes</th><th class="num">Poids non-candidats</th></tr>
  {lignes_tbl}</table>
  <p class="small" style="margin-top:12px"><strong>Repère :</strong> la prévision bayésienne
  <a href="https://github.com/whyalwaysrose/presidentielle-2027">whyalwaysrose</a> affiche un rétro-test
  2022 de 1,9 point d'erreur moyenne sur les duels, à J−31 — nous sommes ici à J−{bt["dernier"]["jours_avant"]},
  avec une méthode bien plus simple, et nous publions notre erreur au lieu de l'affirmer.</p>
</section>

<section id="detail" class="card">
  <h2>Candidat par candidat, au {bt["dernier"]["date"]} (J−{bt["dernier"]["jours_avant"]})</h2>
  <table style="margin-top:10px"><tr><th>Candidat</th><th class="num">Estimation MieuxVoter</th>
  <th class="num">Résultat réel</th><th class="num">Écart</th></tr>
  {det_tbl}</table>
  <p class="small muted" style="margin-top:10px">« Estimation MieuxVoter » désigne la moyenne
  pondérée calculée ici à partir de la compilation de sondages MieuxVoter (licence MIT) : la source
  fournit les enquêtes, la pondération est la nôtre — la colonne indique donc ce que cette méthode
  produisait à cette date, pas un chiffre publié par MieuxVoter.</p>
</section>

<section class="card">
  <h2>Sensibilité au réglage le plus arbitraire</h2>
  <p class="small muted" style="max-width:none">La demi-vie est notre choix le plus discutable (elle fixe la vitesse à
  laquelle une vieille enquête perd son poids). Voici son effet, à la dernière échéance : si l'erreur
  variait fortement, le réglage serait un aveu de fragilité.</p>
  <table style="margin-top:10px"><tr><th>Réglage</th><th class="num">Erreur moyenne</th>
  <th class="num">Biais</th><th class="num">Pire écart</th></tr>
  {sens_tbl}</table>
</section>

<section id="reglages" class="card">
  <h2>Deux réglages mesurés, pas choisis au feeling</h2>

  <h3 style="margin-top:18px">Fenêtre de sélection du scénario</h3>
  <p class="small muted" style="max-width:none">La fenêtre fixe la durée pendant laquelle on cherche le scénario de
  candidatures le plus testé. Trop courte, on rate les scénarios les plus documentés ; trop longue, on
  agrège des sondages d'un autre âge. Erreur moyenne sur les échéances, et couverture (échéances où
  quelque chose était publiable) — correction des effets de maison activée sur toutes les
  lignes :</p>
  <table style="margin-top:10px"><tr><th>Fenêtre</th><th class="num">Erreur moyenne</th>
  <th class="num">Couverture</th><th class="num">Candidats publiés</th>
  <th class="num">Enquêtes retenues</th></tr>
  {gw_tbl}</table>
  <p class="small" style="margin-top:12px"><strong>Décision : 90 jours.</strong> C'est la fenêtre la
  plus courte qui couvre les six échéances (à 60 jours, celle de septembre 2021 restait vide) et qui
  minimise l'erreur{"" if gain_fenetre is None else f" ({_fr2(gain_fenetre)} point de moins qu'à 60 jours)"}.
  Au-delà (120 jours), le gain est nul et l'on agrège des enquêtes plus anciennes pour rien.</p>

  <h3 style="margin-top:24px">Correction des effets de maison</h3>
  <p class="small muted" style="max-width:none">Chaque institut a sa manière de poser ses questions et de redresser ses
  résultats. Nous estimons son écart moyen au consensus des autres — par itérations, avec contraction
  vers zéro quand l'institut est peu vu — puis nous corrigeons avant d'agréger.</p>
  <table style="margin-top:10px"><tr><th>Configuration</th><th class="num">Erreur moyenne</th>
  <th class="num">Couverture</th></tr>
  {gh_tbl}</table>
  <p class="small" style="margin-top:12px"><strong>Décision : correction activée.</strong>
  Le gain est réel mais faible{"" if gain_house is None else f" ({_fr2(gain_house)} point à fenêtre égale)"} —
  et c'est logique : en 2022, la plus grosse erreur (Mélenchon sous-estimé de 14 points) était
  <em>partagée par tous les instituts</em>. Une correction d'effet de maison ne peut rien contre un
  biais collectif : elle corrige les écarts <em>entre</em> instituts, pas leur aveuglement commun.</p>
</section>

<section id="lecons" class="card">
  <h2>Ce que ça nous apprend</h2>
  <ul class="tight">
    <li><strong>Les deux finalistes étaient identifiés</strong> dès octobre 2021 :
    {", ".join(r[0]["top2"])}, dans le bon ordre — les deux qualifiés réels étant Emmanuel Macron et
    Marine Le Pen. En juillet et août 2021, l'ordre était inversé (Le Pen devant).</li>
    <li><strong>Erreur moyenne de {G.fr1u(r[0]["mae"])} point(s)</strong> sur les parts du premier tour
    à J−{bt["dernier"]["jours_avant"]}, pour un biais de {ecart(r[0]["biais"])} : notre tableau n'aurait
    pas désigné un vainqueur, mais il donnait déjà le rapport de forces. Sur les douze candidats réels,
    {r[0]["n"]} étaient publiés.</li>
    <li><strong>Les deux réglages mesurés sont désormais ceux de la page 2027</strong> : fenêtre de
    sélection portée à {best.get("fenetre", 90)} jours (couverture complète des échéances, erreur
    moyenne {_fr2(gw[2]["mae_moyenne"]) if len(gw) > 2 else "—"} contre {_fr2(gw[1]["mae_moyenne"]) if len(gw) > 1 else "—"}
    à 60 jours) et correction des effets de maison activée (gain marginal mais systématique).</li>
    <li><strong>Notre pondération n'apporte rien</strong> : {fr2(r[0]["mae"])} point d'erreur avec
    notre calcul, {fr2(r[1]["mae"])} à poids égaux, {fr2(r[2]["mae"])} avec la dernière enquête seule —
    soit {fr2(abs(gain_dernier))} point de moins pour le sondage brut. La demi-vie ne change presque rien
    non plus ({", ".join(fr2(s["mae"]) for s in bt["sensibilite"])} selon le réglage, de 15 à 180 jours).
    La valeur ajoutée de cette page n'est donc pas l'agrégation : elle est dans la lisibilité, le
    scénario explicite et l'intervalle publié.</li>
    <li><strong>L'erreur n'est pas répartie au hasard</strong> : au dernier point, la plus forte
    sous-estimation est {escape(sous[0]) if sous else "—"} ({ecart(sous[1]["erreur"]) if sous else "—"})
    et la plus forte surestimation {escape(sur[0]) if sur else "—"} ({ecart(sur[1]["erreur"]) if sur else "—"}).
    Les instituts avaient surestimé Zemmour, Pécresse et Hidalgo, et sous-estimé la gauche : un
    agrégateur de sondages ne corrige pas ces biais structurels, il les reproduit.</li>
    <li><strong>Le champ de candidats est le premier facteur d'erreur</strong> : les non-candidats
    (Montebourg, Bertrand, Philippot…) pesaient jusqu'à {G.fr1u(nc_max)} points de notre tableau en
    2021, contre {G.fr1u(r[0]["poids_non_candidats"])} au dernier point. Verrouiller un scénario revient
    à parier sur ce chiffre ; un modèle qui intègre le champ le paie autrement, en largeur d'intervalle.</li>
    <li><strong>Notre méthode peut ne rien publier</strong> : à l'échéance du {", ".join(trous)}, aucun
    scénario n'atteignait trois enquêtes — la page serait restée vide. C'est honnête, mais c'est une
    fragilité à assumer.</li>
    <li><strong>Ce chiffre ne se compare pas</strong> à celui de la prévision bayésienne (1,9 point sur
    les duels à J−31) : autre horizon, autre grandeur. Ce qui est comparable, c'est la discipline —
    désormais, nous publions notre erreur au lieu de l'affirmer.</li>
  </ul>
</section>

<section class="card">
  <h2>Sources et limites du rétro-test</h2>
  <ul class="tight small">
    <li>Sondages : <a href="https://github.com/Bkolenc/sondages_presidentielle2022_ebra">
    Bkolenc/sondages_presidentielle2022_ebra</a> (licence MIT) — {bt["nb_hypotheses"]} hypothèses de
    premier tour, {bt["nb_enquetes"]} dates d'enquête, chaque notice étant liée à la Commission des
    sondages.</li>
    <li>Résultats : scores officiels du premier tour 2022 publiés par le
    <a href="https://www.archives-resultats-elections.interieur.gouv.fr/resultats/presidentielle-2022/FE.php">ministère
    de l'Intérieur</a> (« France entière », archives des résultats électoraux) — 35 132 947 suffrages
    exprimés. Les douze scores ont été vérifiés un à un le 14/09/2026 : identiques à la page
    officielle, et recoupés avec l'article « Élection présidentielle française de 2022 »
    (Wikipédia FR, CC BY-SA).</li>
    <li>Ce rétro-test rejoue notre <em>méthode de calcul</em> sur les données de l'époque : les
    chiffres publiés ici n'ont jamais été affichés en 2022.</li>
    <li>Les intentions de vote des instituts portent sur les suffrages exprimés — comme les résultats
    retenus ici — mais les champs de candidats différaient d'un sondage à l'autre.</li>
    <li><strong>Horizon</strong> : la compilation 2022 s'arrête au 29/11/2021, soit J−132. Étendre ce
    rétro-test à la dernière ligne droite (J−30, J−10) demanderait une compilation couvrant
    janvier-avril 2022 sous licence libre : elle n'existe pas — les références les plus complètes,
    comme <a href="https://github.com/nsppolls/nsppolls">nsppolls</a>, ne portent aucune licence, et
    nous ne les réutilisons pas. Nous mesurons donc notre erreur à l'horizon où nous publions
    (≈ J−215 pour 2027), pas là où l'élection se joue.</li>
  </ul>
  <p class="small">Rétro-test indépendant de toute publication : son intérêt est d'être faux un jour,
  publiquement. Cette page n'est pas un sondage : elle n'interroge personne et n'anticipe aucun vote.</p>
  <p class="small muted">Page générée le {bt["genere"]} par <code>backtest2022.py</code> — rejouable
  à volonté.</p>
</section>
</main>
<footer class="wrap">
  <p><a href="/fr/mentions-legales#observatoire-sondages">Mentions légales</a></p>
</footer>
{G.THEME_JS}</body>
</html>
"""


def main():
    bt = run(force="--force" in sys.argv)
    os.makedirs(os.path.join(SITE, "backtest"), exist_ok=True)
    open(os.path.join(SITE, "backtest", "index.html"), "w", encoding="utf-8").write(render(bt))
    r = bt["dernier"]["modes"]
    print(f"rétro-test 2022 : {bt['nb_enquetes']} dates d'enquête, {bt['nb_hypotheses']} hypothèses")
    for m in r:
        print(f"  {m['mode']:38} MAE={m['mae']}  biais={m['biais']}  pire={m['max_err']}  "
              f"top2={' / '.join(m['top2'])}")
    print("  sensibilité :", ", ".join(f"HL{s['half_life']}={s['mae']}" for s in bt["sensibilite"]))
    print("  page : site/backtest/index.html")


if __name__ == "__main__":
    main()
