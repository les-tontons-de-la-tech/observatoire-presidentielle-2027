#!/usr/bin/env python3
"""Veille de la liste des candidats à la présidentielle 2027.

Surveille la source de consolidation citée par data/candidats2027.json — LCP, qui recense les
déclarations au fil de l'eau — et ne parle que si quelque chose a bougé : la date de mise à jour
de l'article, ou l'ensemble des noms de personnes cités en gras dans son corps.

Pourquoi les noms en gras : la page est une application, la liste n'y est pas un tableau dans le
HTML statique, mais le corps de l'article y est bel et bien, chaque personne en <strong>. Mesuré
le 21/09/2026 : 30 noms, dont 28 déjà dans notre liste — les deux écarts n'étaient que des
accents (« Edouard » contre « Édouard »), d'où la normalisation.

Silencieux quand rien ne change, et quand la source est injoignable : mais après trois échecs
consécutifs il le dit, parce qu'une veille muette et une veille cassée se ressemblent.

Le fichier de référence n'est jamais modifié : c'est un travail éditorial. La veille signale,
l'auteur tranche.
"""
import html
import json
import os
import pathlib
import re
import sys
import unicodedata
import urllib.error
import urllib.request

DEPOT = pathlib.Path("/root/presidentielle2027")
REFERENCE = DEPOT / "data" / "candidats2027.json"
ETAT = pathlib.Path("/root/.hermes/data/veille_candidats_etat.json")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120 Safari/537.36")
ECHECS_AVANT_ALERTE = 3


def sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def cle(nom):
    """Clé de comparaison : sans accents, apostrophes et tirets unifiés, minuscules."""
    n = sans_accents(nom).lower()
    n = n.replace("’", "'").replace("`", "'")
    n = re.sub(r"[\s\-]+", " ", n)
    return re.sub(r"[^a-z' ]", "", n).strip()


def source_a_surveiller():
    d = json.loads(REFERENCE.read_text(encoding="utf-8"))
    for s in d.get("sources_reference", []):
        if s.get("niveau") == "consolidation presse" and s.get("url"):
            return s["url"], d
    raise SystemExit("source de consolidation absente de data/candidats2027.json")


def telecharger(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "fr-FR,fr;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", errors="replace")


def analyser(page):
    """Retourne (date de mise à jour annoncée, ensemble des noms en gras)."""
    m = re.search(r"mis\s*à\s*jour\s*le\s*([^<]{5,60})", page, re.I)
    date = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    noms = set()
    for brut in re.findall(r"<strong[^>]*>(.*?)</strong>", page, re.S | re.I):
        t = re.sub(r"<[^>]+>", " ", brut)
        t = re.sub(r"\s+", " ", html.unescape(t)).strip()
        if not t or len(t) > 40:
            continue
        # Deux à quatre mots, tous commençant par une majuscule : un nom de personne.
        if re.match(r"^(?:[A-ZÉÈÀÂÎÔÛ][\w'’\-\.]+ ){1,3}[A-ZÉÈÀÂÎÔÛ][\w'’\-]+$", t):
            noms.add(t)
    return date, noms


def lire_etat():
    try:
        return json.loads(ETAT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ecrire_etat(etat):
    ETAT.parent.mkdir(parents=True, exist_ok=True)
    tmp = ETAT.with_suffix(".tmp")
    tmp.write_text(json.dumps(etat, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ETAT)  # remplacement atomique : pas de fichier à moitié écrit


def main():
    url, reference = source_a_surveiller()
    etat = lire_etat()

    try:
        page = telecharger(url)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        echecs = int(etat.get("echecs", 0)) + 1
        etat["echecs"] = echecs
        ecrire_etat(etat)
        if echecs >= ECHECS_AVANT_ALERTE:
            print(f"Veille candidats 2027 — source injoignable depuis {echecs} passages")
            print(f"  {url}")
            print(f"  dernière erreur : {type(e).__name__} : {e}")
            print("  La liste n'est plus surveillée tant que la source ne répond pas.")
        return 0

    date, noms = analyser(page)
    if not noms:
        etat["echecs"] = int(etat.get("echecs", 0)) + 1
        ecrire_etat(etat)
        return 0

    precedent_date = etat.get("date", "")
    precedent_noms = set(etat.get("noms", []))
    premier_passage = not etat.get("noms")

    ajoutes = sorted(noms - precedent_noms)
    retires = sorted(precedent_noms - noms)
    ecrire_etat({"date": date, "noms": sorted(noms), "echecs": 0})

    if premier_passage:
        # Une seule fois : l'état de référence, et l'écart avec notre fichier.
        nôtres = {c["nom"] for c in reference.get("candidats", [])}
        cles_notre = {cle(n): n for n in nôtres}
        absents_chez_nous = sorted(n for n in noms if cle(n) not in cles_notre)
        print("Veille candidats 2027 — état de référence")
        print(f"  source   : article mis à jour le {date or 'date inconnue'}")
        print(f"  noms cités en gras : {len(noms)}")
        print(f"  notre liste : {len(nôtres)} lignes, vérifiée le {reference.get('verifie_le', '?')}")
        if absents_chez_nous:
            print(f"  cités par la source et absents de notre liste ({len(absents_chez_nous)}) :")
            for n in absents_chez_nous:
                print(f"    - {n}")
        else:
            print("  aucun nom cité par la source n'est absent de notre liste")
        print(f"  {url}")
        return 0

    if date == precedent_date and not ajoutes and not retires:
        return 0  # rien de neuf : silence complet, c'est le mode normal

    print("Veille candidats 2027 — la source a bougé")
    if date and date != precedent_date:
        print(f"  article mis à jour le {date} (précédemment : {precedent_date or 'inconnu'})")
    if ajoutes:
        print(f"  noms apparus ({len(ajoutes)}) :")
        for n in ajoutes:
            print(f"    + {n}")
    if retires:
        print(f"  noms disparus ({len(retires)}) :")
        for n in retires:
            print(f"    - {n}")
    print(f"  notre liste : data/candidats2027.json ({len(reference.get('candidats', []))} lignes, "
          f"vérifiée le {reference.get('verifie_le', '?')})")
    print("  → à mettre à jour si une déclaration est réelle ; la page est régénérée et le fichier "
          "commité au passage de 18h.")
    print(f"  {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
