#!/usr/bin/env python3
"""Textes rédigés de l'observatoire : journal des mises à jour et section « À lire avant de citer un chiffre ».

Séparé de generate.py à dessein : c'est la partie éditoriale. Elle lit content/observatoire.json
et content/observatoire.en.json, et n'invente aucun chiffre — les chiffres lui sont étrangers, il
ne fait que les entourer de texte.

Deux langues, un seul schéma : les deux fichiers portent exactement les mêmes clés, et le
français fait foi si l'anglais manque. Les rares phrases de service (mentions de renvoi,
compteurs) sont écrites ici en dur, dans les deux langues, avec un `m()` local.
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
CHEMINS = {
    "fr": os.path.join(BASE, "content", "observatoire.json"),
    "en": os.path.join(BASE, "content", "observatoire.en.json"),
}

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]
MOIS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"]


def frd(iso, lang="fr"):
    """2026-09-14 -> « 14 septembre 2026 » (ou « 14 September 2026 » en anglais)."""
    try:
        y, m, j = iso.split("-")
        mois = MOIS_EN if lang == "en" else MOIS
        return f"{int(j)} {mois[int(m) - 1]} {y}"
    except Exception:
        return iso


def charge(lang="fr"):
    """Charge le contenu éditorial de la langue demandée, avec repli sur le français."""
    chemin = CHEMINS.get(lang) or CHEMINS["fr"]
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:            # éditorial : son absence ne doit pas casser la page
        if lang != "fr":
            return charge("fr")
        print(f"contenu éditorial illisible ({e}) : les pages se génèrent sans lui")
        return {}


_CONTENUS = {}


def contenu(lang="fr"):
    """Contenu éditorial mémorisé par langue (le fichier est relu une fois par processus)."""
    if lang not in _CONTENUS:
        _CONTENUS[lang] = charge(lang)
    return _CONTENUS[lang]


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


def _entree(e, valeurs=None, lang="fr"):
    return (f'<div class="maj"><div class="maj-t"><span class="maj-n">{e["nature"]}</span>'
            f'<strong>{e["titre"]}</strong>'
            f'<span class="muted small" style="margin-left:auto;padding-left:1em">{frd(e["date"], lang)}</span></div>'
            f'<p class="small muted" style="margin:6px 0 0">{_sub(e["texte"], valeurs)}</p></div>')


def _corps(limite=None, valeurs=None, lang="fr"):
    """Entrées du journal, éventuellement tronquées, plus le reste à signaler.

    L'auteur (17/09/2026) : le journal affiché sur le site ne porte que les mises à
    jour de chiffres — intégration de nouvelles données (sondages, scrutins…). Les
    entrées éditoriales (présentation, texte, correction, nouveauté, sources,
    données) restent dans le JSON et le CHANGELOG, sans être affichées.
    """
    entrees = [e for e in (contenu(lang).get("changelog") or [])
               if e.get("nature") == "chiffres"]
    vues = entrees[:limite] if limite else entrees
    return "".join(_entree(e, valeurs, lang) for e in vues), len(entrees) - len(vues)


def changelog_bloc(limite=None, titre=None, note=None, valeurs=None, lang="fr"):
    """Le journal. `limite` en garde les N plus récentes (résumé de la page d'accueil)."""
    def m(fr_txt, en_txt):
        return en_txt if lang == "en" else fr_txt

    if not (contenu(lang).get("changelog") or []):
        return ""
    corps, reste = _corps(limite, valeurs, lang)
    if not corps:
        return ""
    suite = ""
    if reste:
        base = "/observatoire/en/sondages/" if lang == "en" else "/observatoire/sondages/"
        suite = (f'<p class="small muted" style="margin:12px 0 0">'
                 f'{m(f"Les {reste} mises à jour plus anciennes figurent dans le journal complet, sur la page", f"The {reste} older updates are in the full log, on the")} '
                 f'<a href="{base}#a-lire">{m("Agrégation", "Aggregate")}</a>.</p>')
    defaut = m(
        "Les chiffres publiés évoluent à chaque intégration de nouvelles données — "
        "sondages, scrutins de l'Assemblée. Chaque mise à jour est datée ici : aucun "
        "chiffre ne change sans une ligne dans ce journal.",
        "The published figures change with every intake of new data — polls, votes in the "
        "National Assembly. Every update is dated here: no figure changes without a line in "
        "this log.")
    titre = titre or m("Journal des mises à jour", "Update log")
    return (f'<section id="changelog" class="card">\n  <h2>{titre}</h2>\n'
            f'  <p class="small muted">{note or defaut}</p>\n  {corps}\n  {suite}\n</section>')


def a_lire_bloc(valeurs=None, lang="fr"):
    """Section détaillée : citer correctement, les pièges, les sources, le cadre légal."""
    def m(fr_txt, en_txt):
        return en_txt if lang == "en" else fr_txt

    c = contenu(lang).get("a_lire") or {}
    if not c:
        return ""

    def liste(titre, elements):
        items = "".join(f"<li>{_sub(x, valeurs)}</li>" for x in elements or [])
        return f'<h3 style="margin-top:22px">{titre}</h3><ul class="tight small">{items}</ul>'

    corps_chiffres = _corps(None, valeurs, lang)[0]
    if not corps_chiffres:
        corps_chiffres = m(
            '<p class="small muted">Aucune mise à jour de chiffres pour le moment. Le journal '
            'se remplit à chaque intégration de nouvelles données.</p>',
            '<p class="small muted">No figure updates yet. The log fills up with every intake of '
            'new data.</p>')
    note_maj = m(
        "Les chiffres publiés évoluent à chaque intégration de nouvelles données — sondages, "
        "scrutins de l&apos;Assemblée. Chaque mise à jour est datée ici : aucun chiffre ne change "
        "sans une ligne.",
        "The published figures change with every intake of new data — polls, votes in the "
        "National Assembly. Every update is dated here: no figure changes without a line.")
    return (f'<section id="a-lire" class="card">\n  <h2>{c["titre"]}</h2>\n'
            f'  <p class="lede" style="font-size:1rem">{_sub(c["chapo"], valeurs)}</p>\n'
            f'  {liste(c["regles_titre"], c["regles"])}\n'
            f'  {liste(c["pieges_titre"], c["pieges"])}\n'
            f'  {liste(c.get("sources_titre", ""), c.get("sources"))}\n'
            f'  {liste(c.get("legal_titre", ""), c.get("legal"))}\n'
            f'  <h3 style="margin-top:26px">{m("Mises à jour des chiffres", "Figure updates")}</h3>\n'
            f'  <p class="small muted" style="max-width:none">{note_maj}</p>\n'
            f'  {corps_chiffres}\n'
            f'  <div class="note-legale small" style="margin-top:22px">\n'
            f'    <p style="margin:0">{c.get("contact", "")}</p>\n  </div>\n</section>')


if __name__ == "__main__":
    for langue in ("fr", "en"):
        c = contenu(langue)
        n = len(c.get("changelog") or [])
        a_lire = "présente" if c.get("a_lire") else "ABSENTE"
        print(f"contenu [{langue}] : {n} entrées de journal, section « à lire » {a_lire}")
        print(f"  -> {CHEMINS[langue]}")
