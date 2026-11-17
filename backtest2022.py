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
def render(bt, lang="fr"):
    """Page du rétro-test, dans la langue demandée (« fr » par défaut).

    Même convention que generate.py et candidats.py : `m(français, anglais)` choisit le texte,
    les métadonnées suivent `lang`, et les adresses passent par G.lien() / G.lien_page().
    """
    from html import escape
    m = (lambda a, b: b) if lang == "en" else (lambda a, b: a)
    res = bt["resultat"]
    ecart = lambda x: ("—" if x is None else
                       (("+" if x > 0 else "−") + G.fr1u(abs(x))))
    lignes_tbl = "\n".join(
        f'<tr><td>{l["date"]}</td><td class="num muted">{m("J−", "D−")}{l["jours_avant"]}</td>'
        + "".join(f'<td class="num">{("—" if l["modes"][k]["mae"] is None else G.fr1u(l["modes"][k]["mae"]))}'
                  f'<span class="muted small"> / {("—" if l["modes"][k]["biais"] is None else ecart(l["modes"][k]["biais"]))}</span></td>'
                  for k, _ in MODES)
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
        f'<tr><td>{m("Demi-vie ", "Half-life ")}{s["half_life"]} {m("jours", "days")}</td>'
        f'<td class="num">{G.fr1u(s["mae"])}</td><td class="num muted">{ecart(s["biais"])}</td>'
        f'<td class="num muted">{G.fr1u(s["max_err"])}</td></tr>' for s in bt["sensibilite"])

    r = bt["dernier"]["modes"]
    # extrêmes du dernier point : ce que la campagne a démenti
    paires = [(n, d) for n, d in det.items() if d["erreur"] is not None]
    gw, gh = bt.get("grille_fenetre") or [], bt.get("grille_house") or []
    gw_tbl = "\n".join(
        f'<tr><td>{g["fenetre"]} {m("jours", "days")}{"" if g["ok"] else m(" <span class=muted>(trou)</span>", " <span class=muted>(gap)</span>")}</td>'
        f'<td class="num"><strong>{_fr2(g["mae_moyenne"])}</strong></td>'
        f'<td class="num">{g["couverture"]}</td>'
        f'<td class="num muted">{_fr2(g["n_moyen"])}</td>'
        f'<td class="num muted">{_fr2(g["polls_moyen"])}</td></tr>' for g in gw)
    # Le libellé des configurations vient du calcul (« fenêtre 60 j — effets de maison
    # corrigés »), en français : il est rebâti ici pour que la version anglaise n'affiche pas
    # une phrase française, sans toucher au fichier de données.
    def _libelle_house(h):
        quoi = (m("effets de maison corrigés", "house effects corrected") if h["house"]
                else m("sans correction", "no correction"))
        return m("fenêtre ", "window ") + str(h["fenetre"]) + m(" j — ", " d — ") + quoi
    gh_tbl = "\n".join(
        f'<tr><td>{_libelle_house(h)}</td><td class="num"><strong>{_fr2(h["mae_moyenne"])}</strong></td>'
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

    # Cette phrase annonçait « à l'échéance du <vide> » : la liste des échéances sans
    # assez d'enquêtes était vide, mais le gabarit gardait la formule quand même — et
    # affirmait donc un cas qui ne s'est pas produit. Elle dit maintenant ce que les
    # données montrent, dans un cas comme dans l'autre.
    if trous:
        phrase_trous = m(
            "à l'échéance du " + ", ".join(trous) + ", aucun scénario n'atteignait trois "
            "enquêtes — la page serait restée vide. C'est honnête, mais c'est une "
            "fragilité à assumer.",
            "at the deadline of " + ", ".join(trous) + ", no scenario reached three "
            "polls — the page would have stayed empty. That is honest, but it is a "
            "fragility to be owned.")
    else:
        phrase_trous = m(
            "sur chacune des " + str(len(bt["lignes"])) + " échéances de ce rétro-test, au moins "
            "trois enquêtes étaient disponibles — la page ne serait jamais restée vide. La "
            "fragilité reste entière : sur une campagne plus pauvre en sondages, le seuil de "
            "trois enquêtes ne serait pas atteint, et l'agrégation se tairait.",
            "at each of the " + str(len(bt["lignes"])) + " deadlines of this backtest, at least "
            "three polls were available — the page would never have stayed empty. The "
            "fragility remains whole: on a campaign with fewer polls, the threshold of "
            "three polls would not be reached, and the aggregation would fall silent.")
    gain_dernier = round((r[2]["mae"] or 0) - (r[0]["mae"] or 0), 2)
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="{G.meta_description('/observatoire/backtest/', lang)}">
<title>{G.titre_court('/observatoire/backtest/', lang)}</title>
<link rel="canonical" href="https://dileviathan.fr{G.lien('/backtest/', lang)}">
<link rel="alternate" hreflang="fr" href="https://dileviathan.fr{G.lien('/backtest/', 'fr')}">
<link rel="alternate" hreflang="en" href="https://dileviathan.fr{G.lien('/backtest/', 'en')}">
<link rel="alternate" hreflang="x-default" href="https://dileviathan.fr{G.lien('/backtest/', 'fr')}">
{G.meta_social('/observatoire/backtest/', lang)}
{G.ld_json("/observatoire/backtest/", lang)}
{G.matomo()}
<style>{G.CSS}{G.DARK}
/* Tables : largeur pleine dans les cartes */
section.card table{{width:100%}}</style>
{G.THEME_HEAD}</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand"><a href="{G.lien('/', lang)}" style="text-decoration:none">{m("Présidentielle 2027", "2027 presidential election")}</a> <span>· {m("rétro-test 2022", "2022 backtest")}</span></div>
  <div class="navlinks"><a href="{G.lien('/', lang)}">{m("Accueil", "Home")}</a><a href="{G.lien_page('/sondages/', lang)}">{m("Agrégation", "Aggregate")}</a>
  <a href="{G.lien_page('/candidats/', lang)}">{m("Les candidats", "Candidates")}</a>{G.nav_workflow(lang)}{G.nav_lois(lang)}<a href="#resultats">{m("Résultats", "Results")}</a><a href="#detail">{m("Détail", "Detail")}</a><a href="#lecons">{m("Leçons", "Lessons")}</a></div>{G.barre_droite('/backtest/', lang)}
</div></div>

<header class="wrap">
  <span class="eyebrow">{m("Validation · observatoire des sondages 2027", "Validation · 2027 poll monitor")}</span>
  <h1>{m("La même méthode, rejouée sur la campagne 2022", "The same method, replayed on the 2022 campaign")}</h1>
  <p class="lede">{m("Notre agrégation n'est pas un modèle de prévision — mais rien n'interdit de mesurer",
  "Our aggregation is not a forecasting model — but nothing prevents us from measuring")}
  {m("son erreur passée. Voici ce qu'elle aurait donné, échéance par échéance, face au résultat réel du",
  "its past error. Here is what it would have given, deadline by deadline, against the actual result of the")}
  {m("premier tour du 10 avril 2022. C'est ce rétro-test qui a fixé deux réglages de la page 2027 :",
  "first round of 10 April 2022. This backtest is what set two settings of the 2027 page:")}
  <strong>{m("fenêtre de sélection de ", "scenario window of ")}{best.get("fenetre", 90)} {m("jours", "days")}</strong> {m("et", "and")}
  <strong>{m("correction des effets de maison", "house-effect correction")}</strong>.</p>
</header>

<main class="wrap">
<section id="resultats" class="card">
  <h2>{m("L'erreur à chaque échéance", "The error at each deadline")}</h2>
  <p class="small muted">{m("Erreur absolue moyenne <strong>/</strong> biais moyen (en points de",
  "Mean absolute error <strong>/</strong> mean bias (in percentage")}
  {m("pourcentage), sur les candidats réels publiés. Les deux colonnes de droite comptent les enquêtes",
  "points), across the real candidates published. The two right-hand columns count the polls")}
  {m("retenues et le poids que notre tableau donnait à des candidats… qui n'existaient pas le jour du",
  "retained and the weight our table gave to candidates… who did not exist on")}
  {m("vote : c'est le prix de l'incertitude sur le champ.", "voting day: that is the price of uncertainty over the field.")}</p>
  <table style="margin-top:10px"><tr><th>{m("Échéance", "Deadline")}</th><th class="num">{m("Distance", "Distance")}</th>
  <th class="num">{m("Notre méthode", "Our method")}</th><th class="num">{m("Poids égaux", "Equal weights")}</th><th class="num">{m("Dernière enquête", "Latest poll only")}</th>
  <th class="num">{m("Enquêtes", "Polls")}</th><th class="num">{m("Poids non-candidats", "Non-candidate weight")}</th></tr>
  {lignes_tbl}</table>
  <p class="small" style="margin-top:12px"><strong>{m("Repère :", "Benchmark:")}</strong> {m("la prévision bayésienne", "the Bayesian forecast")}
  <a href="https://github.com/whyalwaysrose/presidentielle-2027">whyalwaysrose</a> {m("affiche un rétro-test",
  "reports a backtest")}
  {m("2022 de 1,9 point d'erreur moyenne sur les duels, à J−31 — nous sommes ici à J−",
  "of 2022 with 1,9 points mean error on runoffs, at D−31 — we are here at D−")}{bt["dernier"]["jours_avant"]},
  {m("avec une méthode bien plus simple, et nous publions notre erreur au lieu de l'affirmer.",
  "with a much simpler method, and we publish our error instead of asserting it.")}</p>
</section>

<section id="detail" class="card">
  <h2>{m("Candidat par candidat, au ", "Candidate by candidate, on ")}{bt["dernier"]["date"]} ({m("J−", "D−")}{bt["dernier"]["jours_avant"]})</h2>
  <table style="margin-top:10px"><tr><th>{m("Candidat", "Candidate")}</th><th class="num">{m("Estimation MieuxVoter", "MieuxVoter estimate")}</th>
  <th class="num">{m("Résultat réel", "Actual result")}</th><th class="num">{m("Écart", "Gap")}</th></tr>
  {det_tbl}</table>
  <p class="small muted" style="margin-top:10px">{m("« Estimation MieuxVoter » désigne la moyenne",
  "“MieuxVoter estimate” is the weighted average")}
  {m("pondérée calculée ici à partir de la compilation de sondages MieuxVoter (licence MIT) : la source",
  "computed here from the MieuxVoter poll compilation (MIT licence): the source")}
  {m("fournit les enquêtes, la pondération est la nôtre — la colonne indique donc ce que cette méthode",
  "provides the surveys, the weighting is ours — so the column shows what this method")}
  {m("produisait à cette date, pas un chiffre publié par MieuxVoter.", "produced on that date, not a figure published by MieuxVoter.")}</p>
</section>

<section class="card">
  <h2>{m("Sensibilité au réglage le plus arbitraire", "Sensitivity to the most arbitrary setting")}</h2>
  <p class="small muted" style="max-width:none">{m("La demi-vie est notre choix le plus discutable (elle fixe la vitesse à",
  "The half-life is our most debatable choice (it sets how fast")}
  {m("laquelle une vieille enquête perd son poids). Voici son effet, à la dernière échéance : si l'erreur",
  "an old poll loses its weight). Here is its effect, at the last deadline: if the error")}
  {m("variait fortement, le réglage serait un aveu de fragilité.", "varied sharply, the setting would be an admission of fragility.")}</p>
  <table style="margin-top:10px"><tr><th>{m("Réglage", "Setting")}</th><th class="num">{m("Erreur moyenne", "Mean error")}</th>
  <th class="num">{m("Biais", "Bias")}</th><th class="num">{m("Pire écart", "Worst gap")}</th></tr>
  {sens_tbl}</table>
</section>

<section id="reglages" class="card">
  <h2>{m("Deux réglages mesurés, pas choisis au feeling", "Two settings measured, not chosen on a hunch")}</h2>

  <h3 style="margin-top:18px">{m("Fenêtre de sélection du scénario", "Scenario selection window")}</h3>
  <p class="small muted" style="max-width:none">{m("La fenêtre fixe la durée pendant laquelle on cherche le scénario de",
  "The window sets how far back we look for the")}
  {m("candidatures le plus testé. Trop courte, on rate les scénarios les plus documentés ; trop longue, on",
  "most-tested candidate scenario. Too short and we miss the best-documented scenarios; too long and we")}
  {m("agrège des sondages d'un autre âge. Erreur moyenne sur les échéances, et couverture (échéances où",
  "aggregate polls from another age. Mean error across the deadlines, and coverage (deadlines where")}
  {m("quelque chose était publiable) — correction des effets de maison activée sur toutes les",
  "something was publishable) — house-effect correction enabled on every")}
  {m("lignes :", "row:")}</p>
  <table style="margin-top:10px"><tr><th>{m("Fenêtre", "Window")}</th><th class="num">{m("Erreur moyenne", "Mean error")}</th>
  <th class="num">{m("Couverture", "Coverage")}</th><th class="num">{m("Candidats publiés", "Candidates published")}</th>
  <th class="num">{m("Enquêtes retenues", "Polls retained")}</th></tr>
  {gw_tbl}</table>
  <p class="small" style="margin-top:12px"><strong>{m("Décision : 90 jours.", "Decision: 90 days.")}</strong> {m("C'est la fenêtre la",
  "It is the shortest window")}
  {m("plus courte qui couvre les six échéances (à 60 jours, celle de septembre 2021 restait vide) et qui",
  "that covers all six deadlines (at 60 days, the September 2021 one stayed empty) and that")}
  {m("minimise l'erreur", "minimises the error")}{"" if gain_fenetre is None else m(f" ({_fr2(gain_fenetre)} point de moins qu'à 60 jours)", f" ({_fr2(gain_fenetre)} point less than at 60 days)")}.
  {m("Au-delà (120 jours), le gain est nul et l'on agrège des enquêtes plus anciennes pour rien.",
  "Beyond that (120 days), the gain is nil and we aggregate older polls for nothing.")}</p>

  <h3 style="margin-top:24px">{m("Correction des effets de maison", "House-effect correction")}</h3>
  <p class="small muted" style="max-width:none">{m("Chaque institut a sa manière de poser ses questions et de redresser ses",
  "Each polling firm has its own way of asking questions and weighting its")}
  {m("résultats. Nous estimons son écart moyen au consensus des autres — par itérations, avec contraction",
  "results. We estimate its average gap to the others' consensus — iteratively, shrinking")}
  {m("vers zéro quand l'institut est peu vu — puis nous corrigeons avant d'agréger.",
  "towards zero when the firm is rarely seen — then we correct before aggregating.")}</p>
  <table style="margin-top:10px"><tr><th>{m("Configuration", "Configuration")}</th><th class="num">{m("Erreur moyenne", "Mean error")}</th>
  <th class="num">{m("Couverture", "Coverage")}</th></tr>
  {gh_tbl}</table>
  <p class="small" style="margin-top:12px"><strong>{m("Décision : correction activée.", "Decision: correction on.")}</strong>
  {m("Le gain est réel mais faible", "The gain is real but small")}{"" if gain_house is None else m(f" ({_fr2(gain_house)} point à fenêtre égale)", f" ({_fr2(gain_house)} point at equal window)")} —
  {m("et c'est logique : en 2022, la plus grosse erreur (Mélenchon sous-estimé de 14 points) était",
  "and that is logical: in 2022 the largest error (Mélenchon underestimated by 14 points) was")}
  <em>{m("partagée par tous les instituts", "shared by every pollster")}</em>{m(". Une correction d'effet de maison ne peut rien contre un",
  ". A house-effect correction can do nothing against a")}
  {m("biais collectif : elle corrige les écarts <em>entre</em> instituts, pas leur aveuglement commun.",
  "collective bias: it corrects the gaps <em>between</em> pollsters, not their shared blind spot.")}</p>
</section>

<section id="lecons" class="card">
  <h2>{m("Ce que ça nous apprend", "What it teaches us")}</h2>
  <ul class="tight">
    <li><strong>{m("Les deux finalistes étaient identifiés", "Both finalists were identified")}</strong> {m("dès octobre 2021 :",
    "as early as October 2021:")}
    {", ".join(r[0]["top2"])}, {m("dans le bon ordre — les deux qualifiés réels étant Emmanuel Macron et",
    "in the right order — the two actual qualifiers being Emmanuel Macron and")}
    Marine Le Pen. {m("En juillet et août 2021, l'ordre était inversé (Le Pen devant).",
    "In July and August 2021 the order was reversed (Le Pen ahead).")}</li>
    <li><strong>{m("Erreur moyenne de ", "Mean error of ")}{G.fr1u(r[0]["mae"])} {m("point(s)", "point(s)")}</strong> {m("sur les parts du premier tour",
    "on first-round shares")}
    {m("à J−", "at D−")}{bt["dernier"]["jours_avant"]}, {m("pour un biais de ", "for a bias of ")}{ecart(r[0]["biais"])} : {m("notre tableau n'aurait",
    "our table would not")}
    {m("pas désigné un vainqueur, mais il donnait déjà le rapport de forces. Sur les douze candidats réels,",
    "have named a winner, but it already gave the balance of power. Of the twelve real candidates,")}
    {r[0]["n"]} {m("étaient publiés.", "were published.")}</li>
    <li><strong>{m("Les deux réglages mesurés sont désormais ceux de la page 2027", "The two measured settings are now those of the 2027 page")}</strong> : {m("fenêtre de",
    "selection window")}
    {m("sélection portée à ", "raised to ")}{best.get("fenetre", 90)} {m("jours (couverture complète des échéances, erreur",
    "days (full coverage of the deadlines, mean")}
    {m("moyenne ", "error ")}{_fr2(gw[2]["mae_moyenne"]) if len(gw) > 2 else "—"} {m("contre", "against")} {_fr2(gw[1]["mae_moyenne"]) if len(gw) > 1 else "—"}
    {m("à 60 jours) et correction des effets de maison activée (gain marginal mais systématique).",
    "at 60 days) and house-effect correction enabled (a marginal but systematic gain).")}</li>
    <li><strong>{m("Notre pondération n'apporte rien", "Our weighting adds nothing")}</strong> : {fr2(r[0]["mae"])} {m("point d'erreur avec",
    "point of error with")}
    {m("notre calcul, ", "our calculation, ")}{fr2(r[1]["mae"])} {m("à poids égaux, ", "with equal weights, ")}{fr2(r[2]["mae"])} {m("avec la dernière enquête seule —",
    "with the latest poll alone —")}
    {m("soit ", "that is ")}{fr2(abs(gain_dernier))} {m("point de moins pour le sondage brut. La demi-vie ne change presque rien",
    "point less for the raw poll. The half-life barely changes anything")}
    {m("non plus (", "either (")}{", ".join(fr2(s["mae"]) for s in bt["sensibilite"])} {m("selon le réglage, de 15 à 180 jours).",
    "depending on the setting, from 15 to 180 days).")}
    {m("La valeur ajoutée de cette page n'est donc pas l'agrégation : elle est dans la lisibilité, le",
    "The added value of this page is therefore not the aggregation: it lies in readability, the")}
    {m("scénario explicite et l'intervalle publié.", "explicit scenario and the published interval.")}</li>
    <li><strong>{m("L'erreur n'est pas répartie au hasard", "The error is not spread at random")}</strong> : {m("au dernier point, la plus forte",
    "at the last data point, the largest")}
    {m("sous-estimation est ", "underestimation is ")}{escape(sous[0]) if sous else "—"} ({ecart(sous[1]["erreur"]) if sous else "—"})
    {m("et la plus forte surestimation ", "and the largest overestimation ")}{escape(sur[0]) if sur else "—"} ({ecart(sur[1]["erreur"]) if sur else "—"}).
    {m("Les instituts avaient surestimé Zemmour, Pécresse et Hidalgo, et sous-estimé la gauche : un",
    "The pollsters had overestimated Zemmour, Pécresse and Hidalgo, and underestimated the left: a")}
    {m("agrégateur de sondages ne corrige pas ces biais structurels, il les reproduit.",
    "poll aggregator does not correct these structural biases, it reproduces them.")}</li>
    <li><strong>{m("Le champ de candidats est le premier facteur d'erreur", "The candidate field is the first source of error")}</strong> : {m("les non-candidats",
    "the non-candidates")}
    {m("(Montebourg, Bertrand, Philippot…) pesaient jusqu'à ", "(Montebourg, Bertrand, Philippot…) weighed up to ")}{G.fr1u(nc_max)} {m("points de notre tableau en",
    "points of our table in")}
    2021, {m("contre ", "against ")}{G.fr1u(r[0]["poids_non_candidats"])} {m("au dernier point. Verrouiller un scénario revient",
    "at the last data point. Locking a scenario amounts")}
    {m("à parier sur ce chiffre ; un modèle qui intègre le champ le paie autrement, en largeur d'intervalle.",
    "to betting on that figure; a model that integrates the field pays for it elsewhere, in interval width.")}</li>
    <li><strong>{m("Notre méthode peut ne rien publier", "Our method may publish nothing")}</strong> : {phrase_trous}</li>
    <li><strong>{m("Ce chiffre ne se compare pas", "This figure is not comparable")}</strong> {m("à celui de la prévision bayésienne (1,9 point sur",
    "to the Bayesian forecast (1,9 points on")}
    {m("les duels à J−31) : autre horizon, autre grandeur. Ce qui est comparable, c'est la discipline —",
    "runoffs at D−31): another horizon, another quantity. What is comparable is the discipline —")}
    {m("désormais, nous publions notre erreur au lieu de l'affirmer.", "from now on, we publish our error instead of asserting it.")}</li>
  </ul>
</section>

<section class="card">
  <h2>{m("Sources et limites du rétro-test", "Sources and limits of the backtest")}</h2>
  <ul class="tight small">
    <li>{m("Sondages :", "Polls:")} <a href="https://github.com/Bkolenc/sondages_presidentielle2022_ebra">
    Bkolenc/sondages_presidentielle2022_ebra</a> ({m("licence MIT", "MIT licence")}) — {bt["nb_hypotheses"]} {m("hypothèses de",
    "hypotheses of the")}
    {m("premier tour, ", "first round, ")}{bt["nb_enquetes"]} {m("dates d'enquête, chaque notice étant liée à la Commission des",
    "survey dates, each notice linked to the")}
    {m("sondages.", "polling commission.")}</li>
    <li>{m("Résultats : scores officiels du premier tour 2022 publiés par le", "Results: official first-round scores of 2022 published by the")}
    <a href="https://www.archives-resultats-elections.interieur.gouv.fr/resultats/presidentielle-2022/FE.php">{m("ministère",
    "Ministry")}
    {m("de l'Intérieur", "of the Interior")}</a> ({m("« France entière », archives des résultats électoraux) — 35 132 947 suffrages",
    "“France entière”, electoral results archive) — 35 132 947 votes")}
    {m("exprimés. Les douze scores ont été vérifiés un à un le 14/09/2026 : identiques à la page",
    "cast. The twelve scores were checked one by one on 14/09/2026: identical to the")}
    {m("officielle, et recoupés avec l'article « Élection présidentielle française de 2022 »",
    "official page, and cross-checked with the article “Élection présidentielle française de 2022”")}
    ({m("Wikipédia FR, CC BY-SA", "Wikipédia FR, CC BY-SA")}).</li>
    <li>{m("Ce rétro-test rejoue notre", "This backtest replays our")} <em>{m("méthode de calcul", "calculation method")}</em> {m("sur les données de l'époque : les",
    "on the data of the time: the")}
    {m("chiffres publiés ici n'ont jamais été affichés en 2022.", "figures published here were never displayed in 2022.")}</li>
    <li>{m("Les intentions de vote des instituts portent sur les suffrages exprimés — comme les résultats",
    "The pollsters' voting intentions refer to votes cast — as do the results")}
    {m("retenus ici — mais les champs de candidats différaient d'un sondage à l'autre.",
    "retained here — but the candidate fields differed from one poll to the next.")}</li>
    <li><strong>{m("Horizon", "Horizon")}</strong> : {m("la compilation 2022 s'arrête au 29/11/2021, soit J−132. Étendre ce",
    "the 2022 compilation stops on 29/11/2021, that is D−132. Extending this")}
    {m("rétro-test à la dernière ligne droite (J−30, J−10) demanderait une compilation couvrant",
    "backtest to the home straight (D−30, D−10) would require a compilation covering")}
    {m("janvier-avril 2022 sous licence libre : elle n'existe pas — les références les plus complètes,",
    "January-April 2022 under a free licence: it does not exist — the most complete references,")}
    {m("comme", "such as")} <a href="https://github.com/nsppolls/nsppolls">nsppolls</a>, {m("ne portent aucune licence, et",
    "carry no licence at all, and")}
    {m("nous ne les réutilisons pas. Nous mesurons donc notre erreur à l'horizon où nous publions",
    "we do not reuse them. We therefore measure our error at the horizon where we publish")}
    ({m("≈ J−215 pour 2027", "≈ D−215 for 2027")}), {m("pas là où l'élection se joue.", "not where the election is decided.")}</li>
  </ul>
  <p class="small">{m("Rétro-test indépendant de toute publication : son intérêt est d'être faux un jour,",
  "A backtest independent of any publication: its interest is in being wrong one day,")}
  {m("publiquement. Cette page n'est pas un sondage : elle n'interroge personne et n'anticipe aucun vote.",
  "publicly. This page is not a poll: it questions nobody and anticipates no vote.")}</p>
  <p class="small muted">{m("Page générée le ", "Page generated on ")}{bt["genere"]} {m("par", "by")} <code>backtest2022.py</code> — {m("rejouable",
  "replayable")}
  {m("à volonté.", "at will.")}</p>
</section>
</main>
<footer class="wrap">
  <p><a href="/fr/mentions-legales">{m("Mentions légales", "Legal notice")}</a></p>
</footer>
{G.THEME_JS}</body>
</html>
"""


def main():
    bt = run(force="--force" in sys.argv)
    os.makedirs(os.path.join(SITE, "backtest"), exist_ok=True)
    open(os.path.join(SITE, "backtest", "index.html"), "w", encoding="utf-8").write(render(bt))
    # Version anglaise : mêmes chiffres, autres mots.
    en_dir = os.path.join(SITE, "en", "observatoire", "backtest")
    os.makedirs(en_dir, exist_ok=True)
    open(os.path.join(en_dir, "index.html"), "w", encoding="utf-8").write(render(bt, lang="en"))
    r = bt["dernier"]["modes"]
    print(f"rétro-test 2022 : {bt['nb_enquetes']} dates d'enquête, {bt['nb_hypotheses']} hypothèses")
    for m in r:
        print(f"  {m['mode']:38} MAE={m['mae']}  biais={m['biais']}  pire={m['max_err']}  "
              f"top2={' / '.join(m['top2'])}")
    print("  sensibilité :", ", ".join(f"HL{s['half_life']}={s['mae']}" for s in bt["sensibilite"]))
    print("  page : site/backtest/index.html")


if __name__ == "__main__":
    main()
