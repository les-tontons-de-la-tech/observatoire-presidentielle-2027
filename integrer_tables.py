#!/usr/bin/env python3
"""Intègre les tableaux extraits des notices à data/polls_importes.json.

Entrée : les JSON produits par l'extraction (`cache/sondages/*.json`), au format
{notices: [{url, institut, sample, debut, fin, sponsor, tables: [{label, candidates:
[{name, value}], sum}]}]}.

Sortie : `data/polls_importes.json`, la couche locale que `generate.py` ajoute à la
source amont. Rien n'est publié ici : la page se régénère ensuite avec cette couche,
et l'amont reste prioritaire (voir `_avec_imports` dans generate.py).

Refus explicites, jamais de correction au jugé :
  - une table dont la somme s'écarte de 100 de plus de 0,6 ;
  - une table de moins de 6 candidats ;
  - un nom de candidat absent de candidats.csv ;
  - des dates de terrain non ISO.
Une table refusée est comptée et nommée dans le rapport.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
import re
import unicodedata
import urllib.request

DEPOT = pathlib.Path("/root/presidentielle2027")
SORTIE = DEPOT / "data" / "polls_importes.json"
REFERENCE = DEPOT / "data" / "polls.json"
SOURCE = pathlib.Path("/root/.hermes/profiles/dileviathan/cache/sondages")
AMONT = "https://raw.githubusercontent.com/MieuxVoter/presidentielle2027/HEAD/"
CODES = {"cluster17": "cl", "elabe": "el", "harris interactive": "hi", "ifop": "if",
         "ipsos bva": "ip", "odoxa": "od", "opinionway": "ow", "toluna harris interactive": "hi"}
# Nom affiché : celui de la source amont, pour que la page ne montre pas deux graphies du même
# institut selon que l'enquête vient d'eux ou de nous.
CANON = {"cluster17": "Cluster17", "elabe": "ELABE", "harris interactive": "Harris Interactive",
         "toluna harris interactive": "Harris Interactive",
         "ifop": "IFOP", "ipsos bva": "Ipsos BVA", "odoxa": "ODOXA", "opinionway": "OpinionWay"}
Z_95 = 1.96


def sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def cle(nom: str) -> str:
    n = sans_accents(nom).lower().replace("’", "'").replace("-", " ")
    return re.sub(r"[^a-z' ]", "", re.sub(r"\s+", " ", n)).strip()


def lire(url: str) -> str:
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "hermes-observatoire"}),
        timeout=30).read().decode("utf-8", errors="replace")


def ci(valeur: float, base: float) -> tuple[float, float]:
    p = valeur / 100
    marge = Z_95 * (p * (1 - p) / base) ** 0.5 * 100
    basse = round(-marge, 2) if p > marge / 100 else round(-valeur, 2)
    return round(marge, 2), basse


def candidats_amont() -> dict[str, dict]:
    txt = lire(AMONT + "candidats.csv")
    return {cle(r["complete_name"]): r for r in csv.DictReader(io.StringIO(txt))}


def hypotheses_amont() -> list[dict]:
    txt = lire(AMONT + "hypotheses.csv")
    out = []
    for r in csv.DictReader(io.StringIO(txt)):
        noms = [n.strip() for n in (r.get("hypothese_complete") or "").split(",") if n.strip()]
        out.append({"id": r["id_hypothese"], "candidates": noms})
    return out


def identite(r: dict) -> tuple:
    return (str(r.get("institut", "")).strip().lower(), r.get("debut_enquete", ""),
            r.get("fin_enquete", ""), r.get("hypothese", ""))


def main() -> int:
    base = json.loads(REFERENCE.read_text(encoding="utf-8"))["polls"]
    # Identité = institut + dates + hypothèse (l'hypothèse étant attribuée sur l'ensemble des
    # candidats testés). Le poll_id ne sert pas : l'amont le partage entre plusieurs tableaux
    # d'une même enquête, et s'en servir ferait sauter des tableaux légitimes.
    deja = {identite(p) for p in base}
    cands = candidats_amont()
    hyps = hypotheses_amont()
    prochain = max(int(h["id"][1:]) for h in hyps if h["id"][1:].isdigit()) + 1

    if SORTIE.exists():
        anciens = json.loads(SORTIE.read_text(encoding="utf-8"))
        anciens = anciens.get("polls", anciens) if isinstance(anciens, dict) else anciens
    else:
        anciens = []
    records = list(anciens)
    # Une réexécution ne doit pas dupliquer la couche locale : ses entrées comptent comme
    # déjà intégrées, exactement comme celles de la source amont.
    for r in anciens:
        deja.add(identite(r))

    refuses, gardes = [], []
    for f in sorted(SOURCE.glob("*.json")):
        paquet = json.loads(f.read_text(encoding="utf-8"))
        for n in paquet.get("notices", []):
            institut = (n.get("institut") or "").strip()
            _cle_inst = next((k for k in CODES if institut.lower().startswith(k.split()[0])), None)
            code = CODES.get(institut.lower()) or (CODES[_cle_inst] if _cle_inst else None)
            institut = CANON.get(_cle_inst, institut) if _cle_inst else institut
            debut, fin = n.get("debut"), n.get("fin")
            base_n = n.get("sample")
            if not (code and debut and fin and base_n and re.fullmatch(r"\d{4}-\d{2}-\d{2}", debut)
                    and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fin)):
                refuses.append((f.name, institut, "métadonnées incomplètes (code, dates ou base)"))
                continue
            prefixe = f"{debut.replace('-', '')}_{fin[5:].replace('-', '')}_{code}"
            for i, t in enumerate(n.get("tables", [])):
                noms = [(c.get("name") or "").strip() for c in t.get("candidates", [])]
                valeurs = [float(c.get("value")) for c in t.get("candidates", [])]
                somme = round(sum(valeurs), 2)
                if len(noms) < 6:
                    refuses.append((f.name, f"{institut} {debut}", f"table {i+1} : {len(noms)} candidats"))
                    continue
                if abs(somme - 100) > 0.6:
                    refuses.append((f.name, f"{institut} {debut}", f"table {i+1} : somme {somme}"))
                    continue
                inconnus = [x for x in noms if cle(x) not in cands]
                if inconnus:
                    refuses.append((f.name, f"{institut} {debut}",
                                    f"table {i+1} : noms hors candidats.csv ({', '.join(inconnus[:3])})"))
                    continue
                cible = {cle(x) for x in noms}
                hyp = next((h["id"] for h in hyps if {cle(c) for c in h["candidates"]} == cible), None)
                if hyp is None:
                    hyp = f"H{prochain}"
                    prochain += 1
                    hyps.append({"id": hyp, "candidates": noms})
                suffixe = "ABCDEFGHIJ"[i]
                poll_id = f"{prefixe}_{suffixe}"
                rec = {
                    "poll_id": poll_id, "institut": institut,
                    "commanditaire": n.get("sponsor", ""), "debut_enquete": debut,
                    "fin_enquete": fin, "echantillon": int(base_n),
                    "population": n.get("population", "inscrits sur les listes électorales"),
                    "hypothese": hyp, "tour": "1er Tour", "rolling": "", "media": "True",
                    "filename": n.get("url", "").rsplit("/", 1)[-1].replace(".txt", ".pdf"),
                    "candidats": [],
                }
                for nom, valeur in zip(noms, valeurs):
                    c = cands[cle(nom)]
                    sup, inf = ci(valeur, int(base_n))
                    rec["candidats"].append({
                        "candidate_id": c.get("candidate_id", ""),
                        "candidat": c["complete_name"], "complete_name": c["complete_name"],
                        "name": c.get("name", ""), "surname": c.get("surname", ""),
                        "parti": c.get("parti", ""),
                        "annonce_candidature": c.get("annonce_candidature", ""),
                        "retrait_candidature": c.get("retrait_candidature", ""),
                        "second_round": c.get("second_round", ""),
                        "intentions": valeur, "erreur_sup": sup, "erreur_inf": inf,
                    })
                if identite(rec) in deja:
                    refuses.append((f.name, f"{institut} {debut}", f"table {i+1} : déjà intégrée ({poll_id})"))
                    continue
                deja.add(identite(rec))
                records.append(rec); gardes.append(rec)

    SORTIE.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"tables retenues : {len(gardes)} | refusées : {len(refuses)} | total couche locale : {len(records)}")
    for r in gardes:
        print(f"  + {r['poll_id']:22} {r['hypothese']:6} {r['institut']:26} "
              f"{r['debut_enquete']}→{r['fin_enquete']} n={r['echantillon']} "
              f"{len(r['candidats'])} cand.")
    for f, ou, pourquoi in refuses:
        print(f"  ✗ {f} | {ou} | {pourquoi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
