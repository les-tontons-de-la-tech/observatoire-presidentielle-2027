#!/usr/bin/env python3
"""Grille de classement de la veille législative — 13 thèmes, 62 sujets.

Règle de rédaction de cette grille : un motif doit désigner le sujet, pas effleurer le
vocabulaire juridique courant. La première version contenait « étranger », « commune »,
« liberté », « prix » — « à l'étranger » apparaît dans 81 % des textes de loi et ne
désigne rien. Les motifs ci-dessous sont des expressions du domaine, et les rares mots
simples retenus (glyphosate, smic, rgpd, hlm, parcoursup, oqtf) ne s'emploient que là.

Les textes sont normalisés par construire.norm() : minuscules, sans accents. Les motifs
sont donc écrits en ASCII, et « etranger » y couvre « étranger ».
"""
import re

GRILLE = {
    "Numérique": {
        "Intelligence artificielle": r"intelligence artificielle|systemes? d'ia|\bia generative\b|apprentissage automatique|algorithme|modeles? d'intelligence",
        "Données et vie privée": r"donnees numeriques|flux de donnees|producteurs? de donnees|donnees personnelles|protection des donnees|\brgpd\b|\bcnil\b|traitement de donnees|identite numerique|violation de donnees|fichiers? de donnees personnelles",
        "Plateformes et réseaux sociaux": r"reseaux sociaux|plateformes? en ligne|moderation des contenus|contenus illicites|influenceurs|services? numeriques|places? de marche numeriques",
        "Cybersécurité": r"cybersecurite|cyberattaques?|rancongiciels?|\bnis2\b|\banssi\b|securite des systemes d'information|vulnerabilites? informatiques?|certificats? de cybersecurite",
        "Télécoms et souveraineté": r"telecommunications?|frequences? radioelectriques|\b5g\b|\b6g\b|fibre optique|hebergement de donnees|informatique en nuage|souverainete numerique|operateurs? de reseau",
    },
    "Santé": {
        "Hôpital et soignants": r"toilettes?|hopitaux?|hopital public|soignants?|soins psychiatriques|psychiatri\w*|infirmiers?|medecins?|urgences? hospitalieres?|permanence des soins|deserts? medicaux?|praticiens? hospitaliers?",
        "Assurance maladie et remboursements": r"assurance maladie|ticket moderateur|securite sociale|remboursement des soins|mutuelles?|affections? de longue duree|aide medicale d'etat|franchises? medicales?",
        "Médicaments et produits de santé": r"medicaments?|pharmaciens?|pharmacies?|vaccins?|dispositifs? medicaux?|medicaments? generiques?|prix du medicament|agence nationale de securite du medicament",
        "Handicap et autonomie": r"handicap|mdph|allocation aux adultes handicapes|aidants?|perte d'autonomie|maisons? departementales?|accessibilite aux personnes handicapees|grand age",
        "Prévention et santé publique": r"maladies? vectorielles?|moustiques?|epidemies?|sante publique|depistage|tabac|alcool|obesite|sante mentale|vaccination|cancers?|education a la sante",
    },
    "Justice": {
        "Procédure pénale et peines": r"procedure penale|peines?|emprisonnement|recidive|casier judiciaire|detention provisoire|comparution immediate|code de procedure penale",
        "Prisons et exécution des peines": r"prisons?|detenus?|administration penitentiaire|surpopulation carcerale|liberation conditionnelle|milieu ouvert|surveillance electronique|maisons? d'arret",
        "Droit civil et familles": r"code civil|divorce|successions?|filiation|autorite parentale|tutelle|curatelle|etat civil",
        "Institutions judiciaires": r"magistrats?|tribunaux? judiciaires?|cours? d'appel|conseil superieur de la magistrature|juridictions?|cour de cassation|conseil d'etat|office du juge",
        "Victimes et réparation": r"victimes?|indemnisation des victimes|partie civile|fonds d'indemnisation|reparation du prejudice|protection des victimes",
    },
    "Économie": {
        "Entreprises et compétitivité": r"domiciliation|competitivite|pme|tpe|artisans?|reindustrialisation|simplification administrative|chambres? de commerce|statut de l'entrepreneur|entreprises? industrielles?",
        "Consommation et concurrence": r"consommateurs?|autorite de la concurrence|pratiques commerciales|clauses? abusives?|droit de la consommation|vente en ligne",
        "Finances publiques et budget": r"lois? de finances|budget de l'etat|deficit public|dette publique|programmation des finances publiques|cour des comptes|depenses? publiques?|comptes? de la nation",
        "Banque et assurance": r"mutualisation des risques|risques? majeurs|banques?|assurances?|credit immobilier|marches? financiers?|autorite de controle prudentiel|fonds de garantie des depots|services? bancaires?",
        "Emploi et activité économique": r"activite economique|investissements?|exportations?|aides? publiques? aux entreprises|zones? franches?|attractivite economique",
    },
    "Environnement": {
        "Climat et adaptation": r"changement climatique|adaptation au changement climatique|trajectoire bas carbone|canicule|secheresse|strategie nationale bas-carbone|empreinte carbone",
        "Énergie et nucléaire": r"energies?|nucleaire|eolien|photovoltaique|energies? renouvelables?|electricite|hydrogene|gaz renouvelable|mix energetique|parcs? eoliens?",
        "Biodiversité et eau": r"biodiversite|ressource en eau|zones? humides?|especes? protegees?|cours d'eau|pollution de l'eau|agences? de l'eau|protection de la nature",
        "Déchets et pollution": r"dechets|recyclage|economie circulaire|pollution de l'air|pesticides?|amiante|plastique|consignes?|pollutions?",
        "Urbanisme et artificialisation": r"artificialisation|zan|urbanisme|amenagement du territoire|foncier|plans? locaux? d'urbanisme|documents? d'urbanisme",
    },
    "Démocratie": {
        "Institutions et Constitution": r"revision constitutionnelle|constitution|referendum|article 49|assemblee nationale|senat|conseil constitutionnel|reglement de l'assemblee|loi organique",
        "Élections et mandats": r"elections?|mode de scrutin|mandats? electoraux?|ineligibilite|parrainages?|cumul des mandats|circonscriptions? electorales?|candidatures?",
        "Transparence et probité": r"transparence de la vie publique|hatvp|declarations? d'interets?|conflits? d'interets?|lobbying|probite|corruption|parquet national financier",
        "Décentralisation et collectivités": r"piscines? municipales?|dotations? aux collectivites|collectivites? territoriales?|decentralisation|communes?|departements?|regions?|intercommunalite|competences? des collectivites|code general des collectivites",
        "Libertés publiques": r"liberte d'expression|liberte de la presse|liberte de manifestation|liberte d'association|laicite|libertes? publiques?|etat d'urgence",
    },
    "Éducation": {
        "École et programmes": r"ecoles?|programmes? scolaires?|enseignants?|professeurs? des ecoles?|baccalaureat|brevet|apprentissage de la lecture|education nationale|directeurs? d'ecole",
        "Enseignement supérieur et recherche": r"enseignement superieur|universites?|recherche publique|doctorat|parcoursup|grandes ecoles|etudiants?|cnrs",
        "Vie scolaire et laïcité": r"vie scolaire|harcelement scolaire|restauration scolaire|cantine|laicite|violence scolaire|assistants? d'education",
        "Formation et apprentissage": r"apprentissage|formation professionnelle|alternance|apprentis|centres? de formation d'apprentis|compte personnel de formation|reconversion professionnelle",
    },
    "Sécurité": {
        "Police et gendarmerie": r"amendes? de police|police municipale|police nationale|gendarmerie nationale|forces? de l'ordre|securite publique|armement des policiers|commissariats?|brigades? de gendarmerie",
        "Terrorisme et renseignement": r"terrorisme|renseignement|radicalisation|attentats?|fichiers? de renseignement|droit de la securite|lutte contre le terrorisme",
        "Criminalité organisée": r"criminalite organisee|trafic de stupefiants|stupefiants?|blanchiment|bandes? organisees?|cybercriminalite|traite des etres humains|points? de deal",
        "Immigration et asile": r"immigration|droit d'asile|titre de sejour|regroupement familial|obligation de quitter le territoire|\boqtf\b|frontieres?|\\bvisas?\\b|sejour des etrangers|carte de sejour",
        "Vidéosurveillance et sécurité privée": r"videosurveillance|videoprotection|securite privee|alarmes?|cameras? de surveillance|surveillance des espaces publics",
    },
    "Travail": {
        "Droit du travail et contrats": r"code du travail|contrats? de travail|\bcdd\b|\bcdi\b|licenciement|preavis|temps de travail|teletravail|conventions? collectives?",
        "Salaires et pouvoir d'achat": r"\bsmic\b|salaire minimum|pouvoir d'achat|interessement|partage de la valeur|heures? supplementaires?|negociations? salariales?",
        "Retraites": r"retraites?|pensions?|regimes? de retraite|age legal de depart|carrieres? longues?|reversion|agirc-arrco|minimum contributif",
        "Dialogue social et syndicats": r"syndicats?|negociation collective|representativite syndicale|droit de greve|prud'hommes|dialogue social|comites? sociaux? et economiques?",
        "Fonction publique": r"fonction publique|fonctionnaires?|agents? publics?|statut general des fonctionnaires|contractuels?|remuneration des agents publics",
    },
    "Logement": {
        "Location et loyers": r"loyers?|baux?|locataires?|encadrement des loyers|expulsions?|impayes?|rapports? locatifs?|logements? locatifs?",
        "Construction et urbanisme": r"construction|permis de construire|logement social|\bhlm\b|renovation energetique|batiment|maitres? d'ouvrage|normes? de construction",
        "Habitat indigne et hébergement": r"habitat indigne|logements? insalubres?|hebergement d'urgence|sans-abri|marchands? de sommeil|droit au logement opposable",
        "Propriété et copropriété": r"proprietaires?|coproprietes?|charges de copropriete|syndics? de copropriete|plus-values? immobilieres?",
    },
    "Famille": {
        "Protection de l'enfance": r"protection de l'enfance|aide sociale a l'enfance|enfants? places?|droit de visite|assistance educative|enfance en danger",
        "Mineurs et responsabilité": r"mineurs?|responsabilite penale des mineurs|ordonnance de 1945|majorite|tribunaux? pour enfants|protection des mineurs",
        "Violences intrafamiliales": r"violences? conjugales?|violences? intrafamiliales?|feminicides?|ordonnances? de protection|eloignement|telephone grave danger",
        "Couple, filiation, adoption": r"mariage|\bpacs\b|divorce|filiation|adoption|\bpma\b|nom de famille",
        "Prestations familiales": r"prestations? familiales?|\bcaf\b|allocations? familiales?|garde d'enfants?|creches?|conge parental|complement familial",
    },
    "Agriculture": {
        "Filières et revenus agricoles": r"agriculteurs?|exploitations? agricoles?|\bpac\b|crise agricole|installations? d'agriculteurs?|cotisations? agricoles?|revenus? agricoles?",
        "Alimentation et qualité": r"alimentation|qualite des produits|etiquetage|\baop\b|\bigp\b|nutriscore|souverainete alimentaire|securite alimentaire",
        "Pêche et élevage": r"peche maritime|elevage|eleveurs?|aquaculture|abattage|bien-etre animal|filiere peche",
        "Phytosanitaires et santé animale": r"pesticides?|phytosanitaires?|glyphosate|acetamipride|sante animale|antibiotiques?|produits phytopharmaceutiques",
        "Forêt et ruralité": r"forets?|sylviculture|zones? rurales?|chasse|viticulture|communes? rurales?|mondes? ruraux?",
    },
    "Fiscalité": {
        "Impôts des ménages": r"impot sur le revenu|\bcsg\b|\bcrds\b|quotient familial|declaration de revenus|prelevement forfaitaire|frais reels",
        "Fiscalité des entreprises": r"impot sur les societes|\bcvae\b|contribution economique territoriale|taxe sur les transactions|credit d'impot recherche|amortissement",
        "Taxes sectorielles": r"\btva\b|accises?|taxe sur les billets d'avion|malus|redevances?|taxe fonciere|taxe d'habitation|taxes? affectees?",
        "Niches et exonérations": r"niches? fiscales?|exonerations?|abattements?|defiscalisation|reduction d'impot|depenses? fiscales?",
    },
}

# Commission saisie → thème principal (un seul : une commission comme « développement
# durable » désignait à elle seule trois thèmes dans la première version).
COMMISSION_THEME = {
    r"lois constitutionnelles": "Démocratie",
    r"finances": "Économie",
    r"affaires sociales": "Santé",
    r"affaires culturelles": "Éducation",
    r"affaires economiques": "Économie",
    r"developpement durable": "Environnement",
    r"defense": "Sécurité",
    r"affaires etrangeres": "Démocratie",
    r"production et des echanges": "Agriculture",
}


def sujets_valides():
    n = 0
    for theme, grille in GRILLE.items():
        for sujet, pat in grille.items():
            re.compile(pat)          # échoue tôt si une expression est invalide
            n += 1
    return len(GRILLE), n


if __name__ == "__main__":
    t, s = sujets_valides()
    print(f"  grille valide : {t} thèmes, {s} sujets")


# Vocabulaire de titre — utilisé UNIQUEMENT quand la grille stricte ne rend rien, et
# seulement sur un intitulé de texte. Dans un titre de loi, « logement », « agricole »
# ou « aide à mourir » désignent le sujet ; dans un corps de 8 000 caractères, ces mêmes
# mots ne désignent plus rien. C'est toute la différence entre les deux couches.
TITRE = {
    "Numérique": r"numerique|internet|donnees|plateformes?|intelligence artificielle|cyber|algorithme|telecom|reseau(x)? sociaux",
    "Santé": r"sante|maladie|mourir|soins|medical|medecin|hopital|psychiatr|patients?|handicap|vaccin|medicament|pharmac",
    "Justice": r"justice|penal|penitentiaire|prisons?|juges?|tribunaux?|magistrat|victimes?|crimes?|delits?|civil|penalisation",
    "Économie": r"economi|entreprises?|budget|finances?|banque|assurances?|concurrence|commerce|industri|artisan|investissement|comptes? publics",
    "Environnement": r"environnement|climat|energie|biodiversite|pollution|dechets|nucleaire|eolien|textile|mer|montagne|eau|foret",
    "Démocratie": r"collectivites?|communes?|departements?|regions?|elections?|constitution|parlement|institutions?|pouvoirs publics|democratie|scrutin|mandat",
    "Éducation": r"ecole|education|enseignement|universites?|recherche|etudiants?|formation|apprentissage|professeurs?",
    "Sécurité": r"securite|police|gendarmerie|terroris|criminalite|immigration|ordre public|fraudes?|delinquance|stupefiants",
    "Travail": r"travail|salaries?|emploi|retraites?|salaires?|apprentis?|syndicat|greve|fonction publique|professionnalisation",
    "Logement": r"logement|habitat|loyers?|immobili|urbanisme|construction|foncier|copropriete",
    "Famille": r"famille|enfants?|mineurs?|adoption|parental|naissance|divorce|filiation|creche",
    "Agriculture": r"agricol|agriculture|eleveurs?|peche|rural|alimentair|viti|sylviculture|chasse",
    "Fiscalité": r"fiscal|impots?|taxe|tva|cotisations?|exonerations?|niche",
}
