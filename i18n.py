#!/usr/bin/env python3
"""Libellés de l'observatoire, en français et en anglais.

Pourquoi ce module existe : les textes de l'observatoire ne sont pas des données,
ce sont des morceaux de phrases soudés aux gabarits (`generate.py` et les six scripts
qui produisent les autres pages). Une substitution après coup ne marche pas — les
balises `<strong>` et `<a>` coupent les phrases en plein milieu, et un dictionnaire
de nœuds de texte rend des fragments. La traduction doit donc se faire à la source,
au moment où le gabarit est écrit : une clé, deux langues.

Convention : `t(lang, "cle")` et `t(lang, "cle", n=3)` pour les formes fléchies.
Aucune clé ne contient de chiffre : les nombres, dates et pourcentages restent
interpolés par les gabarits, jamais recopiés ici.
"""

LANGUES = ("fr", "en")

TEXTES = {
    "fr": {
        # Navigation et chrome
        "nav_marque": "Présidentielle 2027",
        "nav_observatoire": "observatoire",
        "nav_agregation": "Agrégation",
        "nav_candidats": "Les candidats",
        "nav_backtest2022": "Rétro-test 2022",
        "nav_backtest2017": "Rétro-test 2017",
        "nav_workflow": "Workflow",
        "nav_lois": "Veille législative",
        "nav_evolution": "Évolution",
        "nav_comparaison": "Comparaison",
        "nav_methode": "Méthode",
        "nav_donnees": "Données",
        "nav_limites": "Limites",
        "nav_citer": "Citer un chiffre",
        "bouton_theme": "Changer le thème",

        # Accueil
        "accueil_surtitre": "Observatoire des sondages · présidentielle 2027",
        "accueil_titre": "Agrégation des sondages de la présidentielle 2027",
        "accueil_chapo": (
            "Nous compilons les sondages publiés par les instituts, un scénario de candidatures "
            "à la fois, avec la méthode écrite noir sur blanc et les limites affichées à côté "
            "des chiffres. Pas de probabilité de victoire : une lecture sourcée, datée, discutable."
        ),
        "accueil_cta_agregation": "Voir l'agrégation du jour",
        "accueil_cta_methode": "La méthode",

        # Blocs chiffrés
        "bloc_favori": "Favori du scénario retenu",
        "bloc_sondages_agg": "Sondages agrégés",
        "bloc_instituts": "Instituts",
        "bloc_derniere_enquete": "Dernière enquête",
        "bloc_sondages_source": "Sondages dans la source",
        "bloc_fenetre": "Fenêtre retenue",
        "bloc_scenario": "Scénario",

        # Tableaux
        "th_candidat": "Candidat",
        "th_intentions": "Intentions",
        "th_sondages": "Sondages",
        "th_huit_semaines": "8 semaines",
        "th_evolution": "Évolution",
        "th_mievvoter": "MieuxVoter",

        # Pied de page
        "pied_sources": "Sources ouvertes et citées, une par une.",
        "pied_methode": "Méthode versionnée, journal daté.",
        "pied_contact": "Contact",
    },
    "en": {
        # Navigation et chrome
        "nav_marque": "2027 presidential election",
        "nav_observatoire": "monitor",
        "nav_agregation": "Aggregate",
        "nav_candidats": "Candidates",
        "nav_backtest2022": "2022 backtest",
        "nav_backtest2017": "2017 backtest",
        "nav_workflow": "Workflow",
        "nav_lois": "Legislative watch",
        "nav_evolution": "Trend",
        "nav_comparaison": "Comparison",
        "nav_methode": "Method",
        "nav_donnees": "Data",
        "nav_limites": "Limits",
        "nav_citer": "Citing a figure",
        "bouton_theme": "Switch theme",

        # Accueil
        "accueil_surtitre": "Poll monitor · 2027 presidential election",
        "accueil_titre": "Poll aggregation for the 2027 presidential election",
        "accueil_chapo": (
            "We compile the polls published by the polling institutes, one candidate scenario "
            "at a time, with the method written out in full and the limits displayed next to the "
            "figures. No probability of victory: a sourced, dated, arguable reading."
        ),
        "accueil_cta_agregation": "See today's aggregate",
        "accueil_cta_methode": "The method",

        # Blocs chiffrés
        "bloc_favori": "Front-runner in the selected scenario",
        "bloc_sondages_agg": "Polls aggregated",
        "bloc_instituts": "Institutes",
        "bloc_derniere_enquete": "Latest poll",
        "bloc_sondages_source": "Polls in the source",
        "bloc_fenetre": "Reporting window",
        "bloc_scenario": "Scenario",

        # Tableaux
        "th_candidat": "Candidate",
        "th_intentions": "Voting intention",
        "th_sondages": "Polls",
        "th_huit_semaines": "8 weeks",
        "th_evolution": "Change",
        "th_mievvoter": "MieuxVoter",

        # Pied de page
        "pied_sources": "Open sources, cited one by one.",
        "pied_methode": "Versioned method, dated log.",
        "pied_contact": "Contact",
    },
}


def t(lang, cle, **champs):
    """Rend le libellé `cle` dans la langue demandée.

    Une clé absente lève une erreur immédiatement : mieux vaut un plantage au
    moment de la génération qu'une page anglaise avec un mot français au milieu.
    """
    if lang not in LANGUES:
        raise ValueError(f"langue inconnue : {lang!r} (attendu : {', '.join(LANGUES)})")
    table = TEXTES[lang]
    if cle not in table:
        raise KeyError(f"libellé absent pour {lang!r} : {cle!r}")
    texte = table[cle]
    return texte.format(**champs) if champs else texte


def manquants():
    """Clés présentes dans une langue et absentes dans l'autre (contrôle de parité)."""
    fr, en = set(TEXTES["fr"]), set(TEXTES["en"])
    return sorted(fr - en), sorted(en - fr)


if __name__ == "__main__":
    import sys

    fr_seul, en_seul = manquants()
    print(f"libellés : {len(TEXTES['fr'])} en français, {len(TEXTES['en'])} en anglais")
    if fr_seul or en_seul:
        print(f"  absents en anglais : {fr_seul}")
        print(f"  absents en français : {en_seul}")
        sys.exit(1)
    print("  parité des clés : OK")
    print("  exemple :", t("en", "accueil_titre"))
