#!/usr/bin/env python3
"""Lit le contenu de chaque amendement voté, pour savoir sur quoi porte réellement le vote.

Le titre d'un texte ne dit pas ce que ses amendements touchent : le projet de loi de
finances pour 2027 s'intitule « finances » et contient pourtant un amendement créant une
taxe sur les flux de données numériques. Tant qu'on ne lit pas l'amendement, ce texte ne
peut pas apparaître dans le thème Numérique.

Pour chaque scrutin :
  page du scrutin (elle porte le lien vers l'amendement)
    → page de l'amendement (elle porte son dispositif)
      → on ne conserve que les premiers milliers de caractères du dispositif.

Sortie incrémentale : out/dispositifs.jsonl (une ligne par scrutin, reprise possible).
Aucune page n'est conservée : 9 260 pages d'environ 1 Mo ne tiendraient pas sur le disque.
"""
import json
import os
import re
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/root/presidentielle2027")
import veille_lois as V

RACINE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(RACINE, "data", "lois_votes")
FICHIER = os.path.join(OUT, "dispositifs.jsonl")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
verrou = threading.Lock()


def lire(url, taille_max=1_200_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.read(taille_max).decode("utf-8", "replace")
    except Exception:
        return ""


def extraire_dispositif(html):
    m = re.search(r"ARTICLE\s+\w+", html)
    if not m:
        return "", ""
    debut = max(0, m.start())
    brut = re.sub(r"(?s)<[^>]+>", " ", html[debut:debut + 16000])
    t = re.sub(r"\s+", " ", brut)
    for a, b in (("&#x2019;", "'"), ("&#x2013;", "–"), ("&#x00E9;", "é"), ("&nbsp;", " "),
                 ("&quot;", '"'), ("&amp;", "&"), ("&laquo;", "«"), ("&raquo;", "»")):
        t = t.replace(a, b)
    for stop in ("Navette", "Travaux parlementaires", "Partager", "À lire aussi"):
        j = t.find(stop)
        if j > 200:
            t = t[:j]
    return t.strip()[:2500], m.group(0)


def traiter(s):
    num = s.get("numero")
    titre = (s.get("titre") or "")
    if not num:
        return None
    page = lire(f"https://www.assemblee-nationale.fr/dyn/17/scrutins/{num}")
    lien = ""
    m = re.search(r'href="(https://www\.assemblee-nationale\.fr/dyn/17/amendements/[^"]+)"', page)
    if m:
        lien = m.group(1)
    dispositif, article = "", ""
    if lien:
        dispositif, article = extraire_dispositif(lire(lien))
    return {"numero": num, "titre": titre[:300], "lien": lien,
            "article": article, "dispositif": dispositif}


def main():
    scrutins = [s for s in V.load_scrutins(17) if s.get("numero")]
    # Priorité aux textes dont le titre ne dit pas le contenu (finances, simplification,
    # programmation) : c'est là qu'un amendement peut porter sur un tout autre sujet.
    # Les autres textes sont classés par leur titre, qui est explicite.
    # Ordre de priorité : les scrutins les plus récents d'abord. Un nouveau scrutin doit
    # être lu le jour même ; le stock ancien se résorbe au fil des passages.
    scrutins.sort(key=lambda s: (s.get("dateScrutin") or "", str(s.get("numero"))), reverse=True)
    faits = set()
    if os.path.exists(FICHIER):
        for ligne in open(FICHIER, encoding="utf-8"):
            try:
                faits.add(json.loads(ligne)["numero"])
            except Exception:
                pass
    plafond = 400
    for i, a in enumerate(sys.argv):
        if a == "--max" and i + 1 < len(sys.argv):
            plafond = int(sys.argv[i + 1])
    a_faire = [s for s in scrutins if str(s["numero"]) not in {str(f) for f in faits}][:plafond]
    restants = len([s for s in scrutins if str(s["numero"]) not in {str(f) for f in faits}])
    print(f"  {len(scrutins)} scrutins · {len(faits)} déjà lus · {restants} restants "
          f"· {len(a_faire)} lus ce passage", flush=True)

    with open(FICHIER, "a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=24) as ex:
        for i, res in enumerate(ex.map(traiter, a_faire), 1):
            if res:
                with verrou:
                    f.write(json.dumps(res, ensure_ascii=False) + "\n")
                    if i % 250 == 0:
                        f.flush()
                        print(f"    {i}/{len(a_faire)} · dernier : {res['numero']}", flush=True)
    n = sum(1 for _ in open(FICHIER, encoding="utf-8"))
    avec = sum(1 for l in open(FICHIER, encoding="utf-8") if json.loads(l).get("dispositif"))
    print(f"  terminé : {n} scrutins lus · {avec} avec dispositif exploitable")


if __name__ == "__main__":
    main()
