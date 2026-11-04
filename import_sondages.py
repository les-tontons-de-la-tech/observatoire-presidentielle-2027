#!/usr/bin/env python3
"""Import d'un sondage de la Commission des sondages au format MieuxVoter.

La source réelle du dépôt MieuxVoter n'est pas son `polls.csv` : c'est le catalogue
de la Commission des sondages (`MieuxVoter/sondages-commission-index`), qui publie
chaque notice avec son PDF et son texte extrait. Ce script reprend la chaîne là où
elle s'arrête quand l'amont ne suit plus :

  catalogue → notices « Pres IV » non intégrées → tables d'intentions
  → rapprochement à `hypotheses.csv` → fichiers `polls/<poll_id>.csv`
  → lignes `polls.csv` → enregistrements au format de notre `data/polls.json`.

Il n'écrit rien dans `data/polls.json` : la sortie va dans `data/imports/<enquete>/`,
et l'auteur décide de l'intégration. Un sondage extrait n'est pas un sondage publié.

Usage :
    python3 import_sondages.py --depuis 2026-10-09          # inventaire des IV non intégrées
    python3 import_sondages.py --depuis 2026-10-09 --ifop   # extrait les notices Ifop
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import re
import sys
import unicodedata
import urllib.request

CATALOGUE = ("https://raw.githubusercontent.com/MieuxVoter/sondages-commission-index/"
             "main/")
AMONT = "https://raw.githubusercontent.com/MieuxVoter/presidentielle2027/HEAD/"
DEPOT = pathlib.Path("/root/presidentielle2027")
SORTIE = DEPOT / "data" / "imports"
REFERENCE = DEPOT / "data" / "polls.json"
Z_95 = 1.96


def lire(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-observatoire"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="replace")


def sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def cle(nom: str) -> str:
    n = sans_accents(nom).lower().replace("’", "'").replace("-", " ")
    return re.sub(r"[^a-z' ]", "", re.sub(r"\s+", " ", n)).strip()


def ci(intentions: float, base: float) -> tuple[float, float]:
    """Bornes à 95 %, formule de `compute_confidence_intervals.py` de l'amont."""
    p = intentions / 100
    marge = Z_95 * (p * (1 - p) / base) ** 0.5 * 100
    basse = round(-marge, 2) if p > marge / 100 else round(-intentions, 2)
    return round(marge, 2), basse


def catalogue() -> list[dict]:
    return list(csv.DictReader(io.StringIO(lire(CATALOGUE + "notices_catalog.csv"))))


def derniere_integree() -> str:
    """Dernière date de terrain présente dans notre polls.json."""
    polls = json.loads(REFERENCE.read_text(encoding="utf-8"))["polls"]
    return max(p.get("fin_enquete", "") for p in polls)


def notices_iv(depuis: str) -> list[dict]:
    out = []
    for r in catalogue():
        if (r.get("pdf creation-date") or "")[:10] < depuis:
            continue
        if not (r.get("categorie") or "").lower().startswith("pres"):
            continue
        if not re.search(r"\bIV\b", r["name"]):
            continue
        if not r.get("txt_path"):
            continue
        out.append(r)
    return sorted(out, key=lambda r: (r["pdf creation-date"], r["filename"]))


# --------------------------------------------------------------------------- Ifop

TABLE_LIGNE = re.compile(r"^\s{8,}([A-ZÉÈÀÂÎÔÛ][^\d]{2,60}?)\s+(\d{1,3}[.,]\d)\s*$")


def tableau_ifop(txt: str) -> list[list[tuple[str, float]]]:
    tables, cur = [], []
    for ligne in txt.split("\n"):
        m = TABLE_LIGNE.match(ligne)
        if m:
            nom = m.group(1).strip()
            if "prononcent" in nom.lower() or nom.lower().startswith("total"):
                continue
            cur.append((nom, float(m.group(2).replace(",", "."))))
            continue
        if re.search(r"\bTOTAL\b", ligne, re.I) and cur:
            if len(cur) >= 6 and abs(sum(v for _, v in cur) - 100) <= 0.6:
                tables.append(cur)
            cur = []
    return tables


def meta_ifop(txt: str) -> dict:
    base = re.search(r"échantillon de\s+([\d\s]+?)\s+personnes", txt)
    dates = re.search(r"du\s+(\d{1,2})\s+au\s+(\d{1,2})\s+(janvier|février|mars|avril|mai|"
                      r"juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})", txt)
    commanditaire = re.search(r"réalisée par Ifop pour ([A-Z][^\n]{1,40})", txt)
    mois = {"janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
            "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
            "décembre": 12}
    out = {"echantillon": int(re.sub(r"\s", "", base.group(1))) if base else None,
           "debut_enquete": None, "fin_enquete": None,
           "commanditaire": commanditaire.group(1).strip() if commanditaire else ""}
    if dates:
        j1, j2, m, a = int(dates.group(1)), int(dates.group(2)), mois[dates.group(3)], int(dates.group(4))
        out["debut_enquete"] = f"{a:04d}-{m:02d}-{j1:02d}"
        out["fin_enquete"] = f"{a:04d}-{m:02d}-{j2:02d}"
    return out


# ------------------------------------------------------------------- hypothèses

def hypotheses_amont() -> list[dict]:
    txt = lire(AMONT + "hypotheses.csv")
    out = []
    for r in csv.DictReader(io.StringIO(txt)):
        noms = [n.strip() for n in (r.get("hypothese_complete") or "").split(",") if n.strip()]
        out.append({"id": r["id_hypothese"], "candidates": noms,
                    "comment": r.get("commentaire", "")})
    return out


def rapprocher(noms: list[str], hyps: list[dict]) -> tuple[str | None, bool]:
    cible = {cle(n) for n in noms}
    for h in hyps:
        if {cle(c) for c in h["candidates"]} == cible:
            return h["id"], False
    return None, True


def candidats_amont() -> dict[str, dict]:
    txt = lire(AMONT + "candidats.csv")
    return {cle(r["complete_name"]): r for r in csv.DictReader(io.StringIO(txt))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depuis", default=None, help="date ISO ; défaut = lendemain du dernier terrain intégré")
    ap.add_argument("--ifop", action="store_true", help="extraire les notices Ifop")
    args = ap.parse_args()

    depuis = args.depuis or derniere_integree()
    notices = notices_iv(depuis)
    print(f"Notices « Pres IV » depuis le {depuis} : {len(notices)}")
    for n in notices:
        print(f"  {n['pdf creation-date'][:10]}  {n['name'][:60]:60}  {n['txt_path']}")
    if not args.ifop:
        return 0

    ifop = [n for n in notices if "IFOP" in n["name"].upper()]
    if not ifop:
        print("Aucune notice Ifop dans la fenêtre.")
        return 0

    hyps = hypotheses_amont()
    cands = candidats_amont()
    prochain_h = max(int(h["id"][1:]) for h in hyps) + 1

    for n in ifop:
        txt = lire(CATALOGUE + n["txt_path"])
        tables = tableau_ifop(txt)
        meta = meta_ifop(txt)
        print(f"\n=== {n['filename']}")
        print(f"    base={meta['echantillon']} | terrain {meta['debut_enquete']} → {meta['fin_enquete']}"
              f" | commanditaire {meta['commanditaire'] or '?'}")
        print(f"    tables valides : {len(tables)}")
        if not tables:
            print("    ✗ aucune table à 100 — mise en page hors du motif Ifop")
            continue

        poll_base = f"{meta['debut_enquete'].replace('-', '')}_{meta['fin_enquete'][5:].replace('-', '')}_if" \
            if meta["debut_enquete"] else None
        dossier = SORTIE / (poll_base or n["filename"].replace(".pdf", ""))
        dossier.mkdir(parents=True, exist_ok=True)

        lignes_polls, records = [], []
        for i, table in enumerate(tables):
            suffixe = "ABCDEFGH"[i]
            poll_id = f"{poll_base}_{suffixe}"
            noms = [nom for nom, _ in table]
            hyp, nouveau = rapprocher(noms, hyps)
            if nouveau:
                hyp = f"H{prochain_h}"
                prochain_h += 1
                hyps.append({"id": hyp, "candidates": noms, "comment": "créée à l'import"})
            manquants = [nom for nom in noms if cle(nom) not in cands]

            with (dossier / f"{suffixe}.csv").open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(["candidat", "intentions", "erreur_sup", "erreur_inf"])
                for nom, val in table:
                    sup, inf = ci(val, meta["echantillon"])
                    w.writerow([cands.get(cle(nom), {}).get("complete_name", nom), val, sup, inf])

            lignes_polls.append({
                "poll_id": poll_id, "hypothese": hyp, "nom_institut": "IFOP",
                "commanditaire": meta["commanditaire"], "debut_enquete": meta["debut_enquete"],
                "fin_enquete": meta["fin_enquete"], "echantillon": meta["echantillon"],
                "population": "inscrits sur les listes électorales",
                "tour": "1er Tour", "media": "", "filename": n["filename"],
            })
            records.append({
                "poll_id": poll_id, "institut": "IFOP",
                "commanditaire": meta["commanditaire"],
                "debut_enquete": meta["debut_enquete"], "fin_enquete": meta["fin_enquete"],
                "echantillon": meta["echantillon"],
                "population": "inscrits sur les listes électorales",
                "hypothese": hyp, "tour": "1er Tour", "rolling": "", "media": "True",
                "filename": n["filename"],
                "candidats": [
                    {**{k: cands.get(cle(nom), {}).get(k, "") for k in
                        ("candidate_id", "complete_name", "name", "surname", "parti",
                         "annonce_candidature", "retrait_candidature", "second_round")},
                     "candidat": cands.get(cle(nom), {}).get("complete_name", nom),
                     "intentions": val,
                     "erreur_sup": ci(val, meta["echantillon"])[0],
                     "erreur_inf": ci(val, meta["echantillon"])[1]}
                    for nom, val in table],
            })
            print(f"    {suffixe} : {len(table)} candidats, somme {sum(v for _, v in table):.1f}, "
                  f"{hyp}{' (nouvelle)' if nouveau else ''}"
                  f"{' | noms hors candidats.csv : ' + ', '.join(manquants) if manquants else ''}")

        with (dossier / "polls_rows.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(lignes_polls[0]),
                               lineterminator="\n")
            w.writeheader()
            w.writerows(lignes_polls)
        (dossier / "observatoire.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"    → {dossier}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
