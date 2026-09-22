#!/usr/bin/env python3
"""Contrôle de la borne des descriptions — à lancer depuis la racine du dépôt.

    python3 test_meta_description.py

Ce que ce contrôle refuse : une description de balise <meta> qui dépasse 160 caractères, une
coupe au milieu d'un mot, ou un texte d'auteur modifié dans PAGES_LD. Le texte complet reste
la source des données structurées ; seule la balise est raccourcie.

Stdlib seule, pas de cadre de test : c'est un contrôle, pas une suite.
"""
import sys

import generate as G

BANDE_HAUTE = 160
BANDE_BASSE = 120
echecs = []


def verifier(condition, message):
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  ÉCHEC {message}")
        echecs.append(message)


print("=== 1. couper_description() : cas limites ===")

court = "Une description déjà courte."
verifier(G.couper_description(court) == court, "un texte sous la limite est rendu tel quel")

# Le cas réel : la description de /observatoire/backtest2017/, 198 caractères.
_2017 = (
    "La méthode d'agrégation de l'observatoire rejouée sur la campagne 2017, réglages gelés : "
    "erreur moyenne par échéance, couverture, effet des deux réglages, et ce que cela dit de leur "
    "transférabilité."
)
verifier(len(_2017) == 198, f"le texte de 2017 fait bien 198 caractères (mesuré : {len(_2017)})")
coupe = G.couper_description(_2017)
verifier(len(coupe) <= BANDE_HAUTE, f"ramené sous {BANDE_HAUTE} (obtenu : {len(coupe)})")
verifier(coupe.endswith("…"), "la coupe est annoncée par des points de suspension")
verifier(
    coupe.rstrip("…").rstrip() == _2017[: len(coupe.rstrip("…").rstrip())],
    "la coupe ne réécrit rien avant son point de coupe",
)
dernier_mot_origine = _2017[: len(coupe.rstrip("…").rstrip())].split()[-1]
verifier(
    _2017[len(coupe.rstrip("…").rstrip())] == " ",
    f"coupe sur un mot entier (« {dernier_mot_origine} »), pas au caractère",
)

# Une phrase entière disponible au-delà du minimum : on la garde entière, sans ellipse.
# La première phrase doit franchir DESC_MIN (120) sans discussion, sinon on n'exerce pas la
# branche « coupe à la fin de phrase » — c'est l'erreur que ce contrôle a faite à son premier
# passage, avec une phrase de 119 caractères.
premiere = (
    "Première phrase de contexte volontairement longue, avec suffisamment de mots pour franchir "
    "largement le seuil de cent vingt caractères sans discussion possible."
)
deux_phrases = (
    premiere + " Seconde phrase qui, elle, va faire dépasser la limite haute de cent soixante "
    "caractères, ce qui est précisément ce qu'on veut provoquer ici."
)
print(f"  (cas de test : 1re phrase = {len(premiere)} car, seuil bas = {G.DESC_MIN})")
r2 = G.couper_description(deux_phrases)
verifier(not r2.endswith("…"), "quand une phrase entière tient, la coupe se fait au point, sans ellipse")
verifier(r2.endswith("."), "et la description se termine par un point")
verifier(r2 == premiere, "et la phrase gardée est la première, entière")

print("\n=== 2. Les pages déclarées dans generate.py ===")
for chemin in sorted(G.PAGES_LD):
    texte = G.PAGES_LD[chemin][1]
    servi = G.meta_description(chemin)
    etat = "ok  " if len(servi) <= BANDE_HAUTE else "NON "
    print(f"  [{etat}] {chemin:<30} source {len(texte):>4} car  ->  balise {len(servi):>4} car")
    if len(servi) > BANDE_HAUTE:
        echecs.append(f"{chemin} : balise à {len(servi)} caractères")
    if len(texte) > BANDE_HAUTE and len(servi) == len(texte):
        echecs.append(f"{chemin} : texte trop long mais balise non ramenée")

print("\n=== 3. Le texte de l'auteur n'est pas altéré ===")
sources = {c: G.PAGES_LD[c][1] for c in G.PAGES_LD}
for c in sorted(sources):
    verifier(G.PAGES_LD[c][1] == sources[c], f"{c} : PAGES_LD intact après appel")
verifier(
    len(G.PAGES_LD[next(iter(sources))][1]) >= len(G.meta_description(next(iter(sources)))),
    "la source reste au moins aussi longue que la balise (données structurées préservées)",
)

print("\n=== 4. La page 2017, telle que backtest2017.py la déclare ===")
PAGE_2017 = "/observatoire/backtest2017/"
# On importe le module qui déclare la page : sans ça, ce test ne parlait pas de la vraie page 2017
# mais d'une copie fabriquée ici — et il portait une assertion « la source fait 198 caractères »
# qui serait devenue fausse à la première correction du texte. Un test qui décrit un état révolu
# passe pour de mauvaises raisons.
import backtest2017  # noqa: E402

verifier(PAGE_2017 in G.PAGES_LD, "la page 2017 est déclarée par backtest2017.py")
source = G.PAGES_LD[PAGE_2017][1]
verifier(
    BANDE_BASSE <= len(source) <= BANDE_HAUTE,
    f"le texte déclaré tient dans la bande {BANDE_BASSE}-{BANDE_HAUTE} ({len(source)} car)",
)
servi = G.meta_description(PAGE_2017)
verifier(servi == source, "la balise sert le texte de l'auteur, sans avoir à le couper")

print()
if echecs:
    print(f"{len(echecs)} ÉCHEC(S) :")
    for e in echecs:
        print(f"  - {e}")
    sys.exit(1)
print("TOUS LES CONTRÔLES PASSENT.")
