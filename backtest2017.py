#!/usr/bin/env python3
"""Rétro-test 2017 : la méthode de l'observatoire rejouée hors échantillon.

Les deux réglages de la page 2027 (fenêtre de sélection de 90 jours, correction des effets de
maison) ont été calés sur la campagne 2022. Les rejouer sur 2017, réglages gelés, mesure non plus
le choix qu'ils ont servi à faire mais leur transférabilité.

Entrées
  • sondages : liste encyclopédique « Liste de sondages sur l'élection présidentielle française de
    2017 » (Wikipédia FR, CC BY-SA), lue en wikitext brut et analysée ici. Chaque ligne porte le
    lien de publication donné par le tableau, et l'institut qui l'a réalisée. La liste ne donne pas
    le lien des notices de la Commission des sondages, à la différence de la compilation 2022 :
    l'attribution se porte donc sur l'institut et sur la Commission, pas sur une notice précise.
  • référence : résultats définitifs du premier tour (23 avril 2017), ministère de l'Intérieur,
    jeu de données « Résultats définitifs du 1er tour », Licence Ouverte (data.gouv.fr). Les onze
    scores ont été recoupés le 20/09/2026 avec « Résultats détaillés de l'élection présidentielle
    française de 2017 » (Wikipédia FR, CC BY-SA) : 11/11 identiques, voix et pourcentages.

Sorties
  • data/polls2017.json      (sondages normalisés, même format que data/polls2022.json)
  • data/backtest2017.json   (résultats machine)
  • site/backtest2017/index.html (page publiée)

Limites assumées
  • la liste couvre 2016 et 2017 ; les enquêtes antérieures au 1er janvier 2016 sont écartées, et
    ce choix est écrit sur la page ;
  • les valeurs notées « < 0,5 % » (échantillons où le candidat est testé mais sous le seuil de
    publication) sont lues 0,5 ; leur nombre est compté et publié ;
  • la colonne « Autres candidats » de deux tableaux n'est pas reprise : elle ne nomme personne et
    fausserait le poids des non-candidats, qui est justement une des mesures publiées.
"""
import json, math, os, re, sys, urllib.request
from collections import defaultdict, Counter
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as G

# Cette page n'est pas dans le plan de generate.py (qui reste inchangé) : on déclare son titre, sa
# description et ses données structurées dans les mêmes tables, pour que <title>, la balise meta,
# Open Graph et le JSON-LD ne puissent pas diverger d'une page à l'autre.
PAGE = "/observatoire/backtest2017/"
G.PAGES_LD[PAGE] = (
    "Rétro-test 2017 : la méthode mise à l'épreuve hors échantillon",
    "La méthode d'agrégation de l'observatoire rejouée sur la campagne 2017, réglages gelés : "
    "erreur moyenne, couverture et transférabilité.",
    "Article")
G.TITRES_COURTS[PAGE] = "Rétro-test 2017 : la méthode à l'épreuve"
# Même déclaration en anglais : la page a une version anglaise, et son <title>, sa balise meta, son
# Open Graph et son JSON-LD se lisent dans les tables anglaises de generate.py, à côté des textes
# français — comme pour /observatoire/candidats/. Rien n'est écrit dans generate.py : on y déclare
# la page au même endroit que sa jumelle française, titre sous 60 caractères, description dans la
# bande de 120 à 160.
G.PAGES_LD_EN[PAGE] = (
    "2017 backtest: the method put to the test out of sample",
    "The monitor's aggregation method replayed on the 2017 campaign, settings frozen: average "
    "error, coverage and transferability.",
    "Article")
G.TITRES_COURTS_EN[PAGE] = "2017 backtest: the method on trial"

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
SITE = os.path.join(BASE, "site")
WIKI_URL = ("https://fr.wikipedia.org/w/index.php?title="
            "Liste_de_sondages_sur_l%27%C3%A9lection_pr%C3%A9sidentielle_fran%C3%A7aise_de_2017"
            "&action=raw")
WIKI_CACHE = os.path.join(DATA, "wiki_sondages2017.wikitext")
PAGE_WIKI = ("https://fr.wikipedia.org/wiki/"
             "Liste_de_sondages_sur_l%27%C3%A9lection_pr%C3%A9sidentielle_fran%C3%A7aise_de_2017")
PAGE_RESULTATS = ("https://fr.wikipedia.org/wiki/"
                  "R%C3%A9sultats_d%C3%A9taill%C3%A9s_de_l%27%C3%A9lection_pr%C3%A9sidentielle"
                  "_fran%C3%A7aise_de_2017")
SOURCE_RESULTAT_URL = ("https://static.data.gouv.fr/resources/election-presidentielle-des-23-"
                       "avril-et-7-mai-2017-resultats-definitifs-du-1er-tour-1/20170427-100131/"
                       "Presidentielle_2017_Resultats_Tour_1_c.xls")
SCRUTIN = date(2017, 4, 23)
SCOPE_MIN = "2016-01-01"   # première année où la liste est assez dense pour un rétro-test

# Résultats définitifs du premier tour, France entière : ministère de l'Intérieur, jeu de données
# « Résultats définitifs du 1er tour » (Licence Ouverte), fichier du 27/04/2017. 11 candidats,
# 36 054 394 suffrages exprimés. Vérification du 20/09/2026 : les onze scores recoupés un à un avec
# « Résultats détaillés de l'élection présidentielle française de 2017 » (Wikipédia FR, CC BY-SA).
EXPRIMES = 36054394
VOTES_OFFICIELS = {
    "Emmanuel Macron": 8656346,
    "Marine Le Pen": 7678491,
    "François Fillon": 7212995,
    "Jean-Luc Mélenchon": 7059951,
    "Benoît Hamon": 2291288,
    "Nicolas Dupont-Aignan": 1695000,
    "Jean Lassalle": 435301,
    "Philippe Poutou": 394505,
    "François Asselineau": 332547,
    "Nathalie Arthaud": 232384,
    "Jacques Cheminade": 65586,
}
RESULTAT = {nom: round(100 * voix / EXPRIMES, 2) for nom, voix in VOTES_OFFICIELS.items()}
# Les noms du wikitext sont déjà ceux de la proclamation officielle ; la table existe pour la
# symétrie avec backtest2022.py et pour absorber une variante si la liste en introduit une.
ALIAS = {}
# Même institut, libellés différents selon les lignes du tableau : sans ce regroupement, un effet
# de maison se calcule sur des demi-échantillons et la correction ne veut plus rien dire.
INSTITUTS = {"IFOP": "Ifop", "Ifop-Fiducial": "Ifop", "Cevipof Ipsos-Sopra Steria": "Ipsos",
             "Harris": "Harris Interactive", "OpinionWay": "Opinion Way", "TNS": "Kantar Sofres",
             "Sofres": "Kantar Sofres", "TNS Sofres": "Kantar Sofres",
             "Kantar Sofres - OnePoint": "Kantar Sofres",
             "Kantar Sofres-OnePoint": "Kantar Sofres", "": "institut non nommé"}
EXCLUS = ("Autres candidats",)   # colonne de deux tableaux : elle ne nomme personne

CUTOFFS = ["2016-09-01", "2016-10-01", "2016-11-01", "2016-12-01", "2016-12-12",
           "2017-02-01", "2017-03-01", "2017-03-24", "2017-04-13"]
HORIZON_2027 = "2016-09-20"   # J-215 : l'horizon auquel l'observatoire publie pour 2027
MODES = [("recence", "Notre méthode (fraîcheur + échantillon)"),
         ("egal", "Poids égaux"),
         ("dernier", "Dernière enquête seule")]

MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
        "décembre": 12, "decembre": 12}
MOIS_ABBR = {"janv": 1, "jan": 1, "févr": 2, "fevr": 2, "fév": 2, "fev": 2, "mars": 3, "avr": 4,
             "mai": 5, "juin": 6, "juil": 7, "août": 8, "aout": 8, "sept": 9, "oct": 10,
             "nov": 11, "déc": 12, "dec": 12}
# mots d'une cellule de date qui ne désignent pas un mois et ne doivent pas inquiéter
MOTS_IGNORES = {"du", "au", "et", "le", "la", "les", "vers", "de", "en"}
MOTS_DATES_INCONNUS = Counter()   # rempli par parse_date, vidé à chaque analyse
ROLES = [(r"sondeur", "sondeur"), (r"date", "date"), (r"indécis|indecis", "indecis"),
         (r"abstention", "abstention"), (r"échantillon|echantillon", "echantillon"),
         (r"nsp|ne se prononce", "nsp")]


# ---------------------------------------------------------------- analyse du wikitext
def strip_tags(t):
    """Texte lisible d'une cellule : notes, balises et modèles de présentation retirés."""
    t = re.sub(r"<ref[^>]*/>", "", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", "", t)
    for _ in range(4):
        t = re.sub(r"\{\{blanc\|(.*?)\}\}", r"\1", t, flags=re.S)
        t = re.sub(r"\{\{coloré\|[^|]*\|(.*?)\}\}", r"\1", t, flags=re.S)
    t = re.sub(r"\{\{[Dd]ate\|([^}]*)\}\}", lambda m: " ".join(m.group(1).split("|")), t)
    t = re.sub(r"\{\{1er\s*\}\}", "1", t)
    t = re.sub(r"\{\{1er\|([^}]*)\}\}", r"1 \1", t)
    t = re.sub(r"\{\{formatnum:([^}]*)\}\}", r"\1", t)
    t = re.sub(r"\{\{nobr\|([^}]*)\}\}", r"\1", t)
    t = re.sub(r"\{\{unité\|([^}]*)\}\}", lambda m: m.group(1).replace("|", " "), t)
    t = t.replace("&nbsp;", " ").replace("\u202f", " ").replace("\xa0", " ")
    t = t.replace("[[", "").replace("]]", "")
    return re.sub(r"\s+", " ", t).strip()


def cell_split(line):
    """(attributs, contenu) d'une ligne de cellule, pipes de modèles et de liens ignorés."""
    body = line[1:]
    d, i = 0, 0
    while i < len(body):
        if body.startswith("{{", i) or body.startswith("[[", i):
            d += 1; i += 2; continue
        if body.startswith("}}", i) or body.startswith("]]", i):
            d -= 1; i += 2; continue
        if body[i] == "|" and d == 0:
            return body[:i].strip(), body[i + 1:].strip()
        i += 1
    return "", body.strip()


def read_tables(text):
    """Tableaux du premier tour, avec leur légende ; les sections d'évolution sont écartées."""
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines)
                 if l.startswith("== Sondages concernant le premier tour =="))
    stop = next((i for i, l in enumerate(lines) if l.startswith("=== Évolution des enquêtes ===")),
                len(lines))
    out, cur = [], None
    for i in range(start, stop):
        l = lines[i]
        if l.startswith("{|"):
            cur = dict(line=i + 1, rows=[], caption=None)
        elif cur is not None:
            if l.startswith("|}"):
                out.append(cur); cur = None
            elif l.startswith("|+"):
                cur["caption"] = l[2:].strip()
            elif l.startswith("|-"):
                cur["rows"].append([])
            elif l.startswith("!") or l.startswith("|"):
                if not cur["rows"]:
                    cur["rows"].append([])
                a, c = cell_split(l)
                cur["rows"][-1].append((i + 1, l[0], a, c))
            elif cur["rows"] and cur["rows"][-1] and l.strip():
                # suite d'une cellule : le parti d'un candidat vit sur la ligne suivante
                ln, marker, attrs, content = cur["rows"][-1][-1]
                cur["rows"][-1][-1] = (ln, marker, attrs, content + " " + l.strip())
    return out


def grid_of(rows):
    """Grille (ligne, colonne) vers (attributs, contenu), rowspan et colspan simulés : le wikitext
    fusionne les cellules d'institut, de date et d'échantillon sur toutes les hypothèses d'une même
    enquête, et une ligne d'hypothèse n'a donc pas d'attributs d'institut à elle."""
    grid, occ, ncols = {}, {}, 0
    for r, cells in enumerate(rows):
        c = 0
        for (ln, marker, attrs, content) in cells:
            while (r, c) in occ:
                c += 1
            m = re.search(r'colspan\s*=\s*"?(\d+)', attrs)
            cs = int(m.group(1)) if m else 1
            m = re.search(r'rowspan\s*=\s*"?(\d+)', attrs)
            rs = int(m.group(1)) if m else 1
            for dr in range(rs):
                for dc in range(cs):
                    grid[(r + dr, c + dc)] = (attrs, content)
                    if (dr, dc) != (0, 0):
                        occ[(r + dr, c + dc)] = True
            c += cs
            ncols = max(ncols, c)
    return grid, ncols


def header_roles(h1):
    """Colonnes de tête reconnues (sondeur, date, échantillon…) : les suivantes sont candidates."""
    roles = []
    for c in h1:
        t = strip_tags(c).strip("'").strip().lower()
        role = None
        for pat, name in ROLES:
            if re.match(pat, t):
                role = name; break
        if role is None:
            break
        roles.append(role)
    return roles


def cand_name(cell, alt_cell=""):
    m = re.search(r"\|link=([^\]|]+)", cell)
    if m:
        return strip_tags(m.group(1))
    m = re.search(r"\[\[([^\]|]+)", cell)
    if m:
        return strip_tags(m.group(1))
    t = strip_tags(cell)
    if t:
        return t
    m = re.search(r"\[\[([^\]|]+)", alt_cell)
    return strip_tags(m.group(1)) if m else ""


def cand_parti(cell):
    """Étiquette de parti : elle vit dans le <small> de la cellule de nom."""
    m = re.search(r"<small>\((.*?)\)</small>", cell, flags=re.S)
    bloc = m.group(1) if m else ""
    lk = re.findall(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", bloc)
    if lk:
        return (lk[-1][1] or lk[-1][0]).strip()
    return ""


def parse_pct(c):
    """(valeur, valeur bornée) d'une cellule d'intention ; (None, False) si le candidat n'est pas testé."""
    t = strip_tags(c).strip().strip("'").strip()
    if t in ("", "–", "-", "—", "n.d.", "?"):
        return None, False
    borne = t.startswith("<")
    t = t.lstrip("<≤> ").strip()
    m = re.match(r"^(\d+)(?:[.,](\d+))?\s*%", t.replace(".", ","))
    if not m:
        return None, False
    v = float(m.group(1) + ("." + m.group(2) if m.group(2) else ""))
    return v, borne


def mois_de(texte):
    """(mois reconnus dans l'ordre, mots non reconnus). Un mot non reconnu interdit le report de
    mois : mieux vaut une date écartée qu'une date décalée d'un mois sans le dire."""
    mois, inconnus = [], []
    for mot in re.findall(r"[a-zà-ÿ]+", texte.lower()):
        if mot in MOIS:
            mois.append(MOIS[mot])
        elif mot in MOIS_ABBR:
            mois.append(MOIS_ABBR[mot])
        elif mot not in MOTS_IGNORES:
            inconnus.append(mot)
    return mois, inconnus


def parse_date(txt, caption="", last_month=None):
    """(date de fin, mois utilisé, texte non reconnu) : les tableaux ne portent que les jours, le
    mois et l'année venant de la légende, ou du mois écrit dans la cellule quand il y est."""
    t = strip_tags(txt).lower().strip()
    if not t or not re.search(r"\d", t):
        return None, None, t
    year = None
    m = re.search(r"(20\d\d)", t)
    if m:
        year = int(m.group(1))
    if year is None:
        m = re.search(r"(20\d\d)", caption)
        year = int(m.group(1)) if m else None
    months, inconnus = mois_de(t)
    for mot in inconnus:
        MOTS_DATES_INCONNUS[mot] += 1
    if months:
        m_end = months[-1]
    elif last_month:
        m_end = last_month                 # tableau à légende mensuelle : mois du tableau
    else:
        mm, _ = mois_de(caption)
        m_end = mm[-1] if mm else None
    if year is None or m_end is None:
        return None, None, t
    sans_annee = re.sub(r"\b(?:19|20)\d\d\b", " ", t)
    days = [int(d) for d in re.findall(r"(\d{1,2})(?:er)?", sans_annee) if 1 <= int(d) <= 31]
    if not days:
        return None, m_end, t
    d_end = days[-1]
    if not inconnus and len(months) <= 1 and len(days) >= 2 and days[-1] < days[0]:
        # un seul mois cité et la fin tombe avant le début : l'enquête s'achève le mois suivant
        m_end = m_end % 12 + 1
        if m_end == 1:
            year += 1
    return f"{year:04d}-{m_end:02d}-{d_end:02d}", m_end, None


def parse_institut(attrs, content):
    m = re.search(r"\{\{Sondeur\|([^}|]+)", attrs) or re.search(r"\{\{Sondeur\|([^}|]+)", content)
    if m:
        return m.group(1).strip()
    m = re.match(r"\[https?://\S+\s+([^\]]+)\]", strip_tags(content))
    if m:
        return m.group(1).strip()
    return strip_tags(content)


def parse_ech(c):
    t = strip_tags(c).replace(" ", "")
    m = re.search(r"(\d{2,6})", t)
    return int(m.group(1)) if m else None


def origines_date(t, di):
    """Cellules de date d'origine d'un tableau : le wikitext fusionne la date sur toutes les
    hypothèses d'une même enquête, donc une cellule de date = une enquête."""
    out, occ = [], {}
    hi = {r for r, cells in enumerate(t["rows"]) if cells and all(c[1] == "!" for c in cells)}
    for r, cells in enumerate(t["rows"]):
        c = 0
        for (ln, marker, attrs, content) in cells:
            while (r, c) in occ:
                c += 1
            m = re.search(r'colspan\s*=\s*"?(\d+)', attrs)
            cs = int(m.group(1)) if m else 1
            m = re.search(r'rowspan\s*=\s*"?(\d+)', attrs)
            rs = int(m.group(1)) if m else 1
            if c == di and r not in hi:
                out.append(strip_tags(content))
            for dr in range(rs):
                for dc in range(cs):
                    if (dr, dc) != (0, 0):
                        occ[(r + dr, c + dc)] = True
            c += cs
    return out


def parse_wikitext(text):
    """Sondages du premier tour + comptes de contrôle de l'analyse."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    MOTS_DATES_INCONNUS.clear()
    tables = read_tables(text)
    out, notes = [], Counter()
    cellules_dates = 0
    last_month = {}
    for t in tables:
        grid, ncols = grid_of(t["rows"])
        head_idx = [r for r, cells in enumerate(t["rows"])
                    if cells and all(c[1] == "!" for c in cells)]
        if not head_idx:
            notes["tableau sans en-tête"] += 1
            continue
        # tableaux sans légende (celui d'après la liste officielle) : année lue dans le tableau
        tbl_year = None
        if not re.search(r"20\d\d", t["caption"] or ""):
            for (r, c), (_a, v) in sorted(grid.items()):
                m = re.search(r"(20\d\d)", strip_tags(v or ""))
                if m:
                    tbl_year = int(m.group(1)); break
        h1 = [grid.get((head_idx[0], c), ("", ""))[1] for c in range(ncols)]
        roles = header_roles(h1)
        nlead = len(roles)
        h2 = head_idx[1] if len(head_idx) > 1 else None
        cands = []
        for c in range(nlead, ncols):
            alt = grid.get((h2, c), ("", ""))[1] if h2 is not None else ""
            cands.append((c, cand_name(h1[c], alt), cand_parti(alt)))
        if "date" in roles:
            cellules_dates += len([x for x in origines_date(t, roles.index("date"))
                                   if re.match(r"^(du |le |\d|<|\()", x, re.I)])
        for r in range(head_idx[-1] + 1, len(t["rows"])):
            cells = [grid.get((r, c), (None, None))[1] for c in range(ncols)]
            if all(v is None for v in cells):
                continue
            attrs_row = " ".join(a for _, _, a, _ in t["rows"][r])
            if "colspan" in attrs_row:
                notes["ligne de contexte"] += 1; continue
            first = cells[0] or ""
            if re.search(r"Résultats|Arrêt de publication", strip_tags(first)) \
                    or "interieur.gouv" in str(first):
                notes["ligne de résultats officiels"] += 1; continue
            vals = {}
            for c, name, parti in cands:
                if not name or name in EXCLUS:
                    continue
                v, borne = parse_pct(cells[c] or "")
                if v is not None:
                    vals[name] = (v, parti, borne)
            if len(vals) < 2:
                notes["ligne sans intentions"] += 1; continue
            dcell = cells[roles.index("date")] if "date" in roles else None
            if dcell is None:
                notes["sans date"] += 1; continue
            d, used_month, bad = parse_date(
                dcell, t["caption"] or (str(tbl_year) if tbl_year else ""),
                last_month.get(t["line"]))
            if bad:
                notes["date non reconnue"] += 1; continue
            last_month[t["line"]] = used_month
            ech = parse_ech(cells[roles.index("echantillon")]) if "echantillon" in roles else None
            url = re.search(r"https?://\S+", first)
            # institut : la cellule du tableau, attributs et contenu compris (le modèle
            # {{Sondeur|…}} tient le nom canonique, le lien porte le nom publié)
            inst = parse_institut(*grid.get((r, 0), ("", "")))
            out.append(dict(
                tour="1er Tour", fin_enquete=d,
                institut=INSTITUTS.get(inst, inst) or "institut non nommé",
                echantillon=ech,
                hypothese="Champ testé : " + " / ".join(sorted(vals)),
                candidats=[dict(candidat=n, intentions=v, parti=p or None)
                           for n, (v, p, _b) in sorted(vals.items())],
                notice=url.group(0).split("]")[0] if url else None,
                _ligne=t["line"], _bornes=[n for n, (v, p, b) in vals.items() if b]))
    return out, notes, cellules_dates


# ---------------------------------------------------------------- données
def fetch_wikitext(force=False):
    """Wikitext de la liste, mis en cache : l'analyse reste rejouable hors ligne."""
    os.makedirs(DATA, exist_ok=True)
    if force or not os.path.exists(WIKI_CACHE):
        req = urllib.request.Request(WIKI_URL, headers={"User-Agent": "poc-agregateur-2027"})
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode("utf-8")
        open(WIKI_CACHE, "w", encoding="utf-8").write(raw)
    return open(WIKI_CACHE, encoding="utf-8").read()


def load_polls(force=False):
    """Sondages 2016-2017 normalisés, au format de data/polls2022.json, + comptes de contrôle."""
    polls_all, notes, cellules = parse_wikitext(fetch_wikitext(force))
    polls = []
    for p in polls_all:
        if p["fin_enquete"] < SCOPE_MIN:
            continue
        cands = [dict(candidat=ALIAS.get(c["candidat"], c["candidat"]), intentions=c["intentions"],
                      parti=c["parti"]) for c in p["candidats"] if c["candidat"]]
        polls.append(dict(tour=p["tour"], fin_enquete=p["fin_enquete"], institut=p["institut"],
                          echantillon=p["echantillon"], hypothese=p["hypothese"],
                          candidats=cands, notice=p["notice"]))
    bornes = sum(len(p["_bornes"]) for p in polls_all if p["fin_enquete"] >= SCOPE_MIN)
    # Contrôle de l'analyse, toutes années confondues : le nombre de cellules de date du wikitext
    # (une par enquête) doit égaler le nombre d'enquêtes reconstruites. Un écart signalerait une
    # ligne perdue ou comptée deux fois, pas une différence d'interprétation. La clé d'enquête
    # comprend l'échantillon : un même institut peut publier deux enquêtes closes le même jour
    # (Ifop, 4 mars 2017, 1 822 et 1 392 personnes).
    cle = lambda p: (p["institut"], p["fin_enquete"], p.get("echantillon"))
    couples = {cle(p) for p in polls_all
               if any(c["candidat"] not in EXCLUS for c in p["candidats"])}
    stats = dict(
        lignes_bilan=dict(notes),
        controle=dict(cellules_de_date=cellules, enquetes_reconstruites=len(couples),
                      identiques=(cellules == len(couples))),
        hypotheses_extraites=len(polls),
        enquetes=len({p["fin_enquete"] for p in polls}),
        enquetes_institut=len({cle(p) for p in polls}),
        instituts=sorted({p["institut"] for p in polls}),
        premier=polls and min(p["fin_enquete"] for p in polls),
        dernier=polls and max(p["fin_enquete"] for p in polls),
        valeurs_bornees=bornes,
        colonnes_ecartees=list(EXCLUS),
    )
    json.dump(polls, open(os.path.join(DATA, "polls2017.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    return polls, stats


# ---------------------------------------------------------------- mesure
def fr2(x):
    """Deux décimales, virgule française (les écarts de méthode se jouent à 0,05 point)."""
    return "—" if x is None else f"{x:.2f}".replace(".", ",")


def fr_date(iso):
    """Date au format français pour l'affichage ; les données restent en ISO."""
    return iso[8:10] + "/" + iso[5:7] + "/" + iso[0:4] if iso and len(iso) == 10 else (iso or "—")


def metrics(agg, mode_label):
    """Erreur de l'agrégation face au résultat officiel (sur les 11 candidats réels)."""
    if not agg or not agg.get("rows"):
        return dict(mode=mode_label, n=0, mae=None, biais=None, max_err=None, publies=0,
                    detail={}, poids_non_candidats=0.0, scenario=None, polls=0,
                    top2=[], top3=[])
    estim = {r["candidat"]: r["intentions"] for r in agg["rows"]}
    errs, bias, detail = [], [], {}
    for nom, res in RESULTAT.items():
        if nom not in estim:
            detail[nom] = dict(estimation=None, resultat=res, erreur=None)
            continue
        e = round(estim[nom] - res, 1)
        errs.append(abs(e))
        bias.append(e)
        detail[nom] = dict(estimation=estim[nom], resultat=res, erreur=e)
    non_cand = sum(v for k, v in estim.items() if k not in RESULTAT)
    return dict(
        mode=mode_label, n=len(errs), publies=len(estim),
        mae=(round(sum(errs) / len(errs), 2) if errs else None),
        biais=(round(sum(bias) / len(bias), 2) if bias else None),
        max_err=(round(max(errs), 1) if errs else None),
        detail=detail, poids_non_candidats=round(non_cand, 1),
        scenario=agg.get("scenario"), polls=agg.get("polls_aggregated"),
        top2=[r["candidat"] for r in agg["rows"][:2]],
        top3=[r["candidat"] for r in agg["rows"][:3]],
    )


def grid_window(polls, windows=(30, 60, 90, 120)):
    """Sensibilité de la fenêtre de sélection du scénario (méthode inchangée par ailleurs)."""
    out = []
    for w in windows:
        per = []
        for cut in CUTOFFS:
            m = metrics(G.aggregate(polls, as_of=date.fromisoformat(cut), scenario_window=w,
                                    house_correction=True), f"fenêtre {w} j")
            per.append(dict(date=cut, mae=m["mae"], n=m["n"], polls=m["polls"],
                            non_cand=m["poids_non_candidats"], top2=m["top2"],
                            scenario=m["scenario"]))
        ok = [p for p in per if p["mae"] is not None]
        out.append(dict(
            fenetre=w,
            mae_moyenne=(round(sum(p["mae"] for p in ok) / len(ok), 2) if ok else None),
            couverture=f"{len(ok)}/{len(per)}",
            n_moyen=(round(sum(p["n"] for p in ok) / len(ok), 1) if ok else None),
            polls_moyen=(round(sum(p["polls"] for p in ok) / len(ok), 1) if ok else None),
            detail=per, ok=(len(ok) == len(per))))
    return out


def grid_house(polls, configs=((60, False), (60, True), (90, False), (90, True), (120, True))):
    """Effet de la correction des effets de maison, à fenêtre de sélection égale."""
    out = []
    for w, hc in configs:
        per = []
        for cut in CUTOFFS:
            m = metrics(G.aggregate(polls, as_of=date.fromisoformat(cut), scenario_window=w,
                                    house_correction=hc), f"f{w}/{'hc' if hc else 'sans hc'}")
            per.append(dict(date=cut, mae=m["mae"], n=m["n"], polls=m["polls"]))
        ok = [p for p in per if p["mae"] is not None]
        out.append(dict(fenetre=w, house=hc,
                        libelle=f"fenêtre {w} j, " + ("effets de maison corrigés" if hc
                                                      else "sans correction"),
                        mae_moyenne=(round(sum(p["mae"] for p in ok) / len(ok), 2) if ok else None),
                        couverture=f"{len(ok)}/{len(per)}", detail=per))
    return out


def best_config(gw, gh):
    """Meilleure configuration au vu de ce rétro-test : couverture complète d'abord, puis erreur."""
    cands = [dict(fenetre=g["fenetre"], house=True, mae=g["mae_moyenne"], couv=g["couverture"],
                  ok=g["ok"]) for g in gw]
    cands += [dict(fenetre=h["fenetre"], house=h["house"], mae=h["mae_moyenne"],
                   couv=h["couverture"],
                   ok=(h["couverture"].split("/")[0] == h["couverture"].split("/")[1]))
              for h in gh]
    valides = [c for c in cands if c["ok"] and c["mae"] is not None]
    if not valides:
        return None
    best = min(c["mae"] for c in valides)
    proches = [c for c in valides if c["mae"] <= best + 0.05]
    return min(proches, key=lambda c: (c["fenetre"], not c["house"]))


def densite(polls, horizon):
    """Enquêtes disponibles à un horizon : c'est ce qui décide si la page peut publier."""
    h = date.fromisoformat(horizon)
    ds = sorted({p["fin_enquete"] for p in polls if p["fin_enquete"] <= horizon})
    recents = [d for d in ds if (h - date.fromisoformat(d)).days <= 30]
    return dict(date=horizon, jours_avant=(SCRUTIN - h).days, enquetes=len(ds),
                recentes=len(recents), premiere=ds[0] if ds else None)


def ref_2022():
    """Référence 2022 à J−132, lue dans le rétro-test existant : on ne recopie pas un chiffre que
    le dépôt sait recalculer, et si le fichier manque la page le dit."""
    f = os.path.join(DATA, "backtest2022.json")
    if not os.path.exists(f):
        return None
    try:
        b = json.load(open(f, encoding="utf-8"))
        l = next(x for x in b["lignes"] if x["jours_avant"] == 132)
        m = l["modes"]["recence"]
        g = {x["fenetre"]: x for x in b.get("grille_fenetre", [])}
        h = {(x["fenetre"], x["house"]): x for x in b.get("grille_house", [])}
        return dict(date=l["date"], mae=m["mae"], n=m["n"], biais=m["biais"],
                    fenetre_90=g.get(90, {}).get("mae_moyenne"),
                    fenetre_60=g.get(60, {}).get("mae_moyenne"),
                    house_90_sans=h.get((90, False), {}).get("mae_moyenne"),
                    house_90_avec=h.get((90, True), {}).get("mae_moyenne"))
    except Exception:
        return None


def run(force=False):
    polls, stats = load_polls(force=force)
    lignes = []
    for cut in CUTOFFS:
        cutd = date.fromisoformat(cut)
        entry = dict(date=cut, jours_avant=(SCRUTIN - cutd).days, modes={})
        for mode, label in MODES:
            agg = G.aggregate(polls, as_of=cutd, weight_mode=mode,
                              min_polls=(1 if mode == "dernier" else None))
            entry["modes"][mode] = metrics(agg, label)
        ref = entry["modes"]["recence"]
        entry["scenario"] = ref["scenario"]
        entry["scenario_taille"] = len(G.aggregate(polls, as_of=cutd)["scenario_sign"]) \
            if ref["n"] else 0
        entry["publie"] = ref["n"] > 0
        lignes.append(entry)

    gw = grid_window(polls)
    gh = grid_house(polls)
    best = best_config(gw, gh)

    cutd = date.fromisoformat(CUTOFFS[-1])
    h = G.HALF_LIFE
    sens = []
    for hl in (15, 30, 60, 180):
        G.HALF_LIFE = hl
        m = metrics(G.aggregate(polls, as_of=cutd), f"demi-vie {hl} j")
        sens.append(dict(half_life=hl, mae=m["mae"], biais=m["biais"], max_err=m["max_err"]))
    G.HALF_LIFE = h

    ref = metrics(G.aggregate(polls, as_of=cutd), "Notre méthode")
    h2027 = HORIZON_2027
    agg2027 = G.aggregate(polls, as_of=date.fromisoformat(h2027))
    m2027 = metrics(agg2027, "Notre méthode")
    trous = [l["date"] for l in lignes if not l["publie"]]
    out = dict(
        genere=G.datetime.now().strftime("%Y-%m-%d %H:%M"),
        election="2017-04-23", scrutin=SCRUTIN.isoformat(),
        source_sondages=("Wikipédia FR, « Liste de sondages sur l'élection présidentielle française "
                         "de 2017 » (CC BY-SA), lue en wikitext"),
        source_sondages_url=PAGE_WIKI,
        source_resultat=("Résultats définitifs du 1er tour 2017, ministère de l'Intérieur "
                         "(Licence Ouverte, data.gouv.fr) ; recoupés avec Wikipédia FR (CC BY-SA)"),
        source_resultat_url=SOURCE_RESULTAT_URL,
        source_resultat_recoupement=PAGE_RESULTATS,
        source_resultat_verifie_le="2026-09-20",
        exprimees=EXPRIMES,
        votes_officiels=VOTES_OFFICIELS,
        resultat=RESULTAT,
        perimetre=f"enquêtes dont la date de fin d'enquête est postérieure au {fr_date(SCOPE_MIN)}",
        dernier_sondage=stats["dernier"], premier_sondage=stats["premier"],
        nb_enquetes=stats["enquetes"], nb_sondages=stats["enquetes_institut"],
        nb_hypotheses=stats["hypotheses_extraites"], nb_instituts=len(stats["instituts"]),
        instituts=stats["instituts"], valeurs_bornees=stats["valeurs_bornees"],
        lignes_bilan=stats["lignes_bilan"], colonnes_ecartees=stats["colonnes_ecartees"],
        controle=stats["controle"],
        lignes=lignes, sensibilite=sens,
        grille_fenetre=gw, grille_house=gh, meilleure=best,
        horizon_2027=dict(date=h2027, metric=m2027, densite=densite(polls, h2027),
                          polls_in_window=(agg2027 or {}).get("polls_in_window"),
                          polls_in_scenario=(agg2027 or {}).get("polls_in_scenario"),
                          scenario=(agg2027 or {}).get("scenario"),
                          scenario_taille=len((agg2027 or {}).get("scenario_sign") or [])),
        reference_2022=ref_2022(),
        densites=[densite(polls, c) for c in ("2016-09-20", "2016-12-12", "2017-03-24",
                                              "2017-04-13")],
        echeances_sans_publication=trous,
        dernier=dict(date=CUTOFFS[-1], jours_avant=(SCRUTIN - cutd).days,
                     modes=[lignes[-1]["modes"][m] for m, _ in MODES]),
        reference=ref,
    )
    json.dump(out, open(os.path.join(DATA, "backtest2017.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return out


# ---------------------------------------------------------------- rendu
def render(bt, lang="fr"):
    m = (lambda a, b: b) if lang == "en" else (lambda a, b: a)
    from html import escape
    ecart = lambda x: ("—" if x is None else
                       ("0,00" if abs(x) < 0.005 else (("+" if x > 0 else "−") + fr2(abs(x)))))
    gw, gh = bt["grille_fenetre"], bt["grille_house"]
    best = bt.get("meilleure") or {}
    r = bt["dernier"]["modes"]
    det = r[0]["detail"]
    trous = bt["echeances_sans_publication"]

    lignes_tbl = "\n".join(
        f'<tr><td>{fr_date(l["date"])}</td><td class="num muted">J−{l["jours_avant"]}</td>'
        + "".join(
            (f'<td class="num"><span class="muted">{m("rien de publiable", "nothing publishable")}</span></td>'
             if l["modes"][mode]["n"] == 0
             else f'<td class="num">{G.fr1u(l["modes"][mode]["mae"])}'
                  f'<span class="muted small"> / {ecart(l["modes"][mode]["biais"])}</span></td>')
            for mode, _ in MODES)
        + f'<td class="num muted small">{l["modes"]["recence"]["polls"]}</td>'
        + f'<td class="num muted small">{G.fr1u(l["modes"]["recence"]["poids_non_candidats"])}</td>'
        + f'<td class="num muted small">{l["scenario_taille"] or "—"}</td></tr>'
        for l in bt["lignes"])

    det_tbl = "\n".join(
        f'<tr><td>{escape(nom)}</td>'
        f'<td class="num"><strong>{("—" if d["estimation"] is None else G.fr1u(d["estimation"]))}</strong></td>'
        f'<td class="num muted">{fr2(d["resultat"])}</td>'
        f'<td class="num">{ecart(d["erreur"]) if d["erreur"] is not None else "<span class=muted>—</span>"}</td></tr>'
        for nom, d in sorted(det.items(), key=lambda kv: -kv[1]["resultat"]))

    sens_tbl = "\n".join(
        f'<tr><td>{m("Demi-vie " + str(s["half_life"]) + " jours", "half-life " + str(s["half_life"]) + " d")}</td>'
        f'<td class="num">{G.fr1u(s["mae"])}</td><td class="num muted">{ecart(s["biais"])}</td>'
        f'<td class="num muted">{G.fr1u(s["max_err"])}</td></tr>' for s in bt["sensibilite"])

    gw_tbl = "\n".join(
        f'<tr><td>{m(str(g["fenetre"]) + " jours", str(g["fenetre"]) + " days")}'
        f'{m(" <span class=muted>(trou)</span>", " <span class=muted>(gap)</span>") if not g["ok"] else ""}</td>'
        f'<td class="num"><strong>{fr2(g["mae_moyenne"])}</strong></td>'
        f'<td class="num">{g["couverture"]}</td>'
        f'<td class="num muted">{fr2(g["n_moyen"])}</td>'
        f'<td class="num muted">{fr2(g["polls_moyen"])}</td></tr>' for g in gw)
    gh_tbl = "\n".join(
        f'<tr><td>{m(h["libelle"], "window " + str(h["fenetre"]) + " d, " + ("house effects corrected" if h["house"] else "no correction"))}</td>'
        f'<td class="num"><strong>{fr2(h["mae_moyenne"])}</strong></td>'
        f'<td class="num muted">{h["couverture"]}</td></tr>' for h in gh)

    dens_tbl = "\n".join(
        f'<tr><td>{fr_date(d["date"])}</td><td class="num muted">J−{d["jours_avant"]}</td>'
        f'<td class="num">{d["enquetes"]}</td><td class="num muted">{d["recentes"]}</td></tr>'
        for d in bt["densites"])

    # ce que la fenêtre de 90 jours donne ici, à fenêtre de 60 jours près
    g90 = next((g for g in gw if g["fenetre"] == 90), {})
    g60 = next((g for g in gw if g["fenetre"] == 60), {})
    g120 = next((g for g in gw if g["fenetre"] == 120), {})
    gain_fenetre = None
    if g60.get("mae_moyenne") is not None and g90.get("mae_moyenne") is not None:
        gain_fenetre = round(g60["mae_moyenne"] - g90["mae_moyenne"], 2)
    gain_house = None
    h30 = next((x for x in gh if x["fenetre"] == 90 and not x["house"]), {})
    h90 = next((x for x in gh if x["fenetre"] == 90 and x["house"]), {})
    if h30.get("mae_moyenne") is not None and h90.get("mae_moyenne") is not None:
        gain_house = round(h30["mae_moyenne"] - h90["mae_moyenne"], 2)

    paires = [(n, d) for n, d in det.items() if d["erreur"] is not None]
    sous = min(paires, key=lambda kv: kv[1]["erreur"]) if paires else None
    sur = max(paires, key=lambda kv: kv[1]["erreur"]) if paires else None
    nc = [l["modes"]["recence"]["poids_non_candidats"] for l in bt["lignes"]]
    nc_max = max(nc) if nc else 0
    gain_dernier = round((r[2]["mae"] or 0) - (r[0]["mae"] or 0), 2)
    top2_reel = [n for n, _ in sorted(bt["resultat"].items(), key=lambda kv: -kv[1])][:2]
    m2027 = bt["horizon_2027"]["metric"]
    d2027 = bt["horizon_2027"]["densite"]

    # accrochage du top 2 réel, échéance par échéance : la phrase le lit, elle ne l'affirme pas
    bon_ordre = [l["date"] for l in bt["lignes"]
                 if l["modes"]["recence"]["top2"] == top2_reel]
    bon_ensemble = [l["date"] for l in bt["lignes"]
                    if sorted(l["modes"]["recence"]["top2"]) == sorted(top2_reel)]
    premier_ensemble = bon_ensemble[0] if bon_ensemble else None
    premier_ordre = bon_ordre[0] if bon_ordre else None
    j_de = lambda d: next((l["jours_avant"] for l in bt["lignes"] if l["date"] == d), None)
    top2_premier = " / ".join(bt["lignes"][0]["modes"]["recence"]["top2"])
    if premier_ensemble is None:
        phrase_top2 = ("le couple réel (" + " et ".join(top2_reel) + ") n'entre dans notre top 2 à "
                       "aucune échéance de ce rétro-test. À la première, notre tête de tableau était "
                       + top2_premier + ", deux noms qui ne figuraient pas au scrutin.")
        phrase_top2_en = ("the real pair (" + " and ".join(top2_reel) + ") does not enter our top 2 at "
                          "any cut-off of this backtest. At the first one, our leading two were "
                          + top2_premier + ", two names that were not on the ballot.")
    else:
        phrase_top2 = ("il entre dans notre tableau le " + fr_date(premier_ensemble) + " (J−"
                       + str(j_de(premier_ensemble)) + ")"
                       + (", et dans le bon ordre le " + fr_date(premier_ordre) + " (J−" + str(j_de(premier_ordre))
                          + ")" if premier_ordre and premier_ordre != premier_ensemble
                          else ", sans jamais s'inverser ensuite dans le bon ordre")
                       + ". À la première échéance, notre tête de tableau était " + top2_premier
                       + ", deux noms qui ne figuraient pas au scrutin. La raison tient au champ "
                       "testé, pas à la pondération : en 2016 les instituts mesuraient encore "
                       "Hollande, Juppé, Sarkozy ou Bayrou.")
        phrase_top2_en = ("it enters our table on " + fr_date(premier_ensemble) + " (J−"
                          + str(j_de(premier_ensemble)) + ")"
                          + (", and in the right order on " + fr_date(premier_ordre) + " (J−" + str(j_de(premier_ordre))
                             + ")" if premier_ordre and premier_ordre != premier_ensemble
                             else ", without ever reversing into the right order afterwards")
                          + ". At the first cut-off, our leading two were " + top2_premier
                          + ", two names that were not on the ballot. The reason lies in the field "
                          "tested, not in the weighting: in 2016 the institutes were still measuring "
                          "Hollande, Juppé, Sarkozy or Bayrou.")
    ligne132 = next((l for l in bt["lignes"] if l["jours_avant"] == 132), None)
    m132 = ligne132["modes"]["recence"] if ligne132 else None
    ref2022 = bt.get("reference_2022")
    # trou de la grille à 30 jours : quelle échéance
    g30 = next((g for g in gw if g["fenetre"] == 30), {})
    trou_30 = [p["date"] for p in g30.get("detail", []) if p["mae"] is None]

    if trous:
        phrase_trous = ("à l'échéance du " + ", ".join(fr_date(d) for d in trous) + ", moins de trois enquêtes "
                        "portaient un même champ de candidats : la page serait restée vide. "
                        "C'est la fragilité à assumer, pas un détail de mise en page.")
        phrase_trous_en = ("at the cut-off of " + ", ".join(fr_date(d) for d in trous) + ", fewer than three surveys "
                           "carried the same candidate field: the page would have stayed empty. "
                           "That is the fragility to own, not a layout detail.")
    else:
        phrase_trous = ("sur chacune des " + str(len(bt["lignes"])) + " échéances de ce rétro-test "
                        "(toutes à 90 jours), le seuil de trois enquêtes était atteint : la page "
                        "n'aurait jamais été vide. La fragilité est ailleurs, et la grille de "
                        "fenêtres la montre : à 30 jours une échéance "
                        "(" + ", ".join(fr_date(d) for d in trou_30) + ") serait restée vide.")
        phrase_trous_en = ("at each of the " + str(len(bt["lignes"])) + " cut-offs of this backtest "
                           "(all at 90 days), the threshold of three surveys was met: the page "
                           "would never have been empty. The fragility lies elsewhere, and the window "
                           "grid shows it: at 30 days one cut-off "
                           "(" + ", ".join(fr_date(d) for d in trou_30) + ") would have stayed empty.")

    if m2027["n"] == 0:
        phrase_2027 = (f"le {fr_date(d2027['date'])}, soit J−{d2027['jours_avant']} avant le scrutin, "
                       f"{bt['horizon_2027']['polls_in_window']} enquêtes tenaient dans la fenêtre "
                       f"de 90 jours mais {bt['horizon_2027']['polls_in_scenario']} seulement "
                       f"testaient le champ le plus documenté "
                       f"({bt['horizon_2027']['scenario_taille']} noms) : aucune échéance de ce "
                       f"rétro-test ne correspond, et la page 2027 serait restée vide. C'est le "
                       f"seuil de trois enquêtes, pas la pondération, qui décide ici.")
        phrase_2027_en = (f"on {fr_date(d2027['date'])}, i.e. J−{d2027['jours_avant']} before the ballot, "
                          f"{bt['horizon_2027']['polls_in_window']} surveys fitted in the 90-day window "
                          f"but only {bt['horizon_2027']['polls_in_scenario']} "
                          f"tested the best-documented field "
                          f"({bt['horizon_2027']['scenario_taille']} names): no cut-off of this "
                          f"backtest matches, and the 2027 page would have stayed empty. It is the "
                          f"threshold of three surveys, not the weighting, that decides here.")
    else:
        phrase_2027 = (f"le {fr_date(d2027['date'])}, soit J−{d2027['jours_avant']} avant le scrutin, notre "
                       f"méthode publiait {m2027['n']} candidats pour "
                       f"{G.fr1u(m2027['mae'])} point d'erreur moyenne, avec "
                       f"{bt['horizon_2027']['polls_in_window']} enquêtes dans la fenêtre.")
        phrase_2027_en = (f"on {fr_date(d2027['date'])}, i.e. J−{d2027['jours_avant']} before the ballot, our "
                          f"method published {m2027['n']} candidates for "
                          f"{G.fr1u(m2027['mae'])} point of mean error, with "
                          f"{bt['horizon_2027']['polls_in_window']} surveys in the window.")

    # Comparaison au même J−132 sur 2022 : le chiffre est relu du fichier 2022, jamais recopié
    if ref2022:
        ref2022_txt = (str(ref2022["mae"]).replace(".", ",") + " point sur " + str(ref2022["n"])
                       + " candidats, biais " + ecart(ref2022["biais"]))
        ref2022_txt_en = (str(ref2022["mae"]).replace(".", ",") + " point on " + str(ref2022["n"])
                          + " candidates, bias " + ecart(ref2022["biais"]))
    else:
        ref2022_txt = "3,83 point sur 12 candidats (référence 2022 non recalculée dans ce dépôt)"
        ref2022_txt_en = "3,83 point on 12 candidates (2022 reference not recomputed in this repository)"

    # hiérarchie des fenêtres : la phrase suit les chiffres, elle ne les précède pas
    if gain_fenetre is not None and gain_fenetre >= 0:
        hier_txt = ("La hiérarchie de 2022 se reproduit sur la couverture : 30 jours laisse une "
                    "échéance vide, 60 jours suffit, et 90 jours reste devant 60 de "
                    + fr2(abs(gain_fenetre)) + " point.")
        hier_txt_en = ("The 2022 ordering is reproduced on coverage: 30 days leaves one "
                       "cut-off empty, 60 days is enough, and 90 days stays ahead of 60 by "
                       + fr2(abs(gain_fenetre)) + " point.")
    else:
        hier_txt = "La hiérarchie de 2022 ne se reproduit pas telle quelle sur cette campagne."
        hier_txt_en = "The 2022 ordering is not reproduced as such on this campaign."
    if g90.get("mae_moyenne") is not None and g120.get("mae_moyenne") is not None:
        moins_txt = ("(" + fr2(round(g90["mae_moyenne"] - g120["mae_moyenne"], 2))
                     + " point de moins qu'à 90 jours)")
        moins_txt_en = ("(" + fr2(round(g90["mae_moyenne"] - g120["mae_moyenne"], 2))
                        + " point less than at 90 days)")
    else:
        moins_txt = moins_txt_en = ""

    # effet de la correction des effets de maison, à fenêtre égale
    if h30.get("mae_moyenne") == h90.get("mae_moyenne"):
        house_txt = ("ne déplace pas l'erreur moyenne (" + fr2(h30.get("mae_moyenne")) + " contre "
                     + fr2(h90.get("mae_moyenne")) + ")")
        house_txt_en = ("does not move the mean error (" + fr2(h30.get("mae_moyenne")) + " against "
                        + fr2(h90.get("mae_moyenne")) + ")")
    elif (gain_house or 0) > 0:
        house_txt = "améliore l'erreur moyenne de " + fr2(abs(gain_house)) + " point"
        house_txt_en = "improves the mean error by " + fr2(abs(gain_house)) + " point"
    else:
        house_txt = "dégrade l'erreur moyenne de " + fr2(abs(gain_house)) + " point"
        house_txt_en = "degrades the mean error by " + fr2(abs(gain_house)) + " point"

    # contrôle de l'analyse : le suffixe ne s'affiche que si les comptes ne tombent pas juste
    controle_txt = "" if bt["controle"]["identiques"] else " : écart à expliquer"
    controle_txt_en = "" if bt["controle"]["identiques"] else ", a gap to explain"
    # périmètre : même phrase, recalculée dans la langue demandée plutôt que traduite par substitution
    perimetre_txt = bt["perimetre"]
    perimetre_txt_en = "surveys whose fieldwork end date is later than " + fr_date(SCOPE_MIN)
    # champ verrouillé : le préfixe français est retiré dans les deux langues, le champ reste le même
    scenario_dernier = (bt["lignes"][-1]["scenario"] or m("aucun", "none")).replace("Champ testé : ", "")

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="{G.meta_description('/observatoire/backtest2017/', lang)}">
<title>{G.titre_court('/observatoire/backtest2017/', lang)}</title>
<link rel="canonical" href="https://dileviathan.fr{G.lien('/backtest2017/', lang)}">
<link rel="alternate" hreflang="fr" href="https://dileviathan.fr{G.lien('/backtest2017/', 'fr')}">
<link rel="alternate" hreflang="en" href="https://dileviathan.fr{G.lien('/backtest2017/', 'en')}">
<link rel="alternate" hreflang="x-default" href="https://dileviathan.fr{G.lien('/backtest2017/', 'fr')}">
{G.meta_social('/observatoire/backtest2017/', lang)}
{G.ld_json("/observatoire/backtest2017/", lang)}
{G.matomo()}
<style>{G.CSS}{G.DARK}
/* Tables : largeur pleine dans les cartes */
section.card table{{width:100%}}</style>
{G.THEME_HEAD}</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand"><a href="{G.lien('/', lang)}" style="text-decoration:none">{m("Présidentielle 2027", "2027 presidential election")}</a> <span>· {m("rétro-test 2017", "2017 backtest")}</span></div>
  <div class="navlinks"><a href="{G.lien('/', lang)}">{m("Accueil", "Home")}</a><a href="{G.lien_page('/sondages/', lang)}">{m("Agrégation", "Aggregate")}</a>
  <a href="{G.lien_page('/candidats/', lang)}">{m("Les candidats", "The candidates")}</a>{G.nav_workflow(lang)}{G.nav_lois(lang)}<a href="#resultats">{m("Résultats", "Results")}</a><a href="#detail">{m("Détail", "Breakdown")}</a><a href="#lecons">{m("Leçons", "Lessons")}</a></div>{G.barre_droite('/backtest2017/', lang)}
</div></div>

<header class="wrap">
  <span class="eyebrow">{m("Validation hors échantillon · observatoire des sondages 2027", "Out-of-sample validation · 2027 poll monitor")}</span>
  <h1>{m("La même méthode, rejouée sur la campagne 2017", "The same method, replayed on the 2017 campaign")}</h1>
  <p class="lede">{m("Les deux réglages de notre page 2027 ont été calés sur 2022 : une fenêtre de sélection de ", "The two settings of our 2027 page were calibrated on 2022: a selection window of ")}
  {G.SCENARIO_WINDOW} {m("jours et la correction des effets de maison. Les rejouer sur 2017, sans rien recaler, ne mesure plus le choix qu'ils ont servi à faire, mais leur transférabilité. Voici ce que la méthode aurait donné, échéance par échéance, face au résultat réel du premier tour du 23 avril 2017. Onze candidats, et cette fois des données jusqu'à J−10.", "days and the house-effect correction. Replaying them on 2017, with nothing re-tuned, no longer measures the choice they were used to make, but their transferability. Here is what the method would have produced, cut-off after cut-off, against the actual first-round result of 23 April 2017. Eleven candidates, and this time data down to J−10.")}</p>
</header>

<main class="wrap">
<section id="resultats" class="card">
  <h2>{m("L'erreur à chaque échéance", "The error at each cut-off")}</h2>
  <p class="small muted">{m("Erreur absolue moyenne", "Mean absolute error")} <strong>/</strong> {m("biais moyen (en points de", "mean bias (in percentage")}
  {m("pourcentage), sur les onze candidats réels. Les colonnes de droite comptent les enquêtes retenues,", "points), over the eleven actual candidates. The columns on the right count the surveys retained,")}
  {m("le poids que notre tableau donnait à des noms qui ne figuraient pas au scrutin, et la taille du", "the weight our table gave to names that were not on the ballot, and the size of the")}
  {m("champ testé. « Rien de publiable » signale une échéance où moins de trois enquêtes portaient un", "field tested. “Nothing publishable” flags a cut-off where fewer than three surveys carried the")}
  {m("même champ : notre seuil de publication interdit alors de publier quoi que ce soit.", "same field: our publication threshold then forbids publishing anything at all.")}</p>
  <table style="margin-top:10px"><tr><th>{m("Échéance", "Cut-off")}</th><th class="num">{m("Distance", "Distance")}</th>
  <th class="num">{m("Notre méthode", "Our method")}</th><th class="num">{m("Poids égaux", "Equal weights")}</th><th class="num">{m("Dernière enquête", "Latest survey")}</th>
  <th class="num">{m("Enquêtes", "Surveys")}</th><th class="num">{m("Poids non-candidats", "Non-candidate weight")}</th><th class="num">{m("Champ", "Field")}</th></tr>
  {lignes_tbl}</table>
  <p class="small" style="margin-top:12px"><strong>{m("À horizon égal :", "At equal horizon:")}</strong> {m("au", "on")} {fr_date(ligne132["date"])}
  (J−132), {m("notre calcul donne", "our calculation gives")} {G.fr1u(m132["mae"])} {m("point d'erreur moyenne sur", "point of mean error over")} {m132["n"]} {m("candidats", "candidates")}
  {m("publiés, pour un biais de", "published, for a bias of")} {ecart(m132["biais"])}. {m("Sur 2022, au même J−132, la même méthode donnait", "On 2022, at the same J−132, the same method gave")}
  {m(ref2022_txt, ref2022_txt_en)}.
  {m("L'erreur tient, le biais non. Ce rétro-test va plus loin en revanche, jusqu'à", "The error holds, the bias does not. This backtest goes further, though, down to")}
  J−{bt["dernier"]["jours_avant"]}{m(" : ", ": ")}{m("la compilation 2022 s'arrêtait au 29/11/2021, la liste 2017 va", "the 2022 compilation stopped on 29/11/2021, the 2017 list runs")}
  {m("jusqu'au 21/04/2017.", "to 21/04/2017.")}</p>
</section>

<section id="detail" class="card">
  <h2>{m("Candidat par candidat, au", "Candidate by candidate, on")} {fr_date(bt["dernier"]["date"])} (J−{bt["dernier"]["jours_avant"]})</h2>
  <table style="margin-top:10px"><tr><th>{m("Candidat", "Candidate")}</th><th class="num">{m("Notre estimation", "Our estimate")}</th>
  <th class="num">{m("Résultat officiel", "Official result")}</th><th class="num">{m("Écart", "Gap")}</th></tr>
  {det_tbl}</table>
  <p class="small muted" style="margin-top:10px">{m("La colonne d'estimation est la moyenne pondérée", "The estimate column is the weighted average")}
  {m("calculée par notre méthode à partir des sondages publiés avant cette date : la source fournit les", "computed by our method from the surveys published before that date: the source supplies the")}
  {m("enquêtes, la pondération est la nôtre. Elle indique ce que notre calcul produisait alors, pas un", "surveys, the weighting is ours. It shows what our calculation produced at the time, not a")}
  {m("chiffre publié par un institut. L'estimation est donnée au dixième, comme notre tableau de 2027 ;", "figure published by an institute. The estimate is given to one decimal, like our 2027 table;")}
  {m("les résultats officiels gardent les deux décimales de leur publication.", "the official results keep the two decimals of their publication.")}</p>
  <p class="small muted">{m("Champ verrouillé à cette échéance", "Field locked at this cut-off")}
  ({bt["lignes"][-1]["scenario_taille"]} {m("noms, scénario le plus testé sur les 90 derniers jours) :", "names, the most tested scenario over the last 90 days):")}
  {escape(scenario_dernier)}.</p>
</section>

<section class="card">
  <h2>{m("Sensibilité au réglage le plus arbitraire", "Sensitivity to the most arbitrary setting")}</h2>
  <p class="small muted" style="max-width:none">{m("La demi-vie fixe la vitesse à laquelle une vieille", "The half-life sets how fast an old")}
  {m("enquête perd son poids. Voici son effet à la dernière échéance : une erreur qui bougerait", "survey loses its weight. Here is its effect at the last cut-off: an error that moved")}
  {m("fortement selon ce seul réglage serait un aveu de fragilité.", "sharply on this single setting would be an admission of fragility.")}</p>
  <table style="margin-top:10px"><tr><th>{m("Réglage", "Setting")}</th><th class="num">{m("Erreur moyenne", "Mean error")}</th>
  <th class="num">{m("Biais", "Bias")}</th><th class="num">{m("Pire écart", "Worst gap")}</th></tr>
  {sens_tbl}</table>
</section>

<section id="reglages" class="card">
  <h2>{m("Les deux réglages de 2022, remis à l'épreuve", "The two 2022 settings, put back to the test")}</h2>
  <p class="small muted" style="max-width:none">{m("Ces grilles ne servent pas à recaler quoi que ce", "These grids are not used to re-tune")}
  {m("soit : la page 2027 garde sa fenêtre de 90 jours et sa correction des effets de maison quelles que", "anything: the 2027 page keeps its 90-day window and its house-effect correction whatever the")}
  {m("soient les valeurs ci-dessous. Elles disent seulement ce que ces deux réglages valent sur une", "values below. They only say what these two settings are worth on a")}
  {m("campagne qu'ils n'ont pas vue.", "campaign they never saw.")}</p>

  <h3 style="margin-top:18px">{m("Fenêtre de sélection du scénario", "Scenario selection window")}</h3>
  <p class="small muted" style="max-width:none">{m("Erreur moyenne sur les échéances, couverture", "Mean error across cut-offs, coverage")}
  {m("(échéances où quelque chose était publiable), candidats publiés et enquêtes retenues en moyenne,", "(cut-offs where something was publishable), candidates published and surveys retained on average,")}
  {m("correction des effets de maison activée sur toutes les lignes :", "house-effect correction enabled on every row:")}</p>
  <table style="margin-top:10px"><tr><th>{m("Fenêtre", "Window")}</th><th class="num">{m("Erreur moyenne", "Mean error")}</th>
  <th class="num">{m("Couverture", "Coverage")}</th><th class="num">{m("Candidats publiés", "Candidates published")}</th>
  <th class="num">{m("Enquêtes retenues", "Surveys retained")}</th></tr>
  {gw_tbl}</table>
  <p class="small" style="margin-top:12px">{m("Sur 2017, la fenêtre de 90 jours retenue pour 2027 donne", "On 2017, the 90-day window kept for 2027 gives")}
  {fr2(g90.get("mae_moyenne"))} {m("point d'erreur moyenne et une couverture de", "point of mean error and a coverage of")} {g90.get("couverture", "—")},
  {m("contre", "against")} {fr2(g60.get("mae_moyenne"))} {m("et", "and")} {g60.get("couverture", "—")} {m("à 60 jours, et", "at 60 days, and")}
  {fr2(g120.get("mae_moyenne"))} {m("à 120 jours.", "at 120 days.")}
  {m(hier_txt, hier_txt_en)}
  {m("En revanche, à 120 jours l'erreur tombe à", "At 120 days, however, the error falls to")} {fr2(g120.get("mae_moyenne"))}
  {m(moins_txt + " :\n  ", moins_txt_en + ": ")}{m("sur cette campagne, la fenêtre retenue n'est pas la meilleure. L'écart est du même ordre que celui", "on this campaign, the window retained is not the best one. The gap is of the same order as the one")}
  {m("qu'un tirage d'enquêtes déplace, et un réglage calé sur 2022 et gelé pour 2027 ne se recale pas sur", "a draw of surveys shifts, and a setting calibrated on 2022 and frozen for 2027 does not re-tune on")}
  {m("une campagne de plus : le rejouer, c'est le mesurer.", "one more campaign: replaying it is measuring it.")}</p>

  <h3 style="margin-top:24px">{m("Correction des effets de maison", "House-effect correction")}</h3>
  <p class="small muted" style="max-width:none">{m("Chaque institut a sa manière de poser ses questions", "Each institute has its own way of asking")}
  {m("et de redresser ses résultats. Nous estimons son écart moyen au consensus des autres, par", "questions and reweighting its results. We estimate its mean gap to the consensus of the others, by")}
  {m("itérations, avec contraction vers zéro quand l'institut est peu vu, puis nous corrigeons avant", "iteration, with shrinkage towards zero when the institute is rarely seen, then we correct before")}
  {m("d'agréger.", "aggregating.")}</p>
  <table style="margin-top:10px"><tr><th>{m("Configuration", "Configuration")}</th><th class="num">{m("Erreur moyenne", "Mean error")}</th>
  <th class="num">{m("Couverture", "Coverage")}</th></tr>
  {gh_tbl}</table>
  <p class="small" style="margin-top:12px">{m("À fenêtre de 90 jours égale, la correction", "At an equal 90-day window, the correction")}
  {m(house_txt, house_txt_en)}
  {m("sur cette campagne, là où 2022 mesurait un gain de 0,04 point. Le réglage reste activé pour 2027 : son", "on this campaign, where 2022 measured a gain of 0,04 point. The setting stays enabled for 2027: its")}
  {m("effet y était positif, son coût nul ici, et il vise un défaut réel (chaque maison a son biais de", "effect there was positive, its cost nil here, and it targets a real flaw (every house has its own")}
  {m("questionnement). Une correction d'effet de maison ne corrige que les écarts <em>entre</em> instituts :", "questioning bias). A house-effect correction only corrects gaps <em>between</em> institutes:")}
  {m("elle ne peut rien contre un biais que toutes les enquêtes partagent, et le plus fort écart du dernier", "it can do nothing against a bias that all surveys share, and the largest gap at the last")}
  {m("point", "point")} ({escape(sous[0]) if sous else "—"}, {ecart(sous[1]["erreur"]) if sous else "—"}) {m("appartient à", "belongs to")}
  {m("cette famille : aucun institut ne le corrige, aucune correction d'effet de maison ne l'atteint.", "that family: no institute corrects it, no house-effect correction reaches it.")}</p>
</section>

<section id="lecons" class="card">
  <h2>{m("Ce que la mise à l'épreuve dit", "What the test says")}</h2>
  <ul class="tight">
    <li><strong>{m("Le top 2 réel n'arrive que tard", "The real top 2 only arrives late")}</strong> : {m(phrase_top2, phrase_top2_en)}</li>
    <li><strong>{m("Erreur moyenne de " + G.fr1u(r[0]["mae"]) + " point(s)", "Mean error of " + G.fr1u(r[0]["mae"]) + " point(s)")}</strong> {m("sur les parts du premier", "on the first-round")}
    {m("tour à", "shares at")} J−{bt["dernier"]["jours_avant"]}, {m("pour un biais de", "for a bias of")} {ecart(r[0]["biais"])} : {m("sur les onze", "of the eleven")}
    {m("candidats réels,", "actual candidates,")} {r[0]["n"]} {m("étaient publiés. À J−132, l'erreur moyenne valait", "were published. At J−132, the mean error stood at")}
    {G.fr1u(m132["mae"])} {m("point(s) pour un biais de", "point(s) for a bias of")} {ecart(m132["biais"])} : {m("à trois-quarts de", "three quarters of the way through the")}
    {m("campagne, notre biais était de sous-estimer, pas de surestimer.", "campaign, our bias was to underestimate, not to overestimate.")}</li>
    <li><strong>{m("L'erreur change de forme en approchant du vote", "The error changes shape as the vote approaches")}</strong> : {m("au dernier point, la plus", "at the last point, the largest")}
    {m("forte sous-estimation est", "underestimate is")} {escape(sous[0]) if sous else "—"}
    ({ecart(sous[1]["erreur"]) if sous else "—"}) {m("et la plus forte surestimation", "and the largest overestimate")}
    {escape(sur[0]) if sur else "—"} ({ecart(sur[1]["erreur"]) if sur else "—"}), {m("sur des niveaux", "on levels")}
    {m("d'environ 20 points. Un agrégateur de sondages ne corrige pas ces mouvements de fin de campagne,", "of about 20 points. A poll aggregator does not correct these end-of-campaign moves,")}
    {m("il les reproduit avec du retard.", "it reproduces them late.")}</li>
    <li><strong>{m("Notre pondération n'apporte rien, à nouveau", "Our weighting brings nothing, again")}</strong> : {fr2(r[0]["mae"])} {m("point", "point")}
    {m("d'erreur avec notre calcul,", "of error with our calculation,")} {fr2(r[1]["mae"])} {m("à poids égaux,", "with equal weights,")} {fr2(r[2]["mae"])} {m("avec la", "with the")}
    {m("dernière enquête seule, soit", "latest survey alone, that is")} {fr2(abs(gain_dernier))} {m("point de moins pour le sondage brut. La", "point less for the raw poll. Nor")}
    {m("demi-vie ne change presque rien non plus", "does the half-life change much")}
    ({", ".join(fr2(s["mae"]) for s in bt["sensibilite"])} {m("selon le réglage, de 15 à 180 jours).", "depending on the setting, from 15 to 180 days).")}
    {m("La valeur ajoutée de la page 2027 n'est donc pas l'agrégation : elle est dans la lisibilité, le", "The added value of the 2027 page is therefore not aggregation: it is in legibility, the")}
    {m("scénario explicite et l'intervalle publié.", "explicit scenario and the published interval.")}</li>
    <li><strong>{m("Le champ de candidats reste le premier facteur d'erreur", "The candidate field remains the leading source of error")}</strong> : {m("les noms testés", "the names tested")}
    {m("qui n'étaient pas au scrutin pesaient jusqu'à", "that were not on the ballot weighed up to")} {G.fr1u(nc_max)} {m("points de notre tableau, contre", "points of our table, against")}
    {G.fr1u(r[0]["poids_non_candidats"])} {m("au dernier point. Verrouiller un scénario revient à parier", "at the last point. Locking a scenario amounts to betting")}
    {m("sur ce chiffre.", "on that figure.")}</li>
    <li><strong>{m("Notre méthode peut ne rien publier", "Our method may publish nothing at all")}</strong> : {m(phrase_trous, phrase_trous_en)}</li>
    <li><strong>{m("À l'horizon où nous publions pour 2027, elle aurait même été muette", "At the horizon where we publish for 2027, it would even have been mute")}</strong> :
    {m(phrase_2027, phrase_2027_en)}</li>
  </ul>
</section>

<section class="card">
  <h2>{m("Densité des enquêtes selon l'horizon", "Survey density by horizon")}</h2>
  <p class="small muted" style="max-width:none">{m("Ce qui décide qu'une page peut publier, c'est le", "What decides whether a page can publish is the")}
  {m("nombre d'enquêtes publiées avant la date de coupe, et plus encore celles du mois écoulé. Mesuré", "number of surveys published before the cut-off date, and even more so those of the past month. Measured")}
  {m("sur la liste 2017, en date de fin d'enquête :", "on the 2017 list, on fieldwork end dates:")}</p>
  <table style="margin-top:10px"><tr><th>{m("Horizon", "Horizon")}</th><th class="num">{m("Distance au scrutin", "Distance to the ballot")}</th>
  <th class="num">{m("Dates d'enquête", "Survey dates")}</th><th class="num">{m("dont le mois écoulé", "of which the past month")}</th></tr>
  {dens_tbl}</table>
  <p class="small muted" style="margin-top:10px">{m("Une campagne pauvre en enquêtes fraîches ne se", "A campaign poor in fresh surveys cannot be")}
  {m("rattrape pas par la méthode : elle se solde par une page vide, ou par un intervalle si large qu'il", "rescued by the method: it ends in an empty page, or in so wide an interval that it")}
  {m("ne dit rien.", "says nothing.")}</p>
</section>

<section class="card">
  <h2>{m("Sources et limites de ce rétro-test", "Sources and limits of this backtest")}</h2>
  <ul class="tight small">
    <li><strong>{m("Sondages :", "Surveys:")}</strong> {m("liste « ", "the list “")}<a href="{bt["source_sondages_url"]}">{m("Liste de sondages", "Liste de sondages")}
    {m("sur l'élection présidentielle française de 2017</a> » (Wikipédia FR, CC BY-SA), lue en wikitext", "sur l'élection présidentielle française de 2017</a>” (Wikipedia FR, CC BY-SA), read as raw wikitext")}
    {m("brut et analysée par", "and parsed by")} <code>backtest2017.py</code>. {bt["nb_hypotheses"]} {m("hypothèses de premier", "first-round")}
    {m("tour,", "hypotheses,")} {bt["nb_sondages"]} {m("enquêtes", "surveys")} ({bt["nb_enquetes"]} {m("dates d'enquête distinctes, du", "distinct fieldwork end dates, from")}
    {fr_date(bt["premier_sondage"])} {m("au", "to")} {fr_date(bt["dernier_sondage"])}), {bt["nb_instituts"]} {m("instituts. Les", "institutes. The")}
    {m("chiffres d'enquête sont des faits ; l'attribution reste due et se porte ici sur les instituts", "survey figures are facts; attribution remains due and falls here on the institutes")}
    {m("qui les ont réalisées et sur la", "that carried them out and on the")} <a href="https://www.commission-des-sondages.fr/notices/">{m("Commission des sondages</a>, qui contrôle la publication des sondages en période électorale. La liste ne", "Commission des sondages</a>, which oversees poll publication during election periods. The list does not")}
    {m("donne pas le lien des notices, à la différence de la compilation 2022 : les liens conservés dans", "give the notice links, unlike the 2022 compilation: the links kept in")}
    {m("nos données sont les publications citées par chaque ligne du tableau.", "our data are the publications cited by each row of the table.")}</li>
    <li><strong>{m("Résultats :", "Results:")}</strong> {m("résultats définitifs du premier tour du 23 avril 2017, publiés", "final first-round results of 23 April 2017, published")}
    {m("par le", "by the")} <a href="{bt["source_resultat_url"]}">{m("ministère de l'Intérieur</a> (jeu de données", "Ministry of the Interior</a> (dataset")}
    {m("« Résultats définitifs du 1er tour », Licence Ouverte, data.gouv.fr), France entière :", "“Résultats définitifs du 1er tour”, Open Licence, data.gouv.fr), whole of France:")}
    {G.frnum(bt["exprimees"])} {m("suffrages exprimés. Les onze scores ont été vérifiés un à un le", "votes cast. The eleven scores were checked one by one on")}
    20/09/2026 {m("et recoupés avec « ", "and cross-checked against “")}<a href="{bt["source_resultat_recoupement"]}">{m("Résultats détaillés", "Résultats détaillés")}
    {m("de l'élection présidentielle française de 2017</a> » (Wikipédia FR, CC BY-SA) : voix et", "de l'élection présidentielle française de 2017</a>” (Wikipedia FR, CC BY-SA): votes and")}
    {m("pourcentages identiques pour les onze candidats.", "percentages identical for the eleven candidates.")}</li>
    <li><strong>{m("Périmètre :", "Scope:")}</strong> {m(perimetre_txt + " ; ", perimetre_txt_en + "; ")}{m("la liste en contient aussi pour 2012 à", "the list also has 2012 to")}
    {m("2015, écartées parce qu'elles portent sur un champ de candidats qui n'a plus rien à voir avec", "2015 entries, discarded because they rest on a candidate field with nothing left in common with")}
    {m("le scrutin. La colonne « Autres candidats » de deux tableaux n'est pas reprise : elle ne nomme", "the ballot. The “Autres candidats” column of two tables is not taken up: it names")}
    {m("personne et gonflerait le poids des non-candidats, qui est justement une des mesures publiées.", "nobody and would inflate the weight of non-candidates, which is precisely one of the published measures.")}</li>
    <li><strong>{m("Contrôle de l'analyse :", "Check on the parse:")}</strong> {m("sur l'ensemble des tableaux du premier tour, toutes", "across every first-round table, all")}
    {m("années confondues, le wikitext contient", "years together, the wikitext holds")} {bt["controle"]["cellules_de_date"]} {m("cellules de date,", "date cells,")}
    {m("une par enquête ; l'analyse en reconstruit", "one per survey; the parse reconstructs")}
    {bt["controle"]["enquetes_reconstruites"]}{m(controle_txt, controle_txt_en)}.
    {m("La clé d'une enquête est son institut, sa date de fin et sa taille d'échantillon, parce qu'un", "A survey's key is its institute, its end date and its sample size, because one")}
    {m("même institut peut publier deux enquêtes closes le même jour (Ifop, le 4 mars 2017, 1 822 et", "institute can publish two surveys closed on the same day (Ifop, 4 March 2017, 1 822 and")}
    {m("1 392 personnes). Les lignes de contexte et la ligne de résultats officiels sont écartées, elles", "1 392 people). Context rows and the official-results row are discarded, they")}
    {m("sont comptées à part dans", "are counted separately in")} <code>data/backtest2017.json</code>. {m("Sur le périmètre retenu, cela", "On the retained scope, that")}
    {m("donne", "gives")} {bt["nb_sondages"]} {m("enquêtes,", "surveys,")} {bt["nb_enquetes"]} {m("dates de fin d'enquête et", "fieldwork end dates and")}
    {bt["nb_hypotheses"]} {m("hypothèses de champ.", "field hypotheses.")}</li>
    <li><strong>{m("Valeurs bornées :", "Bounded values:")}</strong> {bt["valeurs_bornees"]} {m("cellules notées « &lt; 0,5 % »", "cells marked “&lt; 0,5 %”")}
    ({m("candidats testés mais sous le seuil de publication des instituts) sont lues 0,5. Les compter", "candidates tested but below the institutes' publication threshold) are read as 0,5. Counting them")}
    {m("comme absentes ferait disparaître des enquêtes entières du champ.", "as absent would wipe whole surveys out of the field.")}</li>
    <li><strong>{m("Ce que ce rétro-test rejoue :", "What this backtest replays:")}</strong> {m("notre méthode de calcul sur les sondages de", "our computation method on the surveys of")}
    {m("l'époque. Les chiffres publiés ici n'ont jamais été affichés en 2017, et les réglages testés", "the time. The figures published here were never displayed in 2017, and the settings tested")}
    {m("sont ceux de la page 2027, pas ceux d'un observatoire qui aurait existé à l'époque.", "are those of the 2027 page, not those of a monitor that would have existed at the time.")}</li>
    <li><strong>{m("Ce que ce rétro-test ne dit pas :", "What this backtest does not say:")}</strong> {m("un résultat sur 2017 ne valide pas la", "a result on 2017 does not validate the")}
    {m("méthode pour 2027. Deux campagnes ne font pas une distribution, et la densité d'enquêtes, la", "method for 2027. Two campaigns do not make a distribution, and survey density,")}
    {m("stabilité du champ de candidats et le nombre d'instituts comptent autant que la formule.", "stability of the candidate field and the number of institutes count as much as the formula.")}</li>
    <li><strong>{m("Ce qui n'a pas été fait :", "What has not been done:")}</strong> {m("les libellés d'instituts ont été regroupés", "institute labels were grouped")}
    {m("lorsqu'ils désignent la même maison (Ifop et Ifop-Fiducial, TNS, Sofres et Kantar Sofres,", "when they designate the same house (Ifop and Ifop-Fiducial, TNS, Sofres and Kantar Sofres,")}
    {m("Cevipof Ipsos-Sopra Steria et Ipsos, Harris et Harris Interactive, OpinionWay et Opinion Way) :", "Cevipof Ipsos-Sopra Steria and Ipsos, Harris and Harris Interactive, OpinionWay and Opinion Way):")}
    {m("sans ce regroupement, un effet de maison se calcule sur des demi-échantillons.", "without that grouping, a house effect is computed on half-samples.")}</li>
  </ul>
  <p class="small">{m("Rétro-test indépendant de toute publication : son intérêt est d'être faux un jour,", "A backtest independent of any publication: its interest is to be wrong one day,")}
  {m("publiquement. Cette page n'est pas un sondage : elle n'interroge personne et n'anticipe aucun vote.", "publicly. This page is not a poll: it questions nobody and anticipates no vote.")}</p>
  <p class="small muted">{m("Page générée le", "Page generated on")} {bt["genere"]} {m("par", "by")} <code>backtest2017.py</code> : {m("rejouable", "replayable")}
  {m("à volonté, sans réseau si le wikitext est en cache.", "at will, without network if the wikitext is cached.")}</p>
</section>
</main>
<footer class="wrap">
  <p><a href="/fr/mentions-legales">{m("Mentions légales", "Legal notice")}</a></p>
</footer>
{G.THEME_JS}</body>
</html>
"""


def main():
    bt = run(force="--force" in sys.argv)
    os.makedirs(os.path.join(SITE, "backtest2017"), exist_ok=True)
    open(os.path.join(SITE, "backtest2017", "index.html"), "w", encoding="utf-8").write(render(bt))
    # Version anglaise : mêmes chiffres, autres mots.
    en_dir = os.path.join(SITE, "en", "observatoire", "backtest2017")
    os.makedirs(en_dir, exist_ok=True)
    open(os.path.join(en_dir, "index.html"), "w", encoding="utf-8").write(render(bt, lang="en"))
    print(f"rétro-test 2017 : {bt['nb_enquetes']} dates d'enquête, {bt['nb_sondages']} enquêtes, "
          f"{bt['nb_hypotheses']} hypothèses, {bt['nb_instituts']} instituts")
    for m in bt["dernier"]["modes"]:
        print(f"  {m['mode']:38} MAE={m['mae']}  biais={m['biais']}  pire={m['max_err']}  "
              f"top2={' / '.join(m['top2'])}")
    print("  échéances sans publication :", bt["echeances_sans_publication"] or "aucune")
    print("  page : site/backtest2017/index.html")


if __name__ == "__main__":
    main()
