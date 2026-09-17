#!/usr/bin/env python3
"""Page « Workflow » de l'observatoire — comment le site se fabrique, en un schéma.

Rôle : rendre l'observatoire vérifiable par un lecteur extérieur. Le schéma montre les sources,
ce qui est mis en cache, ce qui calcule, ce qui est publié, et ce qui déclenche le tout.

Ce fichier est un *générateur*, comme les autres : le dépôt porte le code, pas le résultat
(`site/` n'est pas versionné). Aucune donnée n'est saisie ici ; les chiffres du schéma
(fenêtres, demi-vie, erreur du rétro-test) sont ceux de generate.py et de CHANGELOG.md.

Usage : python3 workflow.py     -> écrit site/workflow/index.html
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as G  # CSS, DARK, THEME_HEAD, THEME_BTN, THEME_JS : le rendu vient de là

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(BASE, "site")

# Palette du schéma. Les familles de couleur sont celles du site (--amber, --blue, --green,
# --red) pour que le schéma se lise dans les deux thèmes ; le violet et l'ardoise, qui n'existent
# pas dans la palette du site, sont définis ici — une valeur par thème, contrastes mesurés.
CSS_PAGE = """
:root{--d-violet:#5b3fa8;--d-slate:#4a5260}
html[data-theme="dark"]{--d-violet:#b9a3fb;--d-slate:#a7b0c4}

.dgwrap{overflow-x:auto;background:var(--bg);border:1px solid var(--line);border-radius:14px;
  padding:14px 10px;margin-top:6px;cursor:zoom-in}
.dgwrap.zoom-active{cursor:zoom-out}
.dgwrap svg{display:block;margin:0 auto;min-width:900px;max-width:100%;height:auto}
/* Lightbox overlay pour le zoom du schéma */
#dg-overlay{display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.85);
  backdrop-filter:blur(4px);cursor:zoom-out;overflow:hidden}
#dg-overlay.open{display:flex;align-items:center;justify-content:center}
#dg-overlay .dg-wrap-inner{position:relative;max-width:95vw;max-height:95vh;overflow:hidden;
  cursor:grab;border-radius:12px;box-shadow:0 0 60px rgba(0,0,0,.5)}
#dg-overlay .dg-wrap-inner:active{cursor:grabbing}
#dg-overlay svg{display:block;max-width:none;max-height:none;transform-origin:0 0;
  background:var(--paper,#11183a);border-radius:12px}
#dg-overlay .close-btn{position:fixed;top:16px;right:20px;width:40px;height:40px;
  background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.2);border-radius:50%;
  color:#fff;font-size:24px;display:flex;align-items:center;justify-content:center;
  cursor:pointer;z-index:10000;transition:background .2s}
#dg-overlay .close-btn:hover{background:rgba(255,255,255,.3)}
#dg-overlay .zoom-hint{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
  color:rgba(255,255,255,.5);font-size:13px;pointer-events:none;z-index:10000;
  background:rgba(0,0,0,.4);padding:6px 14px;border-radius:20px;white-space:nowrap}
.dghint{display:none;font-size:.8rem;color:var(--muted);margin:8px 0 0}
@media(max-width:920px){.dghint{display:block}}

.dg{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.dg .grd{stroke:var(--line);stroke-width:.5;opacity:.45}
.dg .pane{fill:var(--paper);stroke:var(--line);stroke-width:1}
.dg .bx{stroke-width:1.5}
.dg .c-amber{stroke:var(--amber);fill:color-mix(in srgb,var(--amber) 13%,var(--paper))}
.dg .c-blue{stroke:var(--blue);fill:color-mix(in srgb,var(--blue) 13%,var(--paper))}
.dg .c-green{stroke:var(--green);fill:color-mix(in srgb,var(--green) 13%,var(--paper))}
.dg .c-violet{stroke:var(--d-violet);fill:color-mix(in srgb,var(--d-violet) 13%,var(--paper))}
.dg .c-red{stroke:var(--red);fill:color-mix(in srgb,var(--red) 13%,var(--paper))}
.dg .c-slate{stroke:var(--d-slate);fill:color-mix(in srgb,var(--d-slate) 13%,var(--paper))}
.dg .dash{stroke-dasharray:3 3;stroke-width:.9}
.dg .tt{fill:var(--ink);font-size:9px;font-weight:700}
.dg .ss{fill:var(--muted);font-size:7.2px}
.dg .nn{fill:var(--muted);font-size:6.6px}
.dg .lay{fill:var(--muted);font-size:8px;font-weight:700;letter-spacing:.05em}
.dg .ban{fill:var(--ink);font-size:11px;font-weight:700;letter-spacing:.06em}
.dg .ar{fill:none;stroke:var(--muted);stroke-width:1.4}
.dg .ar2{fill:none;stroke:var(--muted);stroke-width:1.1;stroke-dasharray:4 3}
.dg .ah{fill:var(--muted)}
.dg .pill2{fill:none;stroke-width:1}
.dg .sw-b{fill:color-mix(in srgb,var(--amber) 30%,var(--paper));stroke:var(--amber)}
.dg .sw-c{fill:color-mix(in srgb,var(--blue) 30%,var(--paper));stroke:var(--blue)}
.dg .sw-g{fill:color-mix(in srgb,var(--green) 30%,var(--paper));stroke:var(--green)}
.dg .sw-v{fill:color-mix(in srgb,var(--d-violet) 30%,var(--paper));stroke:var(--d-violet)}
.dg .sw-r{fill:color-mix(in srgb,var(--red) 30%,var(--paper));stroke:var(--red)}
.dg .sw-s{fill:color-mix(in srgb,var(--d-slate) 30%,var(--paper));stroke:var(--d-slate)}
"""

# Le schéma. Coordonnées fixes dans un viewBox 1100x930 : toutes les boîtes sont dans une grille
# explicite, et la bande de légende est posée SOUS le schéma (elle le recouvrait en 1100x920).
SCHEMA = """
<svg class="dg" viewBox="0 0 1100 930" xmlns="http://www.w3.org/2000/svg" role="img"
     aria-label="Schéma du workflow : sources externes, cache, générateurs, pages statiques, publication, orchestration">
  <defs>
    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M40 0L0 0 0 40" fill="none" class="grd"/>
    </pattern>
    <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">
      <path d="M0 0L10 5L0 10Z" class="ah"/>
    </marker>
  </defs>
  <rect width="1100" height="930" fill="url(#grid)"/>

  <!-- Bandeau : le déclencheur du cycle -->
  <rect x="20" y="10" width="1060" height="36" rx="6" class="pane"/>
  <text x="550" y="34" text-anchor="middle" class="ban">CYCLE QUOTIDIEN · 18:00 PARIS</text>
  <text x="1060" y="34" text-anchor="end" class="nn">génération ~10 s · cache 12 h</text>

  <!-- ============ 1. COUCHES EXTERNES ============ -->
  <text x="26" y="68" class="lay">COUCHES EXTERNES</text>

  <rect x="30" y="82" width="240" height="72" rx="6" class="bx c-amber"/>
  <text x="150" y="101" text-anchor="middle" class="tt">MieuxVoter/presidentielle2027</text>
  <text x="150" y="114" text-anchor="middle" class="ss">233 enquêtes · JSON</text>
  <text x="150" y="125" text-anchor="middle" class="ss">contrôle quotidien à 11:00</text>
  <text x="150" y="136" text-anchor="middle" class="nn">licence MIT · release le dimanche</text>
  <text x="150" y="147" text-anchor="middle" class="nn">→ data/polls.json</text>

  <rect x="300" y="82" width="240" height="72" rx="6" class="bx c-amber"/>
  <text x="420" y="101" text-anchor="middle" class="tt">whyalwaysrose</text>
  <text x="420" y="114" text-anchor="middle" class="ss">prévision bayésienne · 80 000 tirages</text>
  <text x="420" y="125" text-anchor="middle" class="ss">recalcul quotidien à 07:20</text>
  <text x="420" y="136" text-anchor="middle" class="nn">licence MIT · même source de sondages</text>
  <text x="420" y="147" text-anchor="middle" class="nn">→ data/forecast_bayes.json</text>

  <rect x="570" y="82" width="240" height="72" rx="6" class="bx c-amber"/>
  <text x="690" y="101" text-anchor="middle" class="tt">Bkolenc · campagne 2022</text>
  <text x="690" y="114" text-anchor="middle" class="ss">264 hypothèses de 1er tour</text>
  <text x="690" y="125" text-anchor="middle" class="ss">notices de la Commission des sondages</text>
  <text x="690" y="136" text-anchor="middle" class="nn">licence MIT · résultat officiel vérifié</text>
  <text x="690" y="147" text-anchor="middle" class="nn">→ data/polls2022.json</text>

  <rect x="820" y="82" width="250" height="72" rx="6" class="bx c-amber"/>
  <text x="945" y="101" text-anchor="middle" class="tt">Rédactionnel</text>
  <text x="945" y="114" text-anchor="middle" class="ss">content/observatoire.json</text>
  <text x="945" y="125" text-anchor="middle" class="ss">journal des mises à jour</text>
  <text x="945" y="136" text-anchor="middle" class="nn">data/candidats2027.json</text>
  <text x="945" y="147" text-anchor="middle" class="nn">chaque ligne : source + date de vérification</text>

  <line x1="150" y1="154" x2="200" y2="190" class="ar" marker-end="url(#ah)"/>
  <line x1="420" y1="154" x2="420" y2="190" class="ar" marker-end="url(#ah)"/>
  <line x1="690" y1="154" x2="600" y2="190" class="ar" marker-end="url(#ah)"/>

  <!-- ============ 2. DATA / CACHE ============ -->
  <text x="26" y="202" class="lay">DATA · CACHE</text>

  <rect x="30" y="214" width="170" height="48" rx="6" class="bx c-blue"/>
  <text x="115" y="233" text-anchor="middle" class="tt">data/polls.json</text>
  <text x="115" y="246" text-anchor="middle" class="nn">sondages 2027 · cache 12 h</text>

  <rect x="220" y="214" width="180" height="48" rx="6" class="bx c-blue"/>
  <text x="310" y="233" text-anchor="middle" class="tt">data/forecast_bayes.json</text>
  <text x="310" y="246" text-anchor="middle" class="nn">prévision · cache 6 h</text>

  <rect x="420" y="214" width="170" height="48" rx="6" class="bx c-blue"/>
  <text x="505" y="233" text-anchor="middle" class="tt">data/polls2022.json</text>
  <text x="505" y="246" text-anchor="middle" class="nn">2022 · stable</text>

  <rect x="610" y="214" width="170" height="48" rx="6" class="bx c-blue"/>
  <text x="695" y="233" text-anchor="middle" class="tt">data/history.jsonl</text>
  <text x="695" y="246" text-anchor="middle" class="nn">archive · une ligne par jour</text>

  <path d="M115 262 L115 281 L470 281 L470 298" class="ar" marker-end="url(#ah)"/>
  <path d="M310 262 L310 281 L470 281" class="ar"/>
  <path d="M505 262 L505 281 L470 281" class="ar"/>
  <path d="M695 262 L695 281 L470 281" class="ar"/>

  <!-- ============ 3. GÉNÉRATEURS ============ -->
  <text x="26" y="310" class="lay">GÉNÉRATEURS</text>

  <rect x="30" y="322" width="250" height="72" rx="6" class="bx c-green"/>
  <text x="155" y="341" text-anchor="middle" class="tt">generate.py</text>
  <text x="155" y="354" text-anchor="middle" class="ss">un seul scénario de candidatures retenu</text>
  <text x="155" y="365" text-anchor="middle" class="ss">poids = demi-vie 30 j × √(n/1000)</text>
  <text x="155" y="376" text-anchor="middle" class="nn">correction des effets de maison</text>
  <text x="155" y="387" text-anchor="middle" class="nn">IC 95 % · série hebdo · page Agrégation</text>

  <rect x="300" y="322" width="210" height="72" rx="6" class="bx c-green"/>
  <text x="405" y="341" text-anchor="middle" class="tt">candidats.py</text>
  <text x="405" y="354" text-anchor="middle" class="ss">38 personnes recensées</text>
  <text x="405" y="365" text-anchor="middle" class="ss">17 déclarés · 12 sous condition</text>
  <text x="405" y="376" text-anchor="middle" class="nn">« Qui sera sur le bulletin ? »</text>
  <text x="405" y="387" text-anchor="middle" class="nn">une mesure, pas un modèle</text>

  <rect x="530" y="322" width="210" height="72" rx="6" class="bx c-green"/>
  <text x="635" y="341" text-anchor="middle" class="tt">backtest2022.py</text>
  <text x="635" y="354" text-anchor="middle" class="ss">rejoue la campagne 2022</text>
  <text x="635" y="365" text-anchor="middle" class="ss">erreur par échéance</text>
  <text x="635" y="376" text-anchor="middle" class="nn">grilles de sensibilité</text>
  <text x="635" y="387" text-anchor="middle" class="nn">hors cron : à la demande</text>

  <path d="M945 154 L945 176 L790 176 L790 298 L790 322" class="ar" marker-end="url(#ah)"/>
  <text x="800" y="171" class="nn">contenu éditorial</text>

  <line x1="155" y1="394" x2="155" y2="440" class="ar" marker-end="url(#ah)"/>
  <line x1="405" y1="394" x2="405" y2="440" class="ar" marker-end="url(#ah)"/>
  <line x1="635" y1="394" x2="635" y2="440" class="ar" marker-end="url(#ah)"/>

  <!-- ============ 4. PAGES STATIQUES ============ -->
  <text x="26" y="452" class="lay">PAGES STATIQUES</text>

  <rect x="30" y="464" width="240" height="62" rx="6" class="bx c-violet"/>
  <text x="150" y="483" text-anchor="middle" class="tt">site/index.html</text>
  <text x="150" y="496" text-anchor="middle" class="ss">Accueil · mouvements 7 j</text>
  <text x="150" y="507" text-anchor="middle" class="nn">évolution 8 semaines · comparaison</text>
  <text x="150" y="518" text-anchor="middle" class="nn">méthode · limites</text>

  <rect x="300" y="464" width="240" height="62" rx="6" class="bx c-violet"/>
  <text x="420" y="483" text-anchor="middle" class="tt">site/sondages/index.html</text>
  <text x="420" y="496" text-anchor="middle" class="ss">Agrégation · tête de course</text>
  <text x="420" y="507" text-anchor="middle" class="nn">KPI · tableau par candidat</text>
  <text x="420" y="518" text-anchor="middle" class="nn">marges légales article 2</text>

  <rect x="570" y="464" width="235" height="62" rx="6" class="bx c-violet"/>
  <text x="687" y="483" text-anchor="middle" class="tt">site/backtest/index.html</text>
  <text x="687" y="496" text-anchor="middle" class="ss">Rétro-test 2022</text>
  <text x="687" y="507" text-anchor="middle" class="nn">erreur 3,11 pt · sensibilité</text>
  <text x="687" y="518" text-anchor="middle" class="nn">la décision et ses motifs</text>

  <rect x="835" y="464" width="235" height="62" rx="6" class="bx c-violet"/>
  <text x="952" y="483" text-anchor="middle" class="tt">site/candidats/index.html</text>
  <text x="952" y="496" text-anchor="middle" class="ss">Les candidats</text>
  <text x="952" y="507" text-anchor="middle" class="nn">familles · statuts · sources</text>
  <text x="952" y="518" text-anchor="middle" class="nn">présence sur le bulletin</text>

  <rect x="30" y="546" width="185" height="36" rx="4" class="bx c-blue dash"/>
  <text x="122" y="562" text-anchor="middle" class="ss">data/summary.json</text>
  <text x="122" y="574" text-anchor="middle" class="nn">résultats machine</text>

  <rect x="230" y="546" width="160" height="36" rx="4" class="bx c-blue dash"/>
  <text x="310" y="562" text-anchor="middle" class="ss">movements.json</text>
  <text x="310" y="574" text-anchor="middle" class="nn">alimente le digest</text>

  <line x1="150" y1="526" x2="310" y2="610" class="ar" marker-end="url(#ah)"/>
  <line x1="420" y1="526" x2="420" y2="610" class="ar" marker-end="url(#ah)"/>
  <line x1="687" y1="526" x2="530" y2="610" class="ar" marker-end="url(#ah)"/>
  <line x1="952" y1="526" x2="530" y2="610" class="ar" marker-end="url(#ah)"/>

  <!-- ============ 5. PUBLICATION ============ -->
  <text x="26" y="622" class="lay">PUBLICATION</text>

  <rect x="30" y="634" width="265" height="72" rx="6" class="bx c-red"/>
  <text x="162" y="653" text-anchor="middle" class="tt">nginx:alpine — simulation-poc</text>
  <text x="162" y="666" text-anchor="middle" class="ss">127.0.0.1:8090 · fichiers statiques</text>
  <text x="162" y="677" text-anchor="middle" class="nn">Cache-Control: no-cache</text>
  <text x="162" y="688" text-anchor="middle" class="nn">absolute_redirect off</text>
  <text x="162" y="699" text-anchor="middle" class="nn">monte site/ en lecture seule</text>

  <rect x="320" y="634" width="245" height="72" rx="6" class="bx c-red"/>
  <text x="442" y="653" text-anchor="middle" class="tt">Dépôt public GitHub</text>
  <text x="442" y="666" text-anchor="middle" class="ss">observatoire-presidentielle-2027</text>
  <text x="442" y="677" text-anchor="middle" class="nn">licence MIT · données dérivées</text>
  <text x="442" y="688" text-anchor="middle" class="nn">et contenu éditorial seulement</text>
  <text x="442" y="699" text-anchor="middle" class="nn">commit automatique du jour</text>

  <rect x="590" y="634" width="245" height="72" rx="6" class="bx c-red"/>
  <text x="712" y="653" text-anchor="middle" class="tt">Caddy — reverse proxy</text>
  <text x="712" y="666" text-anchor="middle" class="ss">handle /observatoire*</text>
  <text x="712" y="677" text-anchor="middle" class="nn">préfixe conservé (pas de strip)</text>
  <text x="712" y="688" text-anchor="middle" class="nn">/simulation* → 301 vers /observatoire</text>
  <text x="712" y="699" text-anchor="middle" class="nn">le reste → Next.js :3000</text>

  <rect x="860" y="634" width="210" height="72" rx="6" class="bx c-slate"/>
  <text x="965" y="653" text-anchor="middle" class="tt">dileviathan.fr</text>
  <text x="965" y="666" text-anchor="middle" class="ss">/observatoire</text>
  <text x="965" y="677" text-anchor="middle" class="nn">/observatoire/sondages</text>
  <text x="965" y="688" text-anchor="middle" class="nn">/observatoire/candidats</text>
  <text x="965" y="699" text-anchor="middle" class="nn">/observatoire/backtest</text>

  <line x1="295" y1="670" x2="320" y2="670" class="ar"/>
  <line x1="565" y1="670" x2="590" y2="670" class="ar" marker-end="url(#ah)"/>
  <line x1="835" y1="670" x2="860" y2="670" class="ar" marker-end="url(#ah)"/>
  <path d="M295 682 L295 706 L320 706" class="ar"/>

  <!-- ============ 6. ORCHESTRATION ============ -->
  <text x="26" y="758" class="lay">ORCHESTRATION</text>

  <rect x="30" y="770" width="235" height="82" rx="6" class="bx c-slate"/>
  <text x="147" y="790" text-anchor="middle" class="tt">Cron · 0 18 * * *</text>
  <text x="147" y="804" text-anchor="middle" class="ss">simulation_daily.sh</text>
  <text x="147" y="816" text-anchor="middle" class="nn">sans agent : la sortie est le message</text>
  <text x="147" y="827" text-anchor="middle" class="nn">code de retour ≠ 0 → alerte</text>
  <text x="147" y="838" text-anchor="middle" class="nn">régénère puis contrôle le HTTP 200</text>

  <rect x="295" y="770" width="220" height="82" rx="6" class="bx c-slate"/>
  <text x="405" y="790" text-anchor="middle" class="tt">digest.py</text>
  <text x="405" y="804" text-anchor="middle" class="ss">lit movements.json</text>
  <text x="405" y="816" text-anchor="middle" class="nn">mouvements sur 7 et 28 jours</text>
  <text x="405" y="827" text-anchor="middle" class="nn">état de la source</text>
  <text x="405" y="838" text-anchor="middle" class="nn">dernières valeurs publiées</text>

  <rect x="545" y="770" width="180" height="82" rx="6" class="bx c-slate"/>
  <text x="635" y="790" text-anchor="middle" class="tt">Message Telegram</text>
  <text x="635" y="804" text-anchor="middle" class="ss">synthèse quotidienne</text>
  <text x="635" y="816" text-anchor="middle" class="nn">jour normal : le digest</text>
  <text x="635" y="827" text-anchor="middle" class="nn">incident : l'alerte</text>
  <text x="635" y="838" text-anchor="middle" class="nn">silence si tout va bien</text>

  <rect x="755" y="770" width="315" height="82" rx="6" class="bx c-red"/>
  <text x="912" y="790" text-anchor="middle" class="tt">Suspension légale — article 11</text>
  <text x="912" y="804" text-anchor="middle" class="ss">loi du 19 juillet 1977</text>
  <text x="912" y="816" text-anchor="middle" class="nn">veille et jour de chaque tour :</text>
  <text x="912" y="827" text-anchor="middle" class="nn">avis de suspension, aucun chiffre</text>
  <text x="912" y="838" text-anchor="middle" class="nn">1er tour 18/04/2027 · 2d tour 02/05/2027</text>

  <path d="M147 770 L147 752 L118 752 L118 634" class="ar2" marker-end="url(#ah)"/>
  <line x1="265" y1="811" x2="295" y2="811" class="ar" marker-end="url(#ah)"/>
  <line x1="515" y1="811" x2="545" y2="811" class="ar" marker-end="url(#ah)"/>

  <!-- ============ LÉGENDE — sous le schéma, ne recouvre rien ============ -->
  <rect x="20" y="876" width="1060" height="40" rx="6" class="pane"/>
  <rect x="40" y="888" width="16" height="16" rx="3" class="pill2 sw-b"/>
  <text x="64" y="901" class="ss">Source externe</text>
  <rect x="250" y="888" width="16" height="16" rx="3" class="pill2 sw-c"/>
  <text x="274" y="901" class="ss">Cache / données</text>
  <rect x="440" y="888" width="16" height="16" rx="3" class="pill2 sw-g"/>
  <text x="464" y="901" class="ss">Générateur Python</text>
  <rect x="630" y="888" width="16" height="16" rx="3" class="pill2 sw-v"/>
  <text x="654" y="901" class="ss">Page statique</text>
  <rect x="800" y="888" width="16" height="16" rx="3" class="pill2 sw-s"/>
  <text x="824" y="901" class="ss">Orchestration</text>
  <rect x="960" y="888" width="16" height="16" rx="3" class="pill2 sw-r"/>
  <text x="984" y="901" class="ss">Publication</text>
</svg>
"""

PAGE = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="{G.meta_description('/observatoire/workflow/')}">
<title>Comment le site se fabrique — Observatoire présidentielle 2027</title>
<link rel="canonical" href="https://dileviathan.fr/observatoire/workflow/">
{G.ld_json("/observatoire/workflow/")}
{G.matomo()}
{G.THEME_HEAD}
<style>{G.CSS}{G.DARK}{CSS_PAGE}</style>
</head>
<body>
<div class="topbar"><div class="wrap nav">
  <div class="brand"><a href="/observatoire/" style="text-decoration:none">Présidentielle 2027</a> <span>· workflow</span></div>
  <div class="navlinks"><a href="/observatoire/">Accueil</a><a href="/observatoire/sondages/">Agrégation</a>
  <a href="/observatoire/candidats/">Les candidats</a><a href="/observatoire/backtest/">Rétro-test 2022</a>{G.NAV_LOIS}<a href="#schema" style="font-weight:700;color:var(--ink)">Workflow</a></div>{G.THEME_BTN}
</div></div>

<main class="wrap">
<header>
  <span class="eyebrow">Annexe technique</span>
  <h1>Comment ce site se fabrique</h1>
  <p class="lede">Un observatoire de sondages ne vaut que si l'on peut vérifier d'où viennent ses
  chiffres et comment ils sont calculés. Cette page montre la chaîne complète : une seule source
  pour les intentions de vote, des couches séparées pour le reste, aucun chiffre saisi à la main,
  et une page qui se suspend d'elle-même pendant la période légale.</p>
</header>

<section id="schema" class="card">
  <h2>Le cycle, de la source à la page publiée</h2>
  <p class="small muted" style="max-width:none">Six étapes, une seule source de chiffres (MieuxVoter, licence MIT) et des
  couches complémentaires toujours étiquetées séparément. Une intention de vote ne se moyenne jamais
  avec une probabilité de marché ou de modèle.</p>
  <div class="dgwrap" id="dg-wrap">{SCHEMA}</div>
  <p class="dghint">↔ le schéma défile horizontalement · cliquez pour zoomer</p>
</section>

<!-- Lightbox overlay pour le zoom -->
<div id="dg-overlay">
  <div class="dg-wrap-inner" id="dg-inner"></div>
  <div class="close-btn" id="dg-close">✕</div>
  <div class="zoom-hint">Molette pour zoomer · glisser pour se déplacer · Échap pour fermer</div>
</div>

<div class="cards">
  <div class="card2">
    <h3>La méthode, publiée</h3>
    <p>Poids <code>w = exp(−ln2 × âge_jours / 30) × √(échantillon / 1000)</code>. Intervalle à
    95 % sur la moyenne, plancheré à ±1 point — un intervalle de moyenne, pas de prévision.
    Scénario de candidatures unique, fenêtre de 90 jours, agrégation sur 180 jours, minimum
    trois sondages pour publier.</p>
  </div>
  <div class="card2">
    <h3>Le rythme</h3>
    <p>La source contrôle les nouvelles enquêtes chaque jour à 11:00 et recalcule sa prévision
    à 07:20. Nos pages se régénèrent le soir à 18:00 : un sondage validé le matin est publié le
    jour même. Un cron horodate, contrôle le HTTP 200 et envoie une synthèse.</p>
  </div>
  <div class="card2">
    <h3>Ce que la loi impose</h3>
    <p>Loi n° 77-808 du 19 juillet 1977 : institut, commanditaire, effectif, dates et marges
    pour chaque enquête agrégée (art. 2), aucune publication la veille et le jour d'un scrutin
    (art. 11). Jamais « notre sondage » — une moyenne de sondages n'est pas un sondage.</p>
  </div>
</div>

<section class="card">
  <h2>Ce que le rétro-test 2022 a appris</h2>
  <p class="small muted" style="max-width:none">La méthode rejouée sur la campagne 2022, comparée au résultat officiel
  du ministère de l'Intérieur (12 scores sur 12 vérifiés). C'est ce qui a fixé les deux réglages
  ci-dessus, et c'est aussi ce qui borne la confiance à leur accorder.</p>
  <ul class="tight">
    <li>Erreur moyenne <strong>3,11 point</strong> avec la configuration retenue (fenêtre 90 jours,
    correction des effets de maison activée).</li>
    <li>Les deux finalistes identifiés dès <strong>J−132</strong>, dans le bon ordre.</li>
    <li>La pondération par fraîcheur <strong>n'apporte rien</strong> : 3,83 contre 3,73 pour la
    dernière enquête seule. La valeur de cette page est la lisibilité, pas le calcul.</li>
    <li>Les biais sont <strong>structurels</strong> : à J−132, Mélenchon sous-estimé de 13,8 points,
    Zemmour surestimé de 8,3. Un agrégateur de sondages ne corrige pas ces biais.</li>
    <li>Grilles complètes, réglage par réglage, sur la page
    <a href="/observatoire/backtest/">Rétro-test 2022</a>.</li>
  </ul>
</section>

<section class="card">
  <h2>Vérifier par soi-même</h2>
  <p class="small" style="max-width:none">Le code est publié sous licence MIT, les données dérivées et le contenu
  éditorial sont versionnés au jour le jour :
  <a href="https://github.com/les-tontons-de-la-tech/observatoire-presidentielle-2027">dépôt
  observatoire-presidentielle-2027</a>. Les caches téléchargés (~900 Ko chez MieuxVoter) ne sont
  pas recopiés : ils se rechargent, et la source est citée.</p>
  <p class="small muted" style="margin-top:10px;max-width:none">Page régénérée par <code>workflow.py</code>.
  Journal des changements de chiffres et de textes : <code>CHANGELOG.md</code> du dépôt.</p>
</section>
</main>

<footer class="wrap">
  <p><a href="/fr/mentions-legales">Mentions légales</a></p>
</footer>
{G.THEME_JS}
<script>(function(){{
var wrap=document.getElementById("dg-wrap"),overlay=document.getElementById("dg-overlay"),
inner=document.getElementById("dg-inner"),close=document.getElementById("dg-close");
if(!wrap||!overlay)return;
var svg=wrap.querySelector("svg");if(!svg)return;
var scale=1,tx=0,ty=0,down=false,sx=0,sy=0,stx=0,sty=0;
function openZoom(){{
overlay.classList.add("open");
var clone=svg.cloneNode(true);
clone.setAttribute("width","1100");
clone.setAttribute("height","930");
inner.innerHTML="";
inner.appendChild(clone);
scale=1;tx=0;ty=0;
updateTransform();
}}
function closeZoom(){{overlay.classList.remove("open");inner.innerHTML="";}}
function updateTransform(){{
var el=inner.querySelector("svg");
if(!el)return;
el.style.transform="translate("+tx+"px,"+ty+"px) scale("+scale+")";
}}
wrap.addEventListener("click",function(){{openZoom();}});
overlay.addEventListener("click",function(e){{if(e.target===overlay||e.target===close)closeZoom();}});
overlay.addEventListener("wheel",function(e){{
e.preventDefault();
var ds=e.deltaY>0?0.9:1.1;
var rect=inner.getBoundingClientRect();
var mx=e.clientX-rect.left,my=e.clientY-rect.top;
var ns=scale*ds;if(ns<0.3)ns=0.3;if(ns>8)ns=8;
tx=mx-(mx-tx)*(ns/scale);
ty=my-(my-ty)*(ns/scale);
scale=ns;
updateTransform();
}},{{passive:false}});
inner.addEventListener("mousedown",function(e){{
down=true;sx=e.clientX;sy=e.clientY;stx=tx;sty=ty;
e.preventDefault();
}});
document.addEventListener("mousemove",function(e){{
if(!down)return;var dx=e.clientX-sx,dy=e.clientY-sy;
tx=stx+dx;ty=sty+dy;updateTransform();
}});
document.addEventListener("mouseup",function(){{down=false;}});
document.addEventListener("keydown",function(e){{
if(e.key==="Escape")closeZoom();
}});
}})();</script></body>
</html>
"""


def main():
    out_dir = os.path.join(SITE, "workflow")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(PAGE)
    print(f"  -> {out} ({len(PAGE)} caractères)")


if __name__ == "__main__":
    main()
