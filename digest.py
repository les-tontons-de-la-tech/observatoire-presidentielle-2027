#!/usr/bin/env python3
"""Digest quotidien du POC (cron) : lit data/movements.json et compose un message court."""
import json, os, sys

POC = "/root/presidentielle2027"
D = os.path.join(POC, "data")
mv = json.load(open(os.path.join(D, "movements.json"), encoding="utf-8"))
hist = []
if os.path.exists(os.path.join(D, "history.jsonl")):
    hist = [json.loads(l) for l in open(os.path.join(D, "history.jsonl"), encoding="utf-8") if l.strip()]

DAY = {"01": "01", "02": "02", "03": "03", "04": "04", "05": "05", "06": "06", "07": "07",
       "08": "08", "09": "09", "10": "10", "11": "11", "12": "12"}


def fr1(x):
    return "—" if x is None else f"{x:.1f}".replace(".", ",")


def sgn(x):
    return "—" if x is None else (("+" if x > 0 else "−") + fr1(abs(x)))


def top(rows, field, n=3):
    sel = [r for r in rows if isinstance(r.get(field), (int, float)) and abs(r[field]) >= 1.0]
    sel.sort(key=lambda r: -abs(r[field]))
    return " · ".join(f'{r["candidat"]} {sgn(r[field])}' for r in sel[:n])


d = mv["generated"][:10]
j, m, a = d[8:10], d[5:7], d[:4]
movs, trends = mv["movs"], mv["trends"]
head = movs[0] if movs else None

lines = []
lines.append(f"📊 Présidentielle 2027 — agrégation du {j}/{m}/{a}")
if head:
    lines.append(f"Scénario {mv['scenario']} — {head['candidat']} {fr1(head['intentions'])} % "
                 f"({sgn(head['delta7'])} sur 7 j)")
mvt = top(trends, "delta7") or top(trends, "delta28")
if mvt:
    horizon = "7 j" if top(trends, "delta7") else "28 j"
    lines.append(f"Mouvement ({horizon}, toutes listes) : {mvt}")
lines.append(f"{mv['polls_window']} sondages sur {mv.get('window', 90)} j · "
             f"{mv['polls_agg']} agrégés · dernière enquête {mv['last']}")
lines.append(f"{len(hist)} jour(s) d'archive quotidienne")
try:
    fc = json.load(open(os.path.join(D, "forecast_bayes.json"), encoding="utf-8"))
    rows = [c for c in fc.get("candidats", []) if (c.get("share") or {}).get("q50") is not None]
    rows.sort(key=lambda c: -c["share"]["q50"])
    if rows:
        top = rows[0]
        lines.append(f"Bayésien (whyalwaysrose, {fc.get('as_of')}) : {top['nom']} "
                     f"{fr1(top['share']['q50'] * 100)} % médiane "
                     f"[{fr1(top['share']['q05'] * 100)}–{fr1(top['share']['q95'] * 100)}], "
                     f"P(victoire) {fr1((top.get('p_win') or 0) * 100)} %")
except Exception:
    pass

lines.append("https://dileviathan.fr/observatoire")

alerts = []
if head is None or not movs:
    alerts.append("aucun résultat : source en retard ou scénario disparu")
if mv["polls_agg"] < 3:
    alerts.append(f"seulement {mv['polls_agg']} sondage(s) agrégé(s) : page fragile")
if alerts:
    lines.insert(1, "⚠️ " + " ; ".join(alerts))

print("\n".join(lines))
