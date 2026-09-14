#!/usr/bin/env python3
"""Textes rédigés de l'observatoire : journal des mises à jour et section « À lire avant de citer un chiffre ».

Séparé de generate.py à dessein : c'est la partie éditoriale. Elle lit content/observatoire.json et
n'invente aucun chiffre — les chiffres lui sont étrangers, il ne fait que les entourer de texte.
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
CHEMIN = os.path.join(BASE, "content", "observatoire.json")

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]


def frd(iso):
    """2026-09-14 -> « 14 septembre 2026 »."""
    try:
        y, m, j = iso.split("-")
        return f"{int(j)} {MOIS[int(m) - 1]} {y}"
    except Exception:
        return iso


def charge():
    try:
        with open(CHEMIN, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:            # éditorial : son absence ne doit pas casser la page
        print(f"contenu éditorial illisible ({e}) : les pages se génèrent sans lui")
        return {}


CONTENU = charge()


def _sub(texte, valeurs=None):
    """Remplace les jetons {{nom}} d'un texte rédigé par les valeurs du jour.

    Un jeton sans valeur est retiré : mieux vaut une phrase sans exemple qu'une phrase avec
    « {{tete_nom}} » écrit en clair.
    """
    if isinstance(texte, list):
        return [_sub(x, valeurs) for x in texte]
    if not isinstance(texte, str):
        return texte
    for cle, val in (valeurs or {}).items():
        texte = texte.replace("{{" + cle + "}}", str(val))
    if "{{" in texte:
        import re as _re
        texte = _re.sub(r"\{\{[a-z_]+\}\}", "—", texte)
    return texte


def _entree(e, valeurs=None):
    return (f'<div class="maj"><div class="maj-t"><span class="maj-n">{e["nature"]}</span>'
            f'<strong>{e["titre"]}</strong>'
            f'<span class="muted small" style="margin-left:auto">{frd(e["date"])}</span></div>'
            f'<p class="small muted" style="margin:6px 0 0">{_sub(e["texte"], valeurs)}</p></div>')


def _corps(limite=None, valeurs=None):
    """Entrées du journal, éventuellement tronquées, plus le reste à signaler."""
    entrees = CONTENU.get("changelog") or []
    vues = entrees[:limite] if limite else entrees
    return "".join(_entree(e, valeurs) for e in vues), len(entrees) - len(vues)


def changelog_bloc(limite=None, titre="Journal des mises à jour", note=None, valeurs=None):
    """Le journal. `limite` en garde les N plus récentes (résumé de la page d'accueil)."""
    entrees = CONTENU.get("changelog") or []
    if not entrees:
        return ""
    corps, reste = _corps(limite, valeurs)
    suite = ""
    if reste:
        suite = (f'<p class="small muted" style="margin:12px 0 0">Les {reste} mises à jour plus '
                 f'anciennes figurent dans le journal complet, sur la page '
                 f'<a href="/observatoire/sondages/#a-lire">Agrégation</a>.</p>')
    defaut = ("Chaque changement de chiffre, de texte ou de présentation est daté ici. Aucun chiffre "
              "ne change sans une ligne dans ce journal.")
    return (f'<section id="changelog" class="card">\n  <h2>{titre}</h2>\n'
            f'  <p class="small muted">{note or defaut}</p>\n  {corps}\n  {suite}\n</section>')


def a_lire_bloc(valeurs=None):
    """Section détaillée : citer correctement, les pièges, les sources, le cadre légal."""
    c = CONTENU.get("a_lire") or {}
    if not c:
        return ""

    def liste(titre, elements):
        items = "".join(f"<li>{_sub(x, valeurs)}</li>" for x in elements or [])
        return f'<h3 style="margin-top:22px">{titre}</h3><ul class="tight small">{items}</ul>'

    return (f'<section id="a-lire" class="card">\n  <h2>{c["titre"]}</h2>\n'
            f'  <p class="lede" style="font-size:1rem">{_sub(c["chapo"], valeurs)}</p>\n'
            f'  {liste(c["regles_titre"], c["regles"])}\n'
            f'  {liste(c["pieges_titre"], c["pieges"])}\n'
            f'  {liste(c["sources_titre"], c["sources"])}\n'
            f'  {liste(c["legal_titre"], c["legal"])}\n'
            f'  <h3 style="margin-top:26px">Journal des mises à jour</h3>\n'
            f'  <p class="small muted">Chaque changement de chiffre, de texte ou de présentation est '
            f'daté. Aucun chiffre ne change sans une ligne ici.</p>\n'
            f'  {_corps(None, valeurs)[0]}\n'
            f'  <div class="note-legale small" style="margin-top:22px">\n'
            f'    <p style="margin:0">{c["contact"]}</p>\n  </div>\n</section>')


if __name__ == "__main__":
    n = len(CONTENU.get("changelog") or [])
    print(f"contenu : {n} entrées de journal, section « à lire » "
          f"{'présente' if CONTENU.get('a_lire') else 'ABSENTE'}")
    print(f"  -> {CHEMIN}")
