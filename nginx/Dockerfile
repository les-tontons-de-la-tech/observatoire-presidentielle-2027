# Image nginx de l'Observatoire Présidentielle 2027 (VPS B).
#
# Pourquoi une image construite, plutôt que nginx:alpine pris directement : le correctif d'un
# paquet de la base doit vivre DANS l'image. Un « apk upgrade » lancé dans un conteneur en service
# disparaît à la première recréation, et l'inventaire de l'image continuerait de nommer la version
# vulnérable — donc l'avis resterait ouvert à juste titre.
#
# Cas déclencheur (22/09/2026) : libexpat 2.8.4-r0 -> 2.8.5-r0, CVE-2026-93990, sévérité haute.
# Le composant n'est pas dans le chemin d'exécution de nginx (il n'est tiré que par les outils
# fontconfig de l'image), mais un correctif existe et coûte une ligne : on corrige, on n'argumente pas.
#
# À reconstruire dès que la veille SBOM signale une version corrigée disponible pour un paquet de
# cette image. C'est l'image déployée qui fait foi pour la réponse aux alertes, pas le conteneur.
FROM nginx:alpine
RUN apk upgrade --no-cache && rm -rf /var/cache/apk/*
