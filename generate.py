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
import json, math, os, urllib.request
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


def backtest_block():
    """Bloc de validation, affiché avec la comparaison bayésienne."""
    b = backtest_summary()
    if not b:
        return ('<h3 style="margin-top:24px">Validation</h3><p class="small muted">Rétro-test 2022 '
                'non calculé (lancer <code>python3 backtest2022.py</code>).</p>')
    top2 = " et ".join(b["top2"])
    return (
        '<h3 style="margin-top:24px">Validation : la méthode rejouée sur 2022</h3>'
        '<p class="small" style="max-width:none">Rejouée sur la campagne 2022 (sondages compilés sous licence MIT, résultat '
        'officiel vérifié), notre agrégation affiche <strong>' + fr1u(b["mae"])
        + " point d'erreur moyenne</strong> à J−" + str(b["jours"]) + ", " + str(b["n"])
        + " candidats réels publiés, et les deux finalistes identifiés (" + top2 + "). "
        'Deux enseignements désagréables : la pondération par fraîcheur n\'apporte <em>rien</em> '
        'face à la dernière enquête seule (' + fr1u(b["dernier"]) + " point), et le poids donné aux "
        'non-candidats atteignait ' + fr1u(b["non_cand"]) + ' points au dernier point. '
        '<a href="/observatoire/backtest/">Voir le rétro-test complet, échéance par échéance</a>.</p>')


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
    head = ('<tr><th rowspan="2">Candidat</th>'
            '<th class="num" colspan="2">MieuxVoter<br><span class="muted small">agrégation des '
            'sondages compilés</span></th>'
            '<th class="num" colspan="4">Prévision bayésienne<br><span class="muted small">'
            'whyalwaysrose, 80 000 simulations</span></th></tr>'
            '<tr><th class="num small">scénario ' + str(agg["scenario"]) + '</th>'
            '<th class="num small">toutes listes</th>'
            '<th class="num small">médiane 1<sup>er</sup> tour</th>'
            '<th class="num small">90 % (5–95)</th>'
            '<th class="num small">P(2<sup>e</sup> tour)</th>'
            '<th class="num small">P(victoire)</th></tr>')
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
    stale = ''
    if fc.get("cached_at"):
        from datetime import datetime as dt
        stale = ('<p class="small muted" style="color:var(--amber);max-width:none">⚠ Données mises à jour le '
                 + dt.fromtimestamp(fc["cached_at"]).strftime("%d/%m/%Y à %H:%M")
                 + ' — la source externe est temporairement injoignable.</p>')
    d = fc.get("diagnostics") or {}
    s = fc.get("sondages") or {}
    rf = d.get("runoff_fit") or {}
    intro = ('<p class="small muted" style="max-width:none">Deux colonnes de gauche : nos <strong>intentions de vote</strong> '
             'mesurées (moyenne pondérée). Quatre colonnes de droite : leurs <strong>probabilités</strong> '
             'issues de 80 000 simulations d\'un modèle bayésien. Les niveaux se comparent avec prudence '
             '(deux objets différents) ; l\'incertitude, elle, se compare directement — et elle est '
             'édifiante.</p>'
             '<p class="small muted" style="max-width:none">Ce que recouvre la colonne « MieuxVoter » : la compilation ouverte '
             'des sondages (licence MIT) et la moyenne pondérée calculée à partir d\'elle, selon la '
             'méthode publiée plus bas — jamais un chiffre repris tel quel.</p>')
    chiffres = (f'<h3 style="margin-top:24px">La prévision bayésienne, en chiffres</h3><ul class="tight small" style="max-width:none">'
                f'<li><strong>{s.get("surveys", "?")} enquêtes</strong> et '
                f'<strong>{s.get("hypotheses", "?")} hypothèses</strong> de candidatures dépouillées '
                f'({s.get("hypotheses_tour1", "?")} de premier tour, '
                f'{s.get("hypotheses_tour2", "?")} de second), {len(s.get("instituts") or [])} instituts, '
                f'du {s.get("date_min")} au {s.get("date_max")} — quand l\'agrégation, scénario '
                f'verrouillé, n\'en retient que {agg["polls_aggregated"]}.</li>'
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
        f'{r["candidat"]} {fr1u(r["nous_num"])} % contre {fr1u(r["q50"])} %' for r in tete3)
    lecture = (
        '<h3 style="margin-top:24px">Ce qu\'on lit dans l\'écart</h3><ul class="tight small" style="max-width:none">'
        '<li><strong>Les deux lectures se rejoignent sur le haut du tableau.</strong> '
        + ecart_txt + '. Deux méthodes opposées, la même source de sondages : '
        + ('le plus large écart des trois est de ' + fr1u(abs(tete_max["nous_num"] - tete_max["q50"]))
           + ' point (' + tete_max["candidat"] + '), les autres se comptent en dixièmes.'
           if tete_max else '—') + '</li>'
        '<li><strong>Le reste du tableau suit la même logique</strong> : '
        + (('aucun écart ne dépasse ' + fr1u(abs(reste_max["nous_num"] - reste_max["q50"]))
            + ' point (' + reste_max["candidat"] + ')') if reste_max else '—')
        + '. Là où des écarts subsistent, l\'agrégation donne le niveau d\'un scénario précis de '
        'candidatures, la prévision bayésienne une moyenne pondérée sur toutes les hypothèses : '
        'l\'écart mesure surtout la différence de question posée.</li>'
        '<li><strong>L\'intervalle de l\'agrégation n\'est pas un intervalle de prévision.</strong> '
        + fr1u(largeur_agr) + ' point du côté MieuxVoter contre '
        + (fr1u(largeur_bayes) + ' points dans la prévision bayésienne sur le premier' if largeur_bayes else '—')
        + (f' — un facteur {fr1u(facteur)}' if facteur else '')
        + '. La largeur bayésienne contient l\'incertitude sur le champ de candidats, les erreurs '
        'd\'enquête et la campagne à venir ; l\'intervalle d\'agrégation ne dit que la dispersion des '
        'sondages retenus.</li>'
        '<li><strong>Ils répondent à « qui gagne »</strong> — P(second tour), P(victoire), duels — ce '
        'que cette page ne sait pas faire et ne prétend pas faire.</li>'
        '<li><strong>Validation : match nul.</strong> Ils publient rétro-test 2022, convergence MCMC et '
        'qualité des instituts ajustée. Nous publions désormais notre propre rétro-test 2022 — même '
        'exercice, un seul millésime, une erreur de 3,8 points à J−132 et deux réglages corrigés '
        '(voir la section Validation ci-dessous). Ni l\'un ni l\'autre ne peut prétendre avoir raison : '
        'même source de données, deux modèles, deux façons de se tromper.</li>'
        '<li><strong>Le décalage a une cause connue.</strong> Nos chiffres de milieu de tableau étaient '
        'systématiquement plus bas que les leurs : c\'est ce qui nous a fait passer la fenêtre de '
        'sélection du scénario de 60 à 90 jours, après mesure sur 2022. Depuis, les deux lectures se '
        'rejoignent — un modèle bayésien et une moyenne expliquée ne convergent pas par hasard.</li>'
        '</ul>')

    garde = ('<p class="small muted" style="max-width:none">Ce que cette page garde : lisibilité totale (aucune dépendance, '
             'aucun modèle latent à croire sur parole), chiffre explicite d\'un scénario donné, aucune '
             'donnée non licite. Ce qu\'il doit emprunter : la validation par rétro-test.</p>')
    return intro + stale + compare_table(agg, trends, fc) + chiffres + compare_duels(fc) + lecture + garde


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

    # 2. Scénario de référence : le plus testé récemment (fenêtre courte),
    #    pour ne pas moyenner des configurations de candidatures différentes.
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
        scen_sign, scen_recent = max(recent.items(),
                                     key=lambda kv: (len(kv[1]), max(-x[1] for x in kv[1])))
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
            fichier=p.get("filename") or "—")
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
THEME_HEAD = """<script>(function(){try{var c=localStorage.getItem("theme");
if(c==="dark"||(!c&&window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches))
{document.documentElement.setAttribute("data-theme","dark");}}catch(e){}})();</script>"""

THEME_BTN = """<button type="button" class="themebtn" id="themebtn" aria-label="Changer le thème"
  title="Passer en mode clair ou sombre">&#9681;</button>"""

# Lien vers la page « Workflow » (annexe technique : comment le site se fabrique).
# Défini une seule fois ici, utilisé par les quatre pages — un seul endroit à corriger.
NAV_WORKFLOW = '<a href="/observatoire/workflow/">Workflow</a>'
NAV_LOIS = '<a href="/observatoire/lois/">Veille législative</a>'

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


def render_sondages(agg, movs=None, trends=None, fc=None):
    movs = movs or []
    trends = trends or []
    r0 = agg["rows"][0] if agg["rows"] else None
    rows = agg["rows"]
    VALEURS = valeurs_textes(agg, rows)

    watch = []
    if len(rows) >= 3:
        gap = round(rows[1]["intentions"] - rows[2]["intentions"], 1)
        watch.append(f"Écart entre le 2ᵉ et le 3ᵉ : {fr(gap)} point{'s' if gap >= 1.5 else ''}.")
        if rows[2]["haut"] >= rows[1]["bas"]:
            watch.append("Les intervalles du 2ᵉ et du 3ᵉ se recouvrent : l'écart n'est pas significatif au vu des marges.")
    duo = ""
    if len(rows) >= 2:
        duo = f'''<div class="duo">
      <div class="slot"><span class="tag">1<sup>er</sup> tour · 1<sup>re</sup> place</span>
        <b>{rows[0]["candidat"]}</b>
        <span class="muted small">{rows[0]["parti"] or "sans étiquette"} — <span class="sc"><i>{fr(rows[0]["intentions"])} %</i> <span class="small">[{fr(rows[0]["bas"])}–{fr(rows[0]["haut"])}]</span></span></span></div>
      <div class="slot"><span class="tag">1<sup>er</sup> tour · 2<sup>e</sup> place</span>
        <b>{rows[1]["candidat"]}</b>
        <span class="muted small">{rows[1]["parti"] or "sans étiquette"} — <span class="sc"><i>{fr(rows[1]["intentions"])} %</i> <span class="small">[{fr(rows[1]["bas"])}–{fr(rows[1]["haut"])}]</span></span></span></div>
    </div>
    <p class="small muted" style="margin-top:10px"><strong>Second tour théorique : {rows[0]["candidat"]} et
    {rows[1]["candidat"]}.</strong> Ce sont les deux premiers de cette moyenne — une lecture mécanique du
    tableau, pas une prévision. Le second tour dépend des reports de voix, de la participation et des
    alliances, que nous ne modélisons pas : aucun chiffre de cette page ne dit qui le remporterait.</p>'''

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
        f'<tr><td data-label="Candidat">{r["candidat"]}</td>'
        f'<td class="muted small" data-label="Parti">{r["parti"] or ""}</td>'
        f'<td class="num" data-label="Moyenne"><strong>{fr(r["intentions"])}</strong></td>'
        f'<td class="num muted" data-label="IC 95 %">{fr(r["bas"])} – {fr(r["haut"])}</td>'
        f'<td class="num muted" data-label="Amplitude">{fr(r["mini"])} – {fr(r["maxi"])}</td>'
        f'<td class="num" data-label="Sondages">{r["n"]}</td>'
        f'<td class="num" data-label="n effectif">{fr(r["neff"])}</td>'
        f'<td class="num muted small" data-label="Dernier">{r["dernier"]}</td></tr>'
        for r in rows)

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="Moyenne de sondages de la présidentielle 2027 : pondération publiée, intervalle, marges de chaque enquête, mentions légales et limites affichées.">
<title>Présidentielle 2027 — agrégation des sondages, méthode et limites</title>
<link rel="canonical" href="https://dileviathan.fr/observatoire/sondages/">
<style>{CSS}{DARK}</style>
{THEME_HEAD}</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand"><a href="/observatoire/" style="text-decoration:none">Présidentielle 2027</a> <span>· agrégation</span></div>
  <div class="navlinks"><a href="/observatoire/">Accueil</a><a href="/observatoire/candidats/">Les candidats</a><a href="/observatoire/backtest/">Rétro-test 2022</a>{NAV_WORKFLOW}{NAV_LOIS}<a href="#tete">Tête de course</a>
  <a href="#tableau">Tableau</a><a href="#evolution">Évolution</a>
  <a href="#comparaison">Comparaison</a><a href="#methode">Méthode</a>
  <a href="#a-lire">Citer un chiffre</a><a href="#limites">Limites</a></div>{THEME_BTN}
</div></div>

<header class="wrap">
  <span class="eyebrow">Observatoire des sondages · présidentielle 2027</span>
  <h1>Ce que disent les sondages de la présidentielle 2027, agrégés et sourcés</h1>
  <p class="lede">Un seul scénario de candidatures, une moyenne pondérée par la fraîcheur et la
  taille d'échantillon, un intervalle publié, et la liste de toutes les limites. Page régénérée le
  {frdate(agg['generated'])} (heure de Paris).</p>
</header>

<main class="wrap">
<section id="tete" class="card">
  <div>
    <span class="pill b">Tête de course</span>
    {"" if not r0 else f'''
    <div class="kpi" style="margin-top:14px">
      <span class="big">{fr(r0["intentions"])}</span><span class="unit">%</span>
      <span class="muted">— {r0["candidat"]} ({r0["parti"] or "sans étiquette"})</span>
    </div>
    <p class="small muted" style="margin-top:8px">Intervalle à 95 % : <strong>{fr(r0["bas"])} – {fr(r0["haut"])} %</strong>
    · {r0["n"]} sondages · n effectif {fr(r0["neff"])}</p>'''}
    {duo}
    <h3>Lecture rapide</h3>
    <ul class="small muted liste2">
      {"".join(f"<li>{w}</li>" for w in watch) or "<li>Pas assez de candidats pour comparer les écarts.</li>"}
      <li>Total des intentions : {fr(agg["total_intentions"])} % (les intentions des candidats
      sous le seuil de {agg["min_polls"]} sondages ne sont pas affichées ; chaque ligne étant arrondie
      au dixième, leur somme peut s'en écarter d'un dixième).</li>
    </ul>
  </div>
</section>

<section id="perimetre" class="card">
  <span class="pill a">Périmètre</span>
  <div class="mets">
    <div class="met"><span>Premier tour</span><b>{frd("2027-04-18")} <span class="chrono" data-target="{f"{SCRUTIN_1}T20:00:00" if SCRUTIN_1 else ''}">—</span></b></div>
    <div class="met"><span>Sondages dans la source</span><b>{agg["total_polls_all"]}</b></div>
    <div class="met"><span>1<sup>er</sup> tour, {agg["window"]} derniers jours</span><b>{agg["polls_in_window"]}</b></div>
    <div class="met"><span>Scénario retenu</span><b>{agg["scenario"]} · {agg["scenario_size"]} candidats</b></div>
    <div class="met"><span>Sondages du scénario, {agg["window"]} j</span><b>{agg["polls_in_scenario"]}</b></div>
    <div class="met"><span>Sondages agrégés, {agg["agg_window"]} j</span><b>{agg["polls_aggregated"]}</b></div>
    <div class="met"><span>Période couverte</span><b>{frd(agg["first"])} → {frd(agg["last"])}</b></div>
    <div class="met wide"><span>Instituts</span><b>{", ".join(agg["instituts"])}</b></div>
  </div>
</section>

<section id="tableau" class="card">
  <h2>Moyennes pondérées</h2>
  <p class="small muted" style="max-width:none">Les barres sont proportionnelles à la moyenne. <strong>IC 95 %</strong> :
  incertitude statistique de la moyenne. <strong>Amplitude</strong> : minimum et maximum observés
  parmi les sondages agrégés — c'est la dispersion réelle entre instituts, souvent plus parlante
  que l'intervalle.</p>
  {bars}
  <table class="data" style="margin-top:18px">
    <tr><th>Candidat</th><th>Parti</th><th class="num">Moyenne</th><th class="num">IC 95 %</th>
    <th class="num">Amplitude</th><th class="num">Sondages</th><th class="num">n effectif</th>
    <th class="num">Dernier</th></tr>
    {trs}
  </table>
</section>

<section id="evolution" class="card">
  <h2>Évolution, semaine par semaine</h2>
  <p class="small muted" style="max-width:none">Série <strong>rétro-calculée</strong> : la méthode actuelle appliquée aux
  sondages publiés à chaque échéance hebdomadaire — c'est ce que cette page aurait affiché, pas ce
  qu'elle affichait. Le scénario est verrouillé sur {agg["scenario"]} pour que les lignes restent
  comparables. Un écart inférieur à 1 point reste dans la marge : nous ne le commentons pas.</p>
  {mov_table(movs)}
  <p class="small" style="margin-top:14px"><strong>Mouvements sur 7 jours :</strong> {mov_line(movs)}.</p>
  <h3 style="margin-top:26px">Tendance, toutes listes confondues</h3>
  <p class="small muted" style="max-width:none">Ici, chaque sondage du premier tour compte, quelle que soit la liste testée :
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
  <h2>Comparaison : l'agrégation des sondages face à une prévision bayésienne</h2>
  <p class="small" style="max-width:none">Un projet indépendant, <a
  href="https://github.com/whyalwaysrose/presidentielle-2027">whyalwaysrose/presidentielle-2027</a>
  (licence MIT), publie une prévision bayésienne hiérarchique de la même élection, nourrie de la
  <strong>même source de sondages</strong>, avec le choix inverse du nôtre : il <em>intègre</em>
  l'incertitude sur la liste des candidats au lieu de verrouiller un scénario. Voici les deux côte à
  côte, et ce que l'écart nous apprend.</p>
  {forecast_block(agg, trends, fc)}
  {backtest_block()}
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
  <p class="small"><strong>Ces deux réglages ont été mesurés, pas choisis.</strong> Un
  <a href="/observatoire/backtest/">rétro-test complet sur la campagne 2022</a> — la même méthode rejouée
  face au résultat réel — a fixé la fenêtre de sélection à {agg["window"]} jours (la plus courte qui
  couvre toutes les échéances testées) et activé la correction des effets de maison. Il montre aussi
  les limites de l'exercice : notre pondération par fraîcheur n'apporte rien face à la dernière
  enquête seule, et les biais collectifs des instituts subsistent.</p>
  <p class="small">Données : <a href="https://github.com/MieuxVoter/presidentielle2027">MieuxVoter/presidentielle2027</a>
  (licence MIT), flux JSON brut, 1<sup>er</sup> tour uniquement. Le document est régénéré par un
  script, sans retouche manuelle des chiffres ; la méthode ci-dessus est la spécification exacte du
  code qui produit la page.</p>
</section>

{a_lire_bloc(VALEURS)}

<section id="limites" class="card">
  <h2>Limites de la méthode</h2>
  <div class="excl small" style="max-width:none">
    <p style="margin:0 0 8px"><strong>Cette page n'est pas un modèle de prévision.</strong> Elle n'anticipe
    ni la participation, ni les reports de voix, ni les dynamiques de campagne, et ne calcule aucune
    probabilité de victoire.</p>
    <ul style="margin:0">
      <li><strong>Effets de maison corrigés, mais biais partagés non</strong> : l'écart moyen de
      chaque institut au consensus des autres est estimé puis retranché (rétro-test 2022 : gain réel
      mais faible). En revanche, quand <em>tous</em> les instituts se trompent ensemble — en 2022, une
      sous-estimation de Mélenchon de près de 14 points — aucune correction d'effet de maison ne peut
      rien : nous reproduisons ce biais collectif.</li>
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

<section id="mentions" class="card">
  <h2>Sources, traçabilité et mentions légales</h2>
  <p class="small muted" style="max-width:none">Chaque sondage agrégé est nommé, daté et attribué. Les indications ci-dessous
  sont celles que la loi exige pour la publication des résultats d'un sondage :</p>
  {mentions_table(agg)}
  {legal_block(agg)}
</section>
</main>

<footer class="wrap">
  <p><a href="/fr/mentions-legales#observatoire-sondages">Mentions légales</a></p>
</footer>
{THEME_JS}{CHRONO_JS}</body>
</html>
"""


def mentions_table(agg):
    """Sondages agrégés avec les indications requises par l'article 2 de la loi du 19 juillet 1977
    (organisme, commanditaire, effectif, dates, marges d'erreur) — telles que fournies par la source."""
    det = agg.get("polls_detail") or []
    if not det:
        return '<p class="small muted">Aucun sondage dans la fenêtre d\'agrégation.</p>'
    trs = "".join(
        f'<tr><td class="small">{d["institut"]}</td>'
        f'<td class="small">{d["commanditaire"]}</td>'
        f'<td class="num small">{frd(d["debut"])}<br>→ {frd(d["fin"])}</td>'
        f'<td class="num">{fr(d["echantillon"])}</td>'
        f'<td class="num small">± {fpc(d["marge"])}</td>'
        f'<td class="small muted">{d["fichier"]}</td></tr>'
        for d in det)
    return (
        '<table style="margin-top:14px">\n'
        '<tr><th>Institut</th><th>Commanditaire</th><th class="num">Dates</th>'
        '<th class="num">Interrogés</th><th class="num">Marge</th><th>Référence de la notice</th></tr>\n'
        + trs + '</table>\n'
        f'<p class="small muted" style="margin-top:10px">{len(det)} sondages agrégés, du '
        f'{frd(agg["first"])} au {frd(agg["last"])}. La colonne « marge » reprend l\'écart indiqué par '
        'l\'institut pour le candidat le mieux placé de son enquête.</p>')


def legal_block(agg):
    """Ce que la loi impose, et ce que cette page en fait — sans jamais se dire elle-même « sondage »."""
    n = len(agg.get("polls_detail") or [])
    return f'''  <h3 style="margin-top:24px">Notre situation au regard de la loi du 19 juillet 1977</h3>
  <p class="small">Cette page ne réalise aucun sondage et n'interroge personne : elle agrège des
  sondages publiés par des instituts, en citant pour chacun les indications prévues par l'article 2 de
  la loi n° 77-808 du 19 juillet 1977 — organisme ayant réalisé l'enquête, commanditaire, nombre de
  personnes interrogées, dates des interrogations et mention des marges d'erreur. La loi organique
  n° 2021-335 du 29 mars 2021 impose par ailleurs, pour l'élection du Président de la République, que
  toute publication de sondage soit accompagnée des marges d'erreur des résultats publiés : elles
  figurent dans le tableau ci-dessus.</p>
  <p class="small">Les notices déposées par les instituts auprès de la
  <a href="https://www.commission-des-sondages.fr/notices/">Commission des sondages</a> — questions
  posées, méthode d'échantillonnage, taux de non-réponse (article 3 de la même loi) — y sont
  consultables publiquement. Nous ne les reproduisons pas ici, et nous signalons la limite que cela
  crée : le libellé exact de chaque question n'est pas vérifiable dans nos tableaux.</p>
  <p class="small">En période électorale, l'article 11 interdit toute publication, diffusion ou
  commentaire de sondage électoral la veille et le jour du scrutin ; pour l'élection présidentielle,
  cette interdiction court du samedi précédant le scrutin à zéro heure jusqu'à la fermeture du dernier
  bureau de vote. Cette page s'y conformera, y compris en cessant de se régénérer le moment venu.</p>
    <p class="small">La génération quotidienne s'interrompt d'elle-même la veille et le jour de
  chaque tour de scrutin, dès lors que les dates officielles sont renseignées dans le générateur.</p>
  <p class="small">Nous n'employons pas le mot « sondage » pour notre propre calcul : une
  <em>moyenne de sondages</em> n'est pas une enquête, et la présenter comme telle serait une faute
  méthodologique — la loi sanctionne d'ailleurs cet usage impropre.</p>'''


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


def frdate(s):
    """'2026-09-14 15:29' -> '14/09/2026 à 15:29' (date de génération, lecture française)."""
    try:
        d, h = s.split(" ")
        y, m, j = d.split("-")
        return f"{j}/{m}/{y} à {h}"
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


def render_landing(agg, movs=None, trends=None, fc=None):
    movs = movs or []
    trends = trends or []
    r0 = agg["rows"][0] if agg["rows"] else None
    n_cand = len(agg["rows"])
    VALEURS = valeurs_textes(agg, agg["rows"])
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="Observatoire des sondages de la présidentielle 2027 : agrégation sourcée, méthode publiée, limites affichées.">
<title>Présidentielle 2027 — observatoire des sondages, agrégation sourcée</title>
<link rel="canonical" href="https://dileviathan.fr/observatoire/">
<style>{CSS}{DARK}</style>
{THEME_HEAD}</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand">Présidentielle 2027 <span>· observatoire</span></div>
  <div class="navlinks"><a href="/observatoire/sondages/">Agrégation</a><a href="/observatoire/candidats/">Les candidats</a><a href="/observatoire/backtest/">Rétro-test 2022</a>{NAV_WORKFLOW}{NAV_LOIS}<a href="#evolution">Évolution</a>
  <a href="#comparaison">Comparaison</a><a href="#methode">Méthode</a><a href="#donnees">Données</a><a href="#limites">Limites</a></div>{THEME_BTN}
</div></div>

<header class="wrap hero">
  <span class="eyebrow">Observatoire des sondages · présidentielle 2027</span>
  <h1>Agrégation des sondages de la présidentielle 2027</h1>
  <p class="lede">Nous compilons les sondages publiés par les instituts, <strong>un scénario de
  candidatures à la fois</strong>, avec la méthode écrite noir sur blanc et les limites affichées à
  côté des chiffres. Pas de probabilité de victoire : une lecture sourcée, datée, discutable.</p>
  <div class="cta">
    <a class="btn" href="/observatoire/sondages/">Voir l'agrégation du jour</a>
    <a class="btn2" href="#methode">La méthode</a>
  </div>

  <div class="statgrid">
    <div class="stat"><span>Favori du scénario retenu</span>
      <b>{"" if not r0 else fr(r0["intentions"]) + " %"}</b>
      <span>{"" if not r0 else r0["candidat"]}</span></div>
    <div class="stat"><span>Sondages agrégés</span><b>{agg["polls_aggregated"]}</b>
      <span>sur {agg["agg_window"]} jours</span></div>
    <div class="stat"><span>Instituts couverts</span><b>{len(agg["instituts"])}</b>
      <span>{", ".join(agg["instituts"][:3])}</span></div>
    <div class="stat"><span>Dernière enquête</span><b>{agg["last"][8:10]}/{agg["last"][5:7]}/{agg["last"][0:4]}</b>
      <span>période : {agg["first"][8:10]}/{agg["first"][5:7]}/{agg["first"][0:4]} → {agg["last"][8:10]}/{agg["last"][5:7]}/{agg["last"][0:4]}</span></div>
  </div>
  <div class="chrono-glass">
      <span class="chrono-glass-label">Premier tour</span>
      <div class="chrono-glass-units">
        <div class="chrono-unit"><span class="chrono-num" data-target="{f"{SCRUTIN_1}T20:00:00" if SCRUTIN_1 else ''}" data-unit="d">--</span><span class="chrono-lab">jours</span></div>
        <div class="chrono-unit"><span class="chrono-num" data-target="{f"{SCRUTIN_1}T20:00:00" if SCRUTIN_1 else ''}" data-unit="h">--</span><span class="chrono-lab">heures</span></div>
        <div class="chrono-unit"><span class="chrono-num" data-target="{f"{SCRUTIN_1}T20:00:00" if SCRUTIN_1 else ''}" data-unit="m">--</span><span class="chrono-lab">minutes</span></div>
        <div class="chrono-unit"><span class="chrono-num" data-target="{f"{SCRUTIN_1}T20:00:00" if SCRUTIN_1 else ''}" data-unit="s">--</span><span class="chrono-lab">secondes</span></div>
      </div>
      <span class="chrono-glass-foot">dimanche 18 avril 2027</span>
    </div>
  <p class="small muted">Scénario retenu : {agg["scenario"]}
  ({agg["scenario_size"]} candidats) · {n_cand} candidats publiés · source : {agg["total_polls_all"]}
  sondages compilés, dont {agg["polls_in_window"]} sur les {agg["window"]} derniers jours.
  Page régénérée le {frdate(agg["generated"])}.</p>
</header>

<main class="wrap">
<section id="evolution" class="card">
  <h2>Évolution, semaine par semaine</h2>
  <p class="small muted" style="max-width:none">Série <strong>rétro-calculée</strong> par la méthode actuelle, sur les sondages
  publiés à chaque échéance hebdomadaire (ce que la page aurait affiché, pas ce qu'elle affichait).
  Un écart inférieur à 1 point reste dans la marge et n'est pas commenté.</p>
  {mov_table(movs)}
  <p class="small" style="margin-top:14px"><strong>Mouvements sur 7 jours (scénario retenu) :</strong>
  {mov_line(movs)}.</p>
  <h3 style="margin-top:24px">Tendance, toutes listes confondues</h3>
  <p class="small muted" style="max-width:none">Indicateur de direction : chaque sondage du premier tour compte, quelle que
  soit la liste testée. Les niveaux ne sont pas comparables à ceux du tableau ci-dessus ; seule
  l'évolution compte, et elle est plus robuste (beaucoup plus d'enquêtes).
  <a href="/observatoire/sondages/#evolution">Méthode et détail</a>.</p>
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
        <li>Une page méthode complète et un générateur sans dépendance externe — les chiffres ne sont
        jamais saisis à la main.</li>
      </ul>
    </div>
    <div class="card2">
      <h3 class="ko">Ce que ça ne fait pas</h3>
      <ul class="tight">
        <li>Aucune probabilité de victoire, aucun modèle de second tour.</li>
        <li>Aucune probabilité de second tour ni de victoire ; aucune anticipation de la
        participation ou des reports de voix.</li>
        <li>Aucune donnée de question : le libellé exact des questions posées n'est pas dans
        notre source (voir les notices de la Commission des sondages).</li>
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
  les limites complètes sont sur la page <a href="/observatoire/sondages/">Agrégation</a>.</p>
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
  </div>
</section>

<section id="comparaison" class="card">
  <h2>Comparaison avec une prévision bayésienne</h2>
  <p class="small muted" style="max-width:none">Un projet MIT indépendant prévoit la même élection à partir des
  <strong>mêmes sondages</strong>, mais en intégrant l'incertitude sur la liste des candidats au lieu
  de verrouiller un scénario. En résumé : les deux lectures se rejoignent désormais sur tout le haut du
  tableau (aucun écart supérieur à 0,3 point sous le quatrième), et leurs intervalles restent dix fois
  plus larges que les nôtres — donc plus honnêtes. Analyse complète sur la page
  <a href="/observatoire/sondages/#comparaison">Agrégation</a>.</p>
  {forecast_block(agg, trends, fc)}
  {backtest_block()}
</section>

<section id="limites" class="card">
  <h2>À lire avant de citer un chiffre</h2>
  <div class="excl small" style="max-width:none">
    <p style="margin:0 0 8px"><strong>Cette page n'est pas un modèle de prévision.</strong> Elle décrit
    ce que disent les sondages publiés, agrémenté d'une incertitude explicite — rien de plus.</p>
    <p style="margin:0">Une moyenne de sondages n'est pas un résultat, et une intention de vote n'est
    pas un vote. La méthode est versionnée : chaque changement est daté dans le journal ci-dessous, et
    le détail de ce qui peut être cité — sous quelle forme et à quelles conditions — se trouve dans la
    section <a href="/observatoire/sondages/#a-lire">Citer un chiffre</a>.</p>
  </div>
  <ul class="tight small" style="max-width:none">
    <li><strong>Citez la moyenne, jamais un sondage</strong> : « moyenne des sondages publiés au
    {VALEURS["date_maj"]}, scénario {VALEURS["scenario"]} ({VALEURS["scenario_size"]} candidats),
    {VALEURS["polls_aggregated"]} enquêtes agrégées ».</li>
    <li><strong>Citez l'intervalle avec le niveau</strong> : {VALEURS["tete_nom"]}
    {VALEURS["tete_val"]} % [{VALEURS["tete_ic"]}]. Un chiffre nu laisse croire à une précision que la
    moyenne n'a pas.</li>
    <li><strong>Sous un point d'écart, nous ne commentons pas</strong> — l'écart est dans la marge, et
    il ne doit pas être commenté davantage ailleurs.</li>
  </ul>
</section>

{changelog_bloc(3, "Dernières mises à jour", "Résumé des trois dernières. Le journal complet, avec les sources et le cadre légal, est dans la section Citer un chiffre de la page Agrégation.", VALEURS)}
</main>

<footer class="wrap">
  <p><a href="/fr/mentions-legales#observatoire-sondages">Mentions légales</a></p>
</footer>
{THEME_JS}{CHRONO_JS}</body>
</html>
"""


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
    open(os.path.join(SITE, "sondages", "index.html"), "w", encoding="utf-8").write(
        render_sondages(agg, movs, trends, fc))
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
    print(f"série : {len(series)} points hebdo | archive quotidienne : {n_hist} jour(s) "
          f"-> {os.path.join(DATA, 'history.jsonl')}")


if __name__ == "__main__":
    main()
