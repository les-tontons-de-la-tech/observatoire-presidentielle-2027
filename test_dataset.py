#!/usr/bin/env python3
"""Contrôle du jeu de données déclaré — à lancer depuis la racine du dépôt, après génération.

    python3 test_dataset.py

Ce que ce contrôle refuse : un `Dataset` déclaré sans `distribution`, une distribution qui
pointe vers un fichier absent du site, un export qui ne porte pas les clés que le balisage
promet. Le balisage et le fichier doivent dire la même chose — c'est tout l'intérêt.

Stdlib seule, pas de cadre de test : c'est un contrôle, pas une suite.
"""
import json
import os
import re
import sys

import generate as G

echecs = []


def verifier(condition, message):
    if condition:
        print(f"  ✓ {message}")
    else:
        echecs.append(message)
        print(f"  ✗ {message}")


for chemin in G.PAGES_DATASET:
    html = G.ld_json(chemin)
    bloc = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    verifier(bloc is not None, f"{chemin} : un graphe JSON-LD")
    if not bloc:
        continue
    graphe = json.loads(bloc.group(1))["@graph"]
    noeuds = [n for n in graphe if n.get("@type") == "Dataset"]
    verifier(len(noeuds) == 1, f"{chemin} : un et un seul Dataset")
    if not noeuds:
        continue
    n = noeuds[0]
    verifier(n.get("@id") == G.DATASET_ID, f"{chemin} : @id stable ({G.DATASET_ID})")
    distrib = n.get("distribution") or []
    verifier(len(distrib) == 2, f"{chemin} : deux distributions (JSON + CSV)")
    for d in distrib:
        # Le dossier `site/` est monté à la racine de /observatoire/ : la distribution est donc
        # relative à /observatoire/, pas à la racine du domaine.
        rel = d.get("contentUrl", "").replace(G.SITE_URL + "/observatoire/", "")
        verifier(bool(d.get("encodingFormat")) and os.path.isfile(os.path.join(G.SITE, rel)),
                 f"{chemin} : distribution servie — {rel}")
    verifier(n.get("license") and n.get("isAccessibleForFree") is True,
             f"{chemin} : licence déclarée et accès libre")
    verifier(bool(n.get("variableMeasured")), f"{chemin} : ce que le jeu mesure est nommé")

# L'export doit porter ce que le balisage promet, sinon la distribution ne tient pas parole.
f_json = os.path.join(G.SITE, "sondages", "donnees.json")
verifier(os.path.isfile(f_json), "export JSON présent")
if os.path.isfile(f_json):
    with open(f_json, encoding="utf-8") as f:
        doc = json.load(f)
    for cle in ("genere_le", "calcule_le", "methode_url", "unites", "candidats"):
        verifier(cle in doc, f"export : clé « {cle} »")
    candidats = doc.get("candidats") or []
    verifier(bool(candidats), f"export : {len(candidats)} candidat(s)")
    verifier(all("moyenne_pct" in c and "ic95_bas_pct" in c and "ic95_haut_pct" in c
                 for c in candidats),
             "export : chaque candidat porte une moyenne et son intervalle")

sys.exit(1 if echecs else 0)
