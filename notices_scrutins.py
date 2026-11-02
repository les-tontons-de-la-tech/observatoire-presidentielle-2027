#!/usr/bin/env python3
"""Rédige une notice PAR SCRUTIN, à partir du dispositif officiel de son amendement.

Pourquoi par scrutin et non par texte : la carte du projet de loi de finances dans le
thème Numérique n'affiche que trois scrutins, dont l'amendement n° 1358 sur la taxe des
données. Une notice attachée au texte parlait d'un autre amendement — donc elle était
masquée, et la carte restait sans explication. La notice doit décrire le vote montré.

Modes :
  --affiches   ne traite que les scrutins réellement affichés par le site (le dernier de
               chaque texte et le dernier de chaque couple texte/thème) — rapide, et
               suffisant pour que chaque carte porte son explication ;
  (défaut)     traite tous les scrutins dont le dispositif a été lu.

Sortie : out/notices_scrutins.json — { "9336": "…", … }
"""
import html
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veille_lois as V
import veille_votes as votes2

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lois_votes")
F_DISP = os.path.join(OUT, "dispositifs.jsonl")
F_NOTICES = os.path.join(OUT, "notices_scrutins.json")
KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODELE = "deepseek/deepseek-chat"

CONSIGNE = """Tu rédiges la notice d'un vote parlementaire pour un observatoire citoyen.

On te donne le DISPOSITIF OFFICIEL d'un amendement (le texte déposé) et les données du vote.
Écris 1 à 3 phrases en français qui disent ce que fait la mesure, puis le résultat du vote.

Règles absolues :
- N'utilise que ce qui figure dans le dispositif ou dans les données du vote. N'invente
  aucun chiffre, aucune date, aucun nom, aucun groupe absent du texte.
- Aucun jugement, aucun adjectif de valeur, aucune formule de commentateur.
- Commence par la mesure : « Crée… », « Étend… », « Supprime… », « Impose… ».
- Si le dispositif ne permet pas de savoir ce que fait la mesure, réponds : VIDE
- Réponds par le texte seul, sans préambule ni guillemets."""


def appel(item):
    num, dispositif, titre = item
    corps = {"model": MODELE, "temperature": 0.2, "max_tokens": 300,
             "messages": [{"role": "system", "content": CONSIGNE},
                          {"role": "user", "content": f"DISPOSITIF OFFICIEL :\n{dispositif[:2600]}\n\n"
                                                      f"SCRUTIN : {titre[:200]}"}]}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(corps).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.load(r)
        txt = (d["choices"][0]["message"]["content"] or "").strip()
        txt = re.sub(r'^["«\s]+|["»\s]+$', "", txt)
        if txt.upper().startswith("VIDE") or len(txt) < 25:
            return num, ""
        return num, re.sub(r"\s+", " ", txt)[:600]
    except Exception:
        return num, None


def affiches():
    """Numéros des scrutins que le site met réellement en avant."""
    scrutins = V.load_scrutins(votes2.LEG)
    groupes = defaultdict(list)
    for s in scrutins:
        nom, _ = V.law_name(V._clean(s.get("titre") or ""))
        if nom:
            groupes[nom].append(s)
    nums = set()
    for nom, votes in groupes.items():
        votes.sort(key=lambda s: ((s.get("dateScrutin") or ""), str(s.get("numero"))))
        nums.add(str(votes[-1]["numero"]))
    return nums


def main():
    mode_affiches = "--affiches" in sys.argv
    deja = {}
    if os.path.exists(F_NOTICES):
        deja = json.load(open(F_NOTICES, encoding="utf-8"))
    cibles = affiches() if mode_affiches else None

    a_faire = []
    for ligne in open(F_DISP, encoding="utf-8"):
        d = json.loads(ligne)
        num = str(d.get("numero"))
        if num in deja or not d.get("dispositif"):
            continue
        if cibles is not None and num not in cibles:
            continue
        a_faire.append((num, html.unescape(d["dispositif"]), d.get("titre") or ""))

    print(f"  {len(a_faire)} scrutins à rédiger"
          + (" (affichés seulement)" if mode_affiches else ""))

    with ThreadPoolExecutor(max_workers=8) as ex:
        for num, resume in ex.map(appel, a_faire):
            if resume is not None:
                deja[num] = resume
    json.dump(deja, open(F_NOTICES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  {sum(1 for v in deja.values() if v)} notices par scrutin disponibles")
    for num, r in list(deja.items())[:3]:
        if r:
            print(f"   · {num} → {r[:110]}")


if __name__ == "__main__":
    main()
