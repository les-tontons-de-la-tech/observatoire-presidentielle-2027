#!/usr/bin/env python3
"""
POC — Agrégation des sondages de la présidentielle 2027 (sandbox).

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
  - aucune correction des effets de maison : ce POC ne prétend pas à la
    précision d'un modèle d'agrégation professionnel.
"""
import json, math, os, urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta

SRC = "https://raw.githubusercontent.com/MieuxVoter/presidentielle2027/refs/heads/main/presidentielle2027.json"
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
SITE = os.path.join(BASE, "site")
SCENARIO_WINDOW = 60   # fenêtre de sélection du scénario (fraîcheur)
AGG_WINDOW = 180       # fenêtre d'agrégation des sondages du scénario retenu
HALF_LIFE = 30         # demi-vie du poids temporel (jours)
MIN_POLLS = 3          # nombre minimum de sondages pour être publié
IC_FLOOR = 1.0         # plancher de l'intervalle (± points) : anti-fausse précision
TODAY = date.today()


def fetch(force=False):
    os.makedirs(DATA, exist_ok=True)
    cache = os.path.join(DATA, "polls.json")
    if not force and os.path.exists(cache):
        age_h = (datetime.now().timestamp() - os.path.getmtime(cache)) / 3600
        if age_h < 12:
            return json.load(open(cache, encoding="utf-8"))
    req = urllib.request.Request(SRC, headers={"User-Agent": "poc-agregateur-2027"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8")
    json.loads(raw)  # validation
    open(cache, "w", encoding="utf-8").write(raw)
    return json.loads(raw)


MARKETS_API = "https://gamma-api.polymarket.com/events"
MARKETS_SLUGS = {
    "vainqueur": "next-french-presidential-election",
    "second_tour": None,   # renseigné par recherche de titre
}


def fetch_markets(force=False):
    """Marchés de prédiction Polymarket : probabilités (≠ intentions de vote).
    Toute erreur renvoie None : la page doit se générer même sans les marchés."""
    cache = os.path.join(DATA, "markets.json")
    if not force and os.path.exists(cache):
        age_h = (datetime.now().timestamp() - os.path.getmtime(cache)) / 3600
        if age_h < 6:
            try:
                return json.load(open(cache, encoding="utf-8"))
            except Exception:
                pass
    try:
        out = {"fetched": datetime.now().strftime("%Y-%m-%d %H:%M"), "series": {}}
        for url in (f"{MARKETS_API}?closed=false&limit=100&order=volume24hr&ascending=false",
                    f"{MARKETS_API}?closed=false&limit=20&tag_slug=france"):
            evs = _get_json(url)
            for e in evs:
                title = (e.get("title") or "").lower()
                key = None
                if "next french presidential election" == title:
                    key = "vainqueur"
                elif "advance to the 2nd round" in title:
                    key = "second_tour"
                elif "who will be on the ballot" in title:
                    key = "bulletin"
                if not key or key in out["series"]:
                    continue
                rows = []
                for m in e.get("markets") or []:
                    name = m.get("groupItemTitle") or ""
                    try:
                        prices = json.loads(m.get("outcomePrices") or "[]")
                    except Exception:
                        prices = []
                    if name and prices:
                        rows.append(dict(candidat=name, proba=round(float(prices[0]) * 100, 1),
                                         volume=int(float(m.get("volume") or 0))))
                rows.sort(key=lambda r: -r["proba"])
                if rows:
                    out["series"][key] = dict(titre=e.get("title"), fin=str(e.get("endDate"))[:10],
                                              volume24h=e.get("volume24h"), rows=rows[:10])
        if not out["series"]:
            return None
        json.dump(out, open(cache, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return out
    except Exception:
        return None


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "poc-agregateur-2027"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


FORECAST_URL = ("https://raw.githubusercontent.com/whyalwaysrose/presidentielle-2027/"
                "main/site/data/forecast.json")


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
            candidat=r["candidat"], nous=fr1u(r["intentions"]), nous_tous=fr1u(allx.get(r["candidat"])),
            q50=(None if sh.get("q50") is None else round(sh["q50"] * 100, 1)),
            q05=(None if sh.get("q05") is None else round(sh["q05"] * 100, 1)),
            q95=(None if sh.get("q95") is None else round(sh["q95"] * 100, 1)),
            p_qualify=(None if not c else round((c.get("p_qualify") or 0) * 100, 1)),
            p_win=(None if not c else round((c.get("p_win") or 0) * 100, 1)),
        ))
    return out


def compare_table(agg, trends, fc):
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
    head = ('<tr><th>Candidat</th>'
            '<th class="num">Nous<br><span class="muted small">scénario ' + str(agg["scenario"]) +
            '</span></th>'
            '<th class="num">Nous<br><span class="muted small">toutes listes</span></th>'
            '<th class="num">Eux<br><span class="muted small">médiane 1<sup>er</sup> tour</span></th>'
            '<th class="num">Eux<br><span class="muted small">90 % (5–95)</span></th>'
            '<th class="num">Eux<br><span class="muted small">P(2<sup>e</sup> tour)</span></th>'
            '<th class="num">Eux<br><span class="muted small">P(victoire)</span></th></tr>')
    return ('<table style="margin-top:10px">' + head + body + '</table>')


def compare_duels(fc):
    duels = sorted((fc or {}).get("duels") or [], key=lambda z: -(z.get("p_matchup") or 0))[:5]
    if not duels:
        return ""
    body = "\n".join(
        f'<tr><td>{x.get("nom_a")} <span class="muted small">vs</span> {x.get("nom_b")}</td>'
        f'<td class="num muted">{fr1u((x.get("p_matchup") or 0) * 100)} %</td>'
        f'<td class="num"><strong>{fr1u((x.get("p_a_wins") or 0) * 100)} %</strong> '
        f'<span class="muted small">pour {x.get("nom_a")}</span></td></tr>'
        for x in duels)
    return ('<h3 style="margin-top:24px">Leurs duels les plus probables</h3>'
            '<table style="margin-top:8px"><tr><th>Affiche</th>'
            '<th class="num">Probabilité du duel</th><th class="num">Issue</th></tr>'
            + body + '</table>')


def forecast_block(agg, trends, fc):
    """Comparaison honnête : moyenne maison (scénario verrouillé) vs prévision bayésienne."""
    if not fc or not fc.get("candidats"):
        return ('<p class="small muted">Prévision bayésienne indisponible à cette génération '
                '(source externe) — la page reste complète par ailleurs.</p>')
    d = fc.get("diagnostics") or {}
    s = fc.get("sondages") or {}
    rf = d.get("runoff_fit") or {}
    intro = ('<p class="small muted">Deux colonnes de gauche : nos <strong>intentions de vote</strong> '
             'mesurées (moyenne pondérée). Quatre colonnes de droite : leurs <strong>probabilités</strong> '
             'issues de 80 000 simulations d\'un modèle bayésien. Les niveaux se comparent avec prudence '
             '(deux objets différents) ; l\'incertitude, elle, se compare directement — et elle est '
             'édifiante.</p>')
    chiffres = (f'<h3 style="margin-top:24px">Leur modèle, en chiffres</h3><ul class="tight small">'
                f'<li><strong>{s.get("surveys", "?")} enquêtes</strong> et '
                f'<strong>{s.get("hypotheses", "?")} hypothèses</strong> de candidatures dépouillées '
                f'({s.get("hypotheses_tour1", "?")} de premier tour, '
                f'{s.get("hypotheses_tour2", "?")} de second), {len(s.get("instituts") or [])} instituts, '
                f'du {s.get("date_min")} au {s.get("date_max")} — quand notre scénario verrouillé ne '
                f'retient que {agg["polls_aggregated"]} enquêtes.</li>'
                f'<li><strong>Échantillon effectif</strong> : {frnum(s.get("effective_sample_tour1", 0))} '
                f'sur {frnum(s.get("raw_sample_tour1", 0))} bruts, après pondération.</li>'
                f'<li><strong>{frnum(fc.get("n_simulations", 0))} simulations</strong> ; convergence '
                f'publiée : R̂ max {d.get("max_rhat", "?")}, ESS min {frnum(d.get("min_ess_bulk", 0))}.</li>'
                f'<li><strong>Validation</strong> : rétro-test 2022 sur les duels, erreur absolue moyenne '
                f'{fr1u(rf.get("mae_points"))} point(s), biais {fr1u(rf.get("bias_points"))} ; '
                f'{d.get("n_transferts_2022", "?")} reports de voix de 2022 modélisés.</li>'
                f'<li><strong>Mise à jour quotidienne</strong> par GitHub Action ; sortie arrêtée au '
                f'{fc.get("as_of")} (calcul du {str(fc.get("generated_at"))[:16]}), site bilingue '
                f'<a href="https://whyalwaysrose.github.io/presidentielle-2027/">'
                f'whyalwaysrose.github.io</a>.</li></ul>')
    lecture = ('<h3 style="margin-top:24px">Ce qu\'on lit dans l\'écart</h3><ul class="tight small">'
               '<li><strong>Accord sur les têtes d\'affiche.</strong> Marine Le Pen 34,0 % chez nous '
               'contre <strong>33,8 %</strong> chez eux ; Jean-Luc Mélenchon 15,4 % contre '
               '<strong>15,7 %</strong>. Modèles opposés, même source, même verdict sur les deux premiers.</li>'
               '<li><strong>Écart croissant au centre du tableau.</strong> Édouard Philippe 14,4 % chez '
               'nous (scénario verrouillé) contre <strong>16,1 %</strong> chez eux ; Bruno Retailleau '
               '6,7 % contre <strong>8,3 %</strong>. Notre lecture « toutes listes » s\'en rapproche : '
               'verrouiller un scénario <em>sous-estime</em> les candidats dont le score dépend de la '
               'liste testée.</li>'
               '<li><strong>Nos intervalles ne sont pas des intervalles de prévision.</strong> ±1 point '
               'autour d\'une moyenne, contre un 90 % de <strong>19,7 à 52,4 %</strong> chez eux sur '
               'Marine Le Pen. Cette largeur contient l\'incertitude sur le champ de candidats, les '
               'erreurs d\'enquête et la campagne à venir : à lire avant de citer nos chiffres.</li>'
               '<li><strong>Ils répondent à « qui gagne »</strong> — P(second tour), P(victoire), duels — '
               'ce que ce POC ne sait pas faire et ne prétend pas faire.</li>'
               '<li><strong>Ils se valident, nous non.</strong> Rétro-test 2022, convergence MCMC, qualité '
               'des instituts ajustée : trois contrôles qui nous manquent. Piste évidente : rejouer notre '
               'méthode sur 2022 pour mesurer son erreur au lieu de l\'affirmer.</li>'
               '<li><strong>Même source de données</strong> : la comparaison éclaire deux '
               '<em>modèles</em>, elle ne confirme pas les chiffres. Deux méthodes nourries du même flux '
               'ne sont pas deux vérifications indépendantes.</li></ul>')
    garde = ('<p class="small muted">Ce que ce POC garde : lisibilité totale (aucune dépendance, '
             'aucun modèle latent à croire sur parole), chiffre explicite d\'un scénario donné, aucune '
             'donnée non licite. Ce qu\'il doit emprunter : la validation par rétro-test.</p>')
    return intro + compare_table(agg, trends, fc) + chiffres + compare_duels(fc) + lecture + garde


def markets_block(mk):
    """Panneau marchés : probabilités, présentées SÉPARÉMENT des intentions de vote."""
    if not mk or not mk.get("series"):
        return ('<p class="small muted">Marchés indisponibles à cette génération '
                '(source externe) — les sondages ci-dessus ne sont pas affectés.</p>')
    labels = {"vainqueur": "Probabilité de victoire (qui sera président)",
              "second_tour": "Probabilité d'être au second tour",
              "bulletin": "Probabilité d'être candidat au premier tour"}
    parts = []
    for key in ("vainqueur", "second_tour", "bulletin"):
        s = mk["series"].get(key)
        if not s:
            continue
        rows = "\n".join(
            f'<tr><td>{r["candidat"]}</td><td class="num"><strong>{fr1u(r["proba"])} %</strong></td>'
            f'<td class="num muted small">{frnum(r["volume"])}</td></tr>'
            for r in s["rows"][:8])
        parts.append(
            f'<h3 style="margin-top:20px">{labels[key]}</h3>'
            f'<table style="margin-top:8px"><tr><th>Candidat</th><th class="num">Marché</th>'
            f'<th class="num">Volume ($)</th></tr>{rows}</table>')
    return ("\n".join(parts)
            + f'<p class="small muted" style="margin-top:10px">Relevé le {mk["fetched"]} (heure de '
            f'Paris) sur Polymarket, marchés publics à clôture 2027.</p>')


def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def signature(poll):
    return tuple(sorted(c["candidat"] for c in poll.get("candidats", [])))


def aggregate(polls, as_of=None, scenario_sign=None, scenario_label=None):
    """Agrégation. `as_of` = date de référence (rétro-calcul pour la série hebdomadaire) ;
    `scenario_sign` = verrouille le scénario (comparabilité des séries)."""
    ref = as_of or TODAY
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

    # 2. Scénario de référence : le plus testé récemment (fenêtre courte),
    #    pour ne pas moyenner des configurations de candidatures différentes.
    if scenario_sign is not None:
        scen_sign = tuple(scenario_sign)
        scen_recent = [(p, age, d) for (p, age, d) in r1
                       if signature(p) == scen_sign and age <= SCENARIO_WINDOW]
        scenario = scenario_label or (scen_recent[0][0].get("hypothese") if scen_recent else "—")
    else:
        recent = defaultdict(list)
        for item in r1:
            if item[1] <= SCENARIO_WINDOW:
                recent[signature(item[0])].append(item)
        if not recent:
            recent = defaultdict(list)
            for item in r1:
                recent[signature(item[0])].append(item)
        scen_sign, scen_recent = max(recent.items(),
                                     key=lambda kv: (len(kv[1]), max(-x[1] for x in kv[1])))
        scenario = scen_recent[0][0]["hypothese"]

    # 3. Agrégation : tous les sondages de ce scénario dans la fenêtre longue,
    #    pondérés par la fraîcheur (demi-vie) et la taille d'échantillon.
    scen_polls = [(p, age, d) for (p, age, d) in r1 if signature(p) == scen_sign and age <= AGG_WINDOW]
    if not scen_polls:
        return None
    acc = defaultdict(list)
    for poll, age, d in scen_polls:
        w = math.exp(-math.log(2) * age / HALF_LIFE) * math.sqrt((poll.get("echantillon") or 1000) / 1000.0)
        for c in poll.get("candidats", []):
            if isinstance(c.get("intentions"), (int, float)):
                acc[c["candidat"]].append((w, float(c["intentions"]), poll.get("institut"), d, c.get("parti")))

    rows = []
    for name, vals in acc.items():
        if len(vals) < MIN_POLLS:
            continue
        sw = sum(v[0] for v in vals)
        mean = sum(w * x for w, x, *_ in vals) / sw
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
        polls_in_window=len([1 for _, age, _ in r1 if age <= SCENARIO_WINDOW]),
        scenario=scenario,
        scenario_sign=sorted(scen_sign),
        scenario_size=len(scen_sign),
        polls_in_scenario=len(scen_recent),
        polls_aggregated=len(scen_polls),
        window=SCENARIO_WINDOW, agg_window=AGG_WINDOW, half_life=HALF_LIFE,
        min_polls=MIN_POLLS, ic_floor=IC_FLOOR,
        first=f"{min(d for _, _, d in scen_polls)}",
        last=f"{max(d for _, _, d in scen_polls)}",
        instituts=inst,
        total_intentions=round(sum(r["intentions"] for r in rows), 1),
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
--red:#d73d2f;--green:#166b4e;--amber:#b66d12;--blue:#245d8c}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#f8f4ea 0%,var(--bg) 100%);color:var(--ink);
font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.55}
a{color:var(--red)}
.wrap{width:min(1080px,calc(100% - 40px));margin:0 auto}
.topbar{border-bottom:1px solid var(--line);background:rgba(248,244,234,.86);position:sticky;top:0;z-index:10}
.nav{min-height:62px;display:flex;align-items:center;justify-content:space-between;gap:18px}
.brand{font-weight:850;letter-spacing:-.04em}
.brand span{color:var(--red)}
.navlinks{display:flex;gap:20px;font-size:.88rem;color:var(--muted);flex-wrap:wrap}
.navlinks a{text-decoration:none;color:inherit}
header{padding:56px 0 24px}
.eyebrow{display:inline-block;font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;
color:var(--red);border:1px solid var(--red);border-radius:999px;padding:4px 12px}
h1{font-size:clamp(1.7rem,4vw,2.6rem);line-height:1.12;letter-spacing:-.03em;margin:18px 0 10px}
.lede{font-size:1.02rem;color:var(--muted);max-width:70ch}
.card{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:26px;
box-shadow:0 18px 50px rgba(45,39,28,.07);margin:22px 0}
.grid{display:grid;gap:18px}
@media(min-width:820px){.grid.cols{grid-template-columns:1.15fr .85fr}}
.kpi{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.kpi .big{font-size:clamp(2.6rem,7vw,4rem);font-weight:850;letter-spacing:-.05em;line-height:1}
.kpi .unit{font-size:1.3rem;font-weight:700;color:var(--muted)}
.pill{display:inline-block;font-size:.74rem;padding:3px 10px;border-radius:999px;border:1px solid var(--line);
color:var(--muted);background:#fff}
.pill.g{color:var(--green);border-color:#bfd8cb}
.pill.a{color:var(--amber);border-color:#e6d3ad}
.pill.b{color:var(--blue);border-color:#c3d5e6}
h2{font-size:1.3rem;letter-spacing:-.02em;margin:0 0 12px}
h3{font-size:1rem;margin:20px 0 8px}
.bar{position:relative;height:26px;border-radius:6px;background:#efe9dc;overflow:hidden;display:flex;align-items:center}
.bar i{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,var(--red),#e2695c)}
.bar span{position:relative;padding-left:10px;font-size:.82rem;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:middle}
th{font-size:.76rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.muted{color:var(--muted)}
.small{font-size:.85rem}
.excl{border-left:3px solid var(--amber);background:#fff9ec;padding:12px 14px;border-radius:0 10px 10px 0}
footer{padding:34px 0 60px;color:var(--muted);font-size:.84rem}
code{background:#efe9dc;padding:1px 5px;border-radius:5px;font-size:.86em}
/* --- landing --- */
.hero{padding:64px 0 26px}
.hero h1{font-size:clamp(2rem,5vw,3.4rem);max-width:22ch}
.hero p.lede{font-size:1.12rem;max-width:64ch}
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
.ok{color:var(--green)}.ko{color:var(--red)}
.up{font-weight:700}.down{font-weight:700}
ul.tight{margin:8px 0 0;padding-left:18px;font-size:.92rem}
ul.tight li{margin:5px 0}
.steps{counter-reset:s;margin:10px 0 0;padding:0;list-style:none}
.steps li{counter-increment:s;position:relative;padding:0 0 14px 44px;font-size:.94rem}
.steps li::before{content:counter(s);position:absolute;left:0;top:-2px;width:30px;height:30px;
border-radius:50%;background:#1d1c17;color:#fff;font-weight:800;display:flex;align-items:center;
justify-content:center;font-size:.9rem}
.roadmap{margin:8px 0 0;padding-left:18px;font-size:.92rem;color:var(--muted)}
footer{border-top:1px solid var(--line)}
"""


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


def mov_table(movs):
    """Tableau par candidat : aujourd'hui, il y a 7 jours, il y a 28 jours, tendance."""
    if not movs:
        return '<p class="small muted">Série indisponible (pas assez de sondages publiés).</p>'
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
    return ('<table style="margin-top:10px"><tr><th>Candidat</th>'
            '<th class="num">Aujourd\'hui</th><th class="num">Il y a 7 j</th><th class="num">Δ 7 j</th>'
            '<th class="num">Il y a 28 j</th><th class="num">Δ 28 j</th>'
            '<th class="num">8 sem. (min–max)</th><th>8 semaines</th></tr>'
            + body + '</table>')


def mov_line(movs):
    def pick(field):
        return sorted([m for m in movs if isinstance(m[field], (int, float)) and abs(m[field]) >= 1.0],
                      key=lambda m: -abs(m[field]))

    def fmt(m, field):
        d = m[field]
        return f'{m["candidat"]} {"+" if d > 0 else "−"}{fr1u(abs(d))} pt'

    big7 = pick("delta7")
    if big7:
        return " · ".join(fmt(m, "delta7") for m in big7[:4]) + " (sur 7 jours)"
    big28 = pick("delta28")
    if big28:
        return ("rien au-delà de 1 point sur 7 jours ; sur 28 jours : "
                + " · ".join(fmt(m, "delta28") for m in big28[:3]))
    return "aucun écart supérieur à 1 point sur 7 ou 28 jours (tous dans la marge)"


def fr(x):
    """Formatage français : virgule décimale, pas de ',0' inutile."""
    s = f"{x:.1f}" if isinstance(x, float) else str(x)
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return s.replace(".", ",")


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


def trend_table(rows):
    if not rows:
        return '<p class="small muted">Indicateur indisponible.</p>'
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
    return ('<table style="margin-top:10px"><tr><th>Candidat</th>'
            '<th class="num">Toutes listes</th><th class="num">Il y a 7 j</th><th class="num">Δ 7 j</th>'
            '<th class="num">Il y a 28 j</th><th class="num">Δ 28 j</th>'
            '<th class="num">Sondages</th><th>8 semaines</th></tr>' + body + '</table>')


def render_sondages(agg, movs=None, trends=None, mk=None, fc=None):
    movs = movs or []
    trends = trends or []
    r0 = agg["rows"][0] if agg["rows"] else None
    rows = agg["rows"]
    watch = []
    if len(rows) >= 3:
        gap = round(rows[1]["intentions"] - rows[2]["intentions"], 1)
        watch.append(f"Écart entre le 2ᵉ et le 3ᵉ : {fr(gap)} point{'s' if gap >= 1.5 else ''}.")
        if rows[2]["haut"] >= rows[1]["bas"]:
            watch.append("Les intervalles du 2ᵉ et du 3ᵉ se recouvrent : l'écart n'est pas significatif au vu des marges.")
    maxv = max((r["intentions"] for r in rows), default=1)
    bars = "\n".join(
        f'<div style="margin:10px 0"><div style="display:flex;justify-content:space-between;font-size:.88rem">'
        f'<strong>{r["candidat"]}</strong><span class="muted">{r["parti"] or ""} — '
        f'{fr(r["intentions"])} % <span class="small">[{fr(r["bas"])}–{fr(r["haut"])}]</span></span></div>'
        f'<div class="bar"><i style="width:{(r["intentions"]/maxv*100):.1f}%"></i>'
        f'<span>{fr(r["intentions"])} %</span></div></div>'
        for r in rows)
    trs = "\n".join(
        f'<tr><td>{r["candidat"]}</td><td class="muted small">{r["parti"] or ""}</td>'
        f'<td class="num"><strong>{fr(r["intentions"])}</strong></td>'
        f'<td class="num muted">{fr(r["bas"])} – {fr(r["haut"])}</td>'
        f'<td class="num muted">{fr(r["mini"])} – {fr(r["maxi"])}</td>'
        f'<td class="num">{r["n"]}</td><td class="num">{fr(r["neff"])}</td>'
        f'<td class="num muted small">{r["dernier"]}</td></tr>'
        for r in rows)

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Présidentielle 2027 — agrégation de sondages (POC sandbox)</title>
<style>{CSS}</style>
</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand"><a href="/simulation/" style="text-decoration:none">Présidentielle 2027</a> <span>· agrégation</span></div>
  <div class="navlinks"><a href="/simulation/">Accueil</a><a href="#tete">Tête de course</a>
  <a href="#tableau">Tableau</a><a href="#evolution">Évolution</a><a href="#marches">Marchés</a>
  <a href="#comparaison">Comparaison</a><a href="#methode">Méthode</a>
  <a href="#limites">Limites</a></div>
</div></div>

<header class="wrap">
  <span class="eyebrow">POC sandbox — non publié</span>
  <h1>Ce que disent les sondages de la présidentielle 2027, agrégés et sourcés</h1>
  <p class="lede">Un seul scénario de candidatures, une moyenne pondérée par la fraîcheur et la
  taille d'échantillon, un intervalle publié, et la liste de toutes les limites. Page régénérée le
  {frdate(agg['generated'])} (heure de Paris).</p>
</header>

<main class="wrap">
<section id="tete" class="grid cols">
  <div class="card">
    <span class="pill b">Tête de course</span>
    {"" if not r0 else f'''
    <div class="kpi" style="margin-top:14px">
      <span class="big">{fr(r0["intentions"])}</span><span class="unit">%</span>
      <span class="muted">— {r0["candidat"]} ({r0["parti"] or "sans étiquette"})</span>
    </div>
    <p class="small muted" style="margin-top:8px">Intervalle à 95 % : <strong>{fr(r0["bas"])} – {fr(r0["haut"])} %</strong>
    · {r0["n"]} sondages · effectif effectif {r0["neff"]}</p>'''}
    <h3>Lecture rapide</h3>
    <ul class="small muted">
      {"".join(f"<li>{w}</li>" for w in watch) or "<li>Pas assez de candidats pour comparer les écarts.</li>"}
      <li>Total des intentions publiées : {fr(agg["total_intentions"])} % (les intentions non publiées
      correspondent aux candidats sous le seuil de {agg["min_polls"]} sondages).</li>
    </ul>
  </div>
  <div class="card">
    <span class="pill a">Périmètre</span>
    <table style="margin-top:12px">
      <tr><th>Sondages dans la source</th><td class="num">{agg["total_polls_all"]}</td></tr>
      <tr><th>1<sup>er</sup> tour, {agg["window"]} derniers jours</th><td class="num">{agg["polls_in_window"]}</td></tr>
      <tr><th>Scénario retenu</th><td class="num">{agg["scenario"]} ({agg["scenario_size"]} candidats)</td></tr>
      <tr><th>Sondages du scénario, {agg["window"]} j</th><td class="num">{agg["polls_in_scenario"]}</td></tr>
      <tr><th>Sondages agrégés, {agg["agg_window"]} j</th><td class="num">{agg["polls_aggregated"]}</td></tr>
      <tr><th>Période couverte</th><td class="num">{agg["first"]} → {agg["last"]}</td></tr>
      <tr><th>Instituts</th><td class="num small">{", ".join(agg["instituts"])}</td></tr>
    </table>
  </div>
</section>

<section id="tableau" class="card">
  <h2>Moyennes pondérées</h2>
  <p class="small muted">Les barres sont proportionnelles à la moyenne. <strong>IC 95 %</strong> :
  incertitude statistique de la moyenne. <strong>Amplitude</strong> : minimum et maximum observés
  parmi les sondages agrégés — c'est la dispersion réelle entre instituts, souvent plus parlante
  que l'intervalle.</p>
  {bars}
  <table style="margin-top:18px">
    <tr><th>Candidat</th><th>Parti</th><th class="num">Moyenne</th><th class="num">IC 95 %</th>
    <th class="num">Amplitude</th><th class="num">Sondages</th><th class="num">n effectif</th>
    <th class="num">Dernier</th></tr>
    {trs}
  </table>
</section>

<section id="evolution" class="card">
  <h2>Évolution, semaine par semaine</h2>
  <p class="small muted">Série <strong>rétro-calculée</strong> : la méthode actuelle appliquée aux
  sondages publiés à chaque échéance hebdomadaire — c'est ce que cette page aurait affiché, pas ce
  qu'elle affichait. Le scénario est verrouillé sur {agg["scenario"]} pour que les lignes restent
  comparables. Un écart inférieur à 1 point reste dans la marge : nous ne le commentons pas.</p>
  {mov_table(movs)}
  <p class="small" style="margin-top:14px"><strong>Mouvements sur 7 jours :</strong> {mov_line(movs)}.</p>
  <h3 style="margin-top:26px">Tendance, toutes listes confondues</h3>
  <p class="small muted">Ici, chaque sondage du premier tour compte, quelle que soit la liste testée :
  c'est un <strong>indicateur de direction</strong>. Les niveaux ne sont pas comparables à ceux du
  tableau ci-dessus (une liste de dix candidats ne suit pas la même arithmétique qu'une liste de
  quinze) — seule l'évolution compte, et elle est plus robuste car elle repose sur beaucoup plus
  d'enquêtes.</p>
  {trend_table(trends)}
  <p class="small" style="margin-top:14px"><strong>Mouvement de fond (toutes listes) :</strong>
  {mov_line(trends)}.</p>
  <p class="small muted">Sondages agrégés par point, de J−56 à J−0 :
  {" · ".join(str(p["polls"]) for p in agg.get("series", []))}. Un tiret signale un candidat absent
  du scénario à cette date ; la courbe relie les points disponibles. Les premières semaines reposent
  sur très peu de sondages : un plateau à trois enquêtes ne démontre rien.</p>
</section>

<section id="comparaison" class="card">
  <h2>Comparaison : notre agrégation face à une prévision bayésienne</h2>
  <p class="small">Un projet indépendant, <a
  href="https://github.com/whyalwaysrose/presidentielle-2027">whyalwaysrose/presidentielle-2027</a>
  (licence MIT), publie une prévision bayésienne hiérarchique de la même élection, nourrie de la
  <strong>même source de sondages</strong>, avec le choix inverse du nôtre : il <em>intègre</em>
  l'incertitude sur la liste des candidats au lieu de verrouiller un scénario. Voici les deux côte à
  côte, et ce que l'écart nous apprend.</p>
  {forecast_block(agg, trends, fc)}
</section>

<section id="methode" class="card">
  <h2>Méthode</h2>
  <p class="small">Chaque sondage reçoit un poids :
  <code>w = exp(−ln2 × âge / demi-vie) × √(échantillon / 1000)</code>, avec une demi-vie de
  {agg["half_life"]} jours. La moyenne publiée est la moyenne pondérée ; l'intervalle à 95 %
  vaut <code>1,96 × σ<sub>pondéré</sub> / √n<sub>eff</sub></code>, avec
  <code>n_eff = (Σw)² / Σw²</code> — et il est plancheré à ±{fr(agg["ic_floor"])} point, parce qu'un
  intervalle calculé sur peu de sondages donnerait une fausse précision.</p>
  <p class="small"><strong>Deux fenêtres, pour une raison.</strong> Le <em>scénario</em> est choisi
  sur les {agg["window"]} derniers jours (le plus testé récemment) : c'est lui qui doit être à jour,
  puisque les listes de candidats bougent. Les <em>moyennes</em> sont ensuite calculées sur tous les
  sondages de ce même scénario dans les {agg["agg_window"]} derniers jours
  ({agg["polls_aggregated"]} sondages), pondérés par la fraîcheur. Mélanger les scénarios produirait
  des chiffres faux ; n'utiliser que {agg["window"]} jours produirait des moyennes trop instables.</p>
  <p class="small">Données : <a href="https://github.com/MieuxVoter/presidentielle2027">MieuxVoter/presidentielle2027</a>
  (licence MIT), flux JSON brut, 1<sup>er</sup> tour uniquement. Le document est régénéré par un
  script, sans retouche manuelle des chiffres ; le code du générateur est publié avec la page dans
  le dépôt du POC.</p>
</section>

<section id="marches" class="card">
  <h2>Ce que disent les marchés — et pourquoi ce n'est pas comparable</h2>
  <div class="excl small" style="margin-bottom:14px">
    <strong>Deux objets différents.</strong> Un sondage mesure une <em>intention de vote</em> à une
    date donnée, sur un échantillon interrogé. Un marché de prédiction affiche une
    <em>probabilité</em> implicite, pondérée par l'argent engagé, sur un autre horizon et avec
    d'autres acteurs. Un « 35 % » de marché n'est pas un « 35 % » de sondage : ne les additionnez
    jamais, ne les mettez jamais dans la même moyenne. Ce panneau est un <strong>contrepoint</strong>,
    pas une deuxième source de voix.
  </div>
  {markets_block(mk)}
  <p class="small muted">Les marchés de prédiction ne relèvent pas de la loi du 19 juillet 1977 sur la
  publication des sondages, mais leur publication en France (opérateur non agréé, incitation à
  parier) doit être vérifiée avant toute sortie du sandbox.</p>
</section>

<section id="limites" class="card">
  <h2>Limites (à lire avant de citer un chiffre)</h2>
  <div class="excl small">
    <p style="margin:0 0 8px"><strong>Ce POC n'est pas un modèle de prévision.</strong> Il n'anticipe
    ni la participation, ni les reports de voix, ni les dynamiques de campagne, et ne calcule aucune
    probabilité de victoire.</p>
    <ul style="margin:0">
      <li><strong>Effets de maison non corrigés</strong> : chaque institut a sa propre tendance ; un
      agrégateur professionnel la corrige (et publie comment). Ici, non.</li>
      <li><strong>Marges des instituts ignorées</strong> : l'IC affiché est celui de la moyenne
      (plancheré à ±{fr(agg["ic_floor"])} point), plus étroit que la marge d'un sondage isolé. La colonne
      « amplitude » montre, elle, l'écart réel entre instituts.</li>
      <li><strong>Peu de sondages par scénario</strong> : {agg["polls_aggregated"]} sondages
      seulement entrent dans le calcul — les listes de candidats sont encore instables à ce stade.</li>
      <li><strong>Scénarios écartés</strong> : les sondages testant d'autres listes de candidats ne
      sont pas comptés.</li>
      <li><strong>Candidatures mouvantes</strong> : annonces, retraits et ralliements rendent toute
      liste instable à {agg["window"]} jours de l'élection.</li>
      <li><strong>Ne pas confondre</strong> : une moyenne de sondages n'est pas un résultat, et une
      intention de vote n'est pas un vote.</li>
    </ul>
  </div>
</section>
</main>

<footer class="wrap">
  <p>POC sandbox — non publié, non indexé (page de démonstration méthodologique).
  Source des données : <a href="https://github.com/MieuxVoter/presidentielle2027">MieuxVoter/presidentielle2027</a>,
  licence MIT. Génére le {frdate(agg["generated"])}.</p>
</footer>
</body>
</html>
"""


def frdate(s):
    """'2026-09-14 15:29' -> '14/09/2026 à 15:29' (date de génération, lecture française)."""
    try:
        d, h = s.split(" ")
        y, m, j = d.split("-")
        return f"{j}/{m}/{y} à {h}"
    except Exception:
        return s


def render_landing(agg, movs=None, trends=None, mk=None, fc=None):
    movs = movs or []
    trends = trends or []
    r0 = agg["rows"][0] if agg["rows"] else None
    n_cand = len(agg["rows"])
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="description" content="Observatoire des sondages de la présidentielle 2027 : agrégation sourcée, méthode publiée, limites affichées.">
<title>Présidentielle 2027 — observatoire des sondages (prototype)</title>
<style>{CSS}</style>
</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand">Présidentielle 2027 <span>· observatoire</span></div>
  <div class="navlinks"><a href="/simulation/sondages/">Agrégation</a><a href="#evolution">Évolution</a>
  <a href="#marches">Marchés</a><a href="#comparaison">Comparaison</a>
  <a href="#methode">Méthode</a><a href="#donnees">Données</a><a href="#limites">Limites</a></div>
</div></div>

<header class="wrap hero">
  <span class="eyebrow">Prototype sandbox — non publié, non indexé</span>
  <h1>Les sondages de la présidentielle 2027, agrégés sans boule de cristal</h1>
  <p class="lede">Nous compilons les sondages publiés par les instituts, <strong>un scénario de
  candidatures à la fois</strong>, avec la méthode écrite noir sur blanc et les limites affichées à
  côté des chiffres. Pas de probabilité de victoire : une lecture sourcée, datée, discutable.</p>
  <div class="cta">
    <a class="btn" href="/simulation/sondages/">Voir l'agrégation du jour</a>
    <a class="btn2" href="#methode">Comment c'est calculé</a>
  </div>

  <div class="statgrid">
    <div class="stat"><span>Favori du scénario retenu</span>
      <b>{"" if not r0 else fr(r0["intentions"]) + " %"}</b>
      <span>{"" if not r0 else r0["candidat"]}</span></div>
    <div class="stat"><span>Sondages agrégés</span><b>{agg["polls_aggregated"]}</b>
      <span>sur {agg["agg_window"]} jours</span></div>
    <div class="stat"><span>Instituts couverts</span><b>{len(agg["instituts"])}</b>
      <span>{", ".join(agg["instituts"][:3])}</span></div>
    <div class="stat"><span>Dernière enquête</span><b>{agg["last"][8:10]}.{agg["last"][5:7]}</b>
      <span>période : {agg["first"][8:10]}.{agg["first"][5:7]} → {agg["last"][8:10]}.{agg["last"][5:7]}</span></div>
  </div>
  <p class="small muted" style="margin-top:14px">Scénario retenu : {agg["scenario"]}
  ({agg["scenario_size"]} candidats) · {n_cand} candidats publiés · source : {agg["total_polls_all"]}
  sondages compilés, dont {agg["polls_in_window"]} sur les {agg["window"]} derniers jours.
  Page régénérée le {frdate(agg["generated"])}.</p>
</header>

<main class="wrap">
<section id="evolution" class="card">
  <h2>Évolution, semaine par semaine</h2>
  <p class="small muted">Série <strong>rétro-calculée</strong> par la méthode actuelle, sur les sondages
  publiés à chaque échéance hebdomadaire (ce que la page aurait affiché, pas ce qu'elle affichait).
  Un écart inférieur à 1 point reste dans la marge et n'est pas commenté.</p>
  {mov_table(movs)}
  <p class="small" style="margin-top:14px"><strong>Mouvements sur 7 jours (scénario retenu) :</strong>
  {mov_line(movs)}.</p>
  <h3 style="margin-top:24px">Tendance, toutes listes confondues</h3>
  <p class="small muted">Indicateur de direction : chaque sondage du premier tour compte, quelle que
  soit la liste testée. Les niveaux ne sont pas comparables à ceux du tableau ci-dessus ; seule
  l'évolution compte, et elle est plus robuste (beaucoup plus d'enquêtes).
  <a href="/simulation/sondages/#evolution">Méthode et détail</a>.</p>
  {trend_table(trends)}
  <p class="small" style="margin-top:14px"><strong>Mouvement de fond :</strong> {mov_line(trends)}.</p>
</section>

<section class="card">
  <h2>Trois principes</h2>
  <div class="cards">
    <div class="card2"><h3>Une source unique, citée</h3>
      <p>Les données viennent d'une seule compilation publique et vérifiable —
      <a href="https://github.com/MieuxVoter/presidentielle2027">MieuxVoter/presidentielle2027</a>,
      licence MIT — jamais d'un chiffre repris de seconde main sans origine.</p></div>
    <div class="card2"><h3>Un scénario à la fois</h3>
      <p>Un sondage ne vaut que pour la liste de candidats qu'il teste. Nous retenons le scénario le
      plus testé récemment et nous ignorons les autres, plutôt que de moyenner des configurations
      différentes et de produire un chiffre qui n'existe nulle part.</p></div>
    <div class="card2"><h3>Les limites avec les chiffres</h3>
      <p>Intervalle, amplitude observée, instituts, nombre de sondages, et la liste de ce que la
      méthode ne fait pas : tout est publié sur la même page que les résultats.</p></div>
  </div>
</section>

<section class="card">
  <h2>Ce que ça fait — ce que ça ne fait pas</h2>
  <div class="two">
    <div class="card2">
      <h3 class="ok">Ce que ça fait</h3>
      <ul class="tight">
        <li>Une moyenne pondérée par la fraîcheur de l'enquête et la taille de l'échantillon.</li>
        <li>Un intervalle de confiance explicite sur la moyenne, et l'amplitude réelle entre instituts.</li>
        <li>Le détail par candidat : parti, nombre de sondages, dernière enquête prise en compte.</li>
        <li>Une page méthode et un générateur publiés — les chiffres ne sont jamais saisis à la main.</li>
      </ul>
    </div>
    <div class="card2">
      <h3 class="ko">Ce que ça ne fait pas</h3>
      <ul class="tight">
        <li>Aucune probabilité de victoire, aucun modèle de second tour.</li>
        <li>Aucune correction des effets de maison (chaque institut garde sa tendance).</li>
        <li>Aucune anticipation de la participation, des reports de voix ou d'un fait de campagne.</li>
        <li>Aucune reprise de sondages testant d'autres listes de candidats.</li>
      </ul>
    </div>
  </div>
</section>

<section id="methode" class="card">
  <h2>La méthode, en clair</h2>
  <ol class="steps">
    <li><strong>Collecte.</strong> Nous lisons le flux public de la compilation MieuxVoter
    (CSV et JSON), premier tour uniquement.</li>
    <li><strong>Choix du scénario.</strong> Le scénario retenu est celui qui compte le plus de
    sondages sur les {agg["window"]} derniers jours — les listes de candidats bougent encore.</li>
    <li><strong>Pondération.</strong> Chaque sondage pèse selon son âge (demi-vie de
    {agg["half_life"]} jours) et la racine de son échantillon.</li>
    <li><strong>Incertitude.</strong> L'intervalle à 95 % de la moyenne est plancheré à
    ±{fr(agg["ic_floor"])} point, pour ne pas fabriquer de fausse précision sur peu de sondages.</li>
    <li><strong>Publication.</strong> Un candidat n'apparaît qu'à partir de {agg["min_polls"]} sondages.</li>
  </ol>
  <div class="excl small" style="margin-top:14px">
    <code>poids w = exp(−ln2 × âge_jours / {agg["half_life"]}) × √(échantillon / 1000)</code><br>
    <code>moyenne = Σ(w·x) / Σw</code> &nbsp;·&nbsp;
    <code>IC 95 % = max( 1,96 × σ_pondéré / √n_eff , {fr(agg["ic_floor"])} )</code> avec
    <code>n_eff = (Σw)² / Σw²</code>
  </div>
  <p class="small muted" style="margin-top:12px">Le détail des calculs, les valeurs par candidat et
  les limites complètes sont sur la page <a href="/simulation/sondages/">Agrégation</a>.</p>
</section>

<section id="donnees" class="card">
  <h2>Les données</h2>
  <div class="cards">
    <div class="card2"><h3>Source</h3><p><a href="https://github.com/MieuxVoter/presidentielle2027">MieuxVoter/presidentielle2027</a>
      — compilation ouverte des sondages de la présidentielle 2027 (CSV + JSON), licence MIT.
      L'attribution est obligatoire et figure sur chaque page.</p></div>
    <div class="card2"><h3>Fraîcheur</h3><p>{agg["total_polls_all"]} sondages compilés à ce jour,
      {agg["polls_in_window"]} sur les {agg["window"]} derniers jours. La page est régénérée par
      script ; les données sont mises en cache 12 heures maximum.</p></div>
    <div class="card2"><h3>Ce qui reste à faire</h3>
      <ul class="roadmap">
        <li>correction des effets de maison ;</li>
        <li>moyenne glissante publiée jour par jour ;</li>
        <li>confrontation aux marchés de prédiction ;</li>
        <li>méthode détaillée et export CSV/JSON publics.</li>
      </ul></div>
  </div>
</section>

<section id="comparaison" class="card">
  <h2>Comparaison avec une prévision bayésienne</h2>
  <p class="small muted">Un projet MIT indépendant prévoit la même élection à partir des
  <strong>mêmes sondages</strong>, mais en intégrant l'incertitude sur la liste des candidats au lieu
  de verrouiller un scénario. En résumé : accord sur les deux premiers, écart croissant au centre du
  tableau, et des intervalles chez eux beaucoup plus larges — donc plus honnêtes. Analyse complète sur
  la page <a href="/simulation/sondages/#comparaison">Agrégation</a>.</p>
  {forecast_block(agg, trends, fc)}
</section>

<section id="marches" class="card">
  <h2>Les marchés de prédiction, en contrepoint</h2>
  <p class="small muted">Un marché affiche une <strong>probabilité</strong> implicite, un sondage une
  <strong>intention de vote</strong> : deux objets différents, à ne jamais mélanger dans une même
  moyenne. Utile pour voir si le marché suit ou précède les sondages.</p>
  {markets_block(mk)}
</section>

<section id="limites" class="card">
  <h2>À lire avant de citer un chiffre</h2>
  <div class="excl small">
    <p style="margin:0 0 8px"><strong>Ce prototype n'est pas un modèle de prévision.</strong> Il décrit
    ce que disent les sondages publiés, agrémenté d'une incertitude explicite — rien de plus.</p>
    <p style="margin:0">Une moyenne de sondages n'est pas un résultat, une intention de vote n'est pas
    un vote, et ce projet est un travail en cours : la méthode évoluera, et chaque changement sera
    daté.</p>
  </div>
</section>
</main>

<footer class="wrap">
  <p>Prototype sandbox — non publié, non indexé. Données :
  <a href="https://github.com/MieuxVoter/presidentielle2027">MieuxVoter/presidentielle2027</a>
  (licence MIT). Page régénérée le {frdate(agg["generated"])} ; aucune modification manuelle des chiffres.</p>
</footer>
</body>
</html>
"""


def main():
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
    json.dump(dict(generated=agg["generated"], scenario=agg["scenario"],
                   polls_window=agg["polls_in_window"], polls_agg=agg["polls_aggregated"],
                   last=agg["last"], movs=movs, trends=trends),
              open(os.path.join(DATA, "movements.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    mk = fetch_markets(force="--force" in os.sys.argv)
    fc = fetch_forecast(force="--force" in os.sys.argv)
    n_hist = save_history(agg)
    agg["series"] = [dict(date=p["date"], weeks_ago=p["weeks_ago"], polls=p["polls"],
                          rows={k: v["intentions"] for k, v in p["rows"].items()}) for p in series]
    os.makedirs(SITE, exist_ok=True)
    os.makedirs(os.path.join(SITE, "sondages"), exist_ok=True)
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(render_landing(agg, movs, trends, mk, fc))
    open(os.path.join(SITE, "sondages", "index.html"), "w", encoding="utf-8").write(
        render_sondages(agg, movs, trends, mk, fc))
    json.dump(agg, open(os.path.join(DATA, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
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
    print("marchés : " + (", ".join(f"{k} ({len(v['rows'])} candidats)"
                                    for k, v in (mk or {}).get("series", {}).items())
                          or "indisponibles"))
    print(f"série : {len(series)} points hebdo | archive quotidienne : {n_hist} jour(s) "
          f"-> {os.path.join(DATA, 'history.jsonl')}")


if __name__ == "__main__":
    main()
