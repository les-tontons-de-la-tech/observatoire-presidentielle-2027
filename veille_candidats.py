#!/usr/bin/env python3
"""Veille de la liste des candidats à la présidentielle 2027.

Surveille la source de consolidation citée par data/candidats2027.json — le dossier
« Présidentielle 2027 » de LCP, qui publie ses articles au fil de l'eau — et ne parle que si
quelque chose a bougé : la date de dernière modification du dossier, ou la liste des titres
publiés dans sa grille.

Pourquoi le dossier remplace l'article de recensement (14/10/2026) : l'article « qui sont les
candidats, déjà en lice et prétendants » n'était plus mis à jour depuis le 24 septembre, et ne
mentionnait donc ni les déclarations d'octobre ni celle du jour. Une veille muette sur une source
figée se lit comme une veille en panne. Le dossier, lui, porte une date de modification lisible
et ses derniers titres, chacun avec sa date.

Ce que la veille lit, et où : le tampon de modification vit dans le JSON-LD de la page
(« dateModified »), et les articles dans la grille du dossier, un bloc Drupal par carte
(« views-field-title » pour le titre, « views-field-created » pour la date). Rien n'est deviné :
si la structure change, la veille le dit au lieu de se taire.

Silencieuse quand rien ne change, et quand la source est injoignable — mais après trois échecs
consécutifs elle parle, parce qu'une veille muette et une veille cassée se ressemblent. Une page
qui répond sans qu'on sache plus la lire est signalée comme telle : c'est un problème de lecture,
pas de réseau, et la distinction compte pour savoir quoi réparer.

Le fichier de référence n'est jamais modifié, hors sa date de contrôle : la liste est un travail
éditorial. La veille signale, l'auteur tranche.
"""
import html
import json
import os
import pathlib
import re
import time
import unicodedata
import urllib.error
import urllib.request

DEPOT = pathlib.Path("/root/presidentielle2027")
REFERENCE = DEPOT / "data" / "candidats2027.json"
ETAT = pathlib.Path("/root/.hermes/data/veille_candidats_etat.json")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120 Safari/537.36")
ECHECS_AVANT_ALERTE = 3

# Un nom de personne : deux à quatre mots, tous commençant par une majuscule. Les déterminants
# et les mots de liaison sont exclus, sinon « La France » ou « Face à » passeraient pour des noms.
MOT_MAJ = r"[A-ZÉÈÀÂÎÔÛ][\w'’\-\.]+"
NOM_RE = re.compile(rf"(?:{MOT_MAJ})(?:\s+{MOT_MAJ}){{1,3}}")
STOPLIST = {"la", "le", "les", "un", "une", "des", "du", "de", "au", "aux", "en", "et", "ou",
            "or", "mais", "car", "dans", "sur", "sous", "après", "avant", "face", "chez",
            "avec", "sans", "pour", "par", "que", "qui", "quand", "comment", "pourquoi"}
MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
        "décembre": 12, "decembre": 12}


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


def texte_de(brut):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", brut))).strip()


def analyser(page):
    """Retourne (date de modification du dossier, {url: (titre, date)})."""
    m = re.search(r'"dateModified"\s*:\s*"([^"]+)"', page)
    date_mod = m.group(1) if m else ""

    articles = {}
    for ma in re.finditer(r'<a href="([^"]*?/actualites/[^"#?]+)"[^>]*>', page):
        url = html.unescape(ma.group(1))
        fen = page[ma.end(): ma.end() + 4000]
        coupe = fen.find("views-row")          # ne jamais déborder sur la carte suivante
        if coupe != -1:
            fen = fen[:coupe]
        mt = re.search(r"views-field-title[^>]*>\s*<h[23][^>]*>(.*?)</h[23]>", fen, re.S)
        md = re.search(r"views-field-created[^>]*>\s*<span[^>]*>([^<]+)</span>", fen, re.S)
        if not (mt and md):
            continue
        articles[url] = (texte_de(mt.group(1)), re.sub(r"\s+", " ", md.group(1)).strip())
    return date_mod, articles


def date_iso(date_fr):
    """« 14 octobre 2026 » -> « 2026-10-14 » ; chaîne vide si la date n'est pas lisible."""
    m = re.search(r"(\d{1,2})\s+([A-Za-zéûôàè]+)\s+(\d{4})", date_fr or "")
    if not m:
        return ""
    mois = MOIS.get(m.group(2).lower())
    return f"{m.group(3)}-{mois:02d}-{int(m.group(1)):02d}" if mois else ""


def noms_dans(texte):
    """Noms de personnes repérables dans un titre (« Natacha Polony », « Jean-Luc Mélenchon »)."""
    trouves = set()
    for m in NOM_RE.finditer(texte or ""):
        t = m.group(0).strip(" .,’'")
        if t.split()[0].lower() in STOPLIST:
            continue
        trouves.add(t)
    return trouves


def horodatage_lisible(iso):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T?(\d{2})?:?(\d{2})?", iso or "")
    if not m:
        return iso or "inconnue"
    j, h, mi = f"{m.group(3)}/{m.group(2)}/{m.group(1)}", m.group(4) or "", m.group(5) or ""
    return f"{j} à {h}:{mi}" if h else j


def dater_verification():
    """Pose la date du jour comme date de vérification du fichier de référence.

    Cette date dit quand la liste a été **contrôlée**, pas quand la source a changé : elle doit
    donc avancer même quand le contrôle ne trouve rien. Sans cela, la page afficherait
    indéfiniment la date du dernier changement, ce qui se lit comme un abandon.

    Écriture ciblée sur la seule valeur, avec remplacement atomique : le fichier est tenu à la
    main, on ne le reformate pas. Seule cette date est touchée, jamais une ligne de candidat.
    """
    jour = time.strftime("%Y-%m-%d")
    brut = REFERENCE.read_text(encoding="utf-8")
    nouveau, n = re.subn(
        r'("verifie_le"\s*:\s*")[^"]*(")',
        lambda m: m.group(1) + jour + m.group(2),
        brut,
        count=1,
    )
    if n == 0 or nouveau == brut:
        return False
    tmp = REFERENCE.with_suffix(".tmp")
    tmp.write_text(nouveau, encoding="utf-8")
    os.replace(tmp, REFERENCE)
    return True


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


def signaler_echec(etat, url, motif):
    etat["echecs"] = int(etat.get("echecs", 0)) + 1
    ecrire_etat(etat)
    if etat["echecs"] >= ECHECS_AVANT_ALERTE:
        print(f"Veille candidats 2027 — {motif} depuis {etat['echecs']} passages")
        print(f"  {url}")
        print("  La liste n'est plus surveillée tant que ce n'est pas réparé.")
    return 0


def main():
    url, reference = source_a_surveiller()
    etat = lire_etat()

    try:
        page = telecharger(url)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        return signaler_echec(etat, url, f"source injoignable ({type(e).__name__} : {e})")

    date_mod, articles = analyser(page)
    if not articles:
        return signaler_echec(etat, url, "page illisible : plus aucun article reconnu dans la grille")

    notre_liste = {c["nom"] for c in reference.get("candidats", [])}
    cles_notre = {cle(n): n for n in notre_liste}
    premier_passage = "articles" not in etat

    precedent_mod = etat.get("date_mod", "")
    precedents = etat.get("articles", {})
    apparus = {u: v for u, v in articles.items() if u not in precedents}
    disparus = {u: v for u, v in precedents.items() if u not in articles}
    ecrire_etat({"source": url, "date_mod": date_mod, "articles": articles, "echecs": 0})

    if premier_passage:
        # Une seule fois : l'état de référence, et l'écart avec notre fichier.
        cites = set()
        for titre, _ in articles.values():
            cites |= noms_dans(titre)
        absents_chez_nous = sorted(n for n in cites if cle(n) not in cles_notre)
        print("Veille candidats 2027 — état de référence")
        print(f"  source   : dossier LCP modifié le {horodatage_lisible(date_mod)}")
        print(f"  articles publiés dans la grille : {len(articles)}")
        print(f"  notre liste : {len(notre_liste)} lignes, vérifiée le {reference.get('verifie_le', '?')}")
        if absents_chez_nous:
            print(f"  personnes citées dans ces titres et absentes de notre liste ({len(absents_chez_nous)}) :")
            for n in absents_chez_nous:
                print(f"    - {n}  (tout n'est pas une candidature)")
        else:
            print("  aucune personne citée dans ces titres n'est absente de notre liste")
        print(f"  {url}")
        return 0

    if date_mod == precedent_mod and not apparus and not disparus:
        # Rien de neuf, mais le contrôle a bien eu lieu : la date de vérification du fichier
        # avance, sans un mot. Un contrôle muet qui laisse la date immobile se lit comme un
        # abandon, alors que la liste est bel et bien surveillée.
        dater_verification()
        return 0  # silence complet, c'est le mode normal

    print("Veille candidats 2027 — la source a bougé")
    if date_mod != precedent_mod:
        print(f"  dossier modifié le {horodatage_lisible(date_mod)} "
              f"(précédemment : {horodatage_lisible(precedent_mod)})")
    if apparus:
        print(f"  articles apparus ({len(apparus)}) :")
        for u, (titre, date_fr) in sorted(apparus.items(), key=lambda x: date_iso(x[1][1]), reverse=True):
            print(f"    + {date_fr:22s} {titre}")
            concerne = sorted(cles_notre[cle(n)] for n in noms_dans(titre) if cle(n) in cles_notre)
            if concerne:
                print(f"      → sur notre liste : {', '.join(concerne)}")
            print(f"      {u}")
    if disparus:
        print(f"  articles sortis de la grille ({len(disparus)}) : "
              + ", ".join(t for t, _ in list(disparus.values())[:4])
              + ("…" if len(disparus) > 4 else ""))
    print(f"  notre liste : data/candidats2027.json ({len(notre_liste)} lignes, "
          f"vérifiée le {reference.get('verifie_le', '?')})")
    print("  → à mettre à jour si une déclaration est réelle ; la page est régénérée et le fichier "
          "commité au passage de 18h.")
    print(f"  {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
