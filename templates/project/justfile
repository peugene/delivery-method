# Recettes appelées par le moteur de la méthode ([commands] de delivery.toml).
# Posé par « deliveryctl init » : chaque recette échoue tant que le projet ne l'a pas définie,
# pour qu'une vérification non configurée soit rouge, jamais verte.

# Lint, build, tests unitaires et d'intégration ; jugé sur son seul code de sortie.
check:
    @echo "justfile : définir la recette 'check' pour la pile du projet" >&2; exit 1

# Un test ciblé (travail en cours d'une story, morsure du relecteur) ; selector : fichier,
# classe ou nom de test selon l'outil de la pile.
test selector:
    @echo "justfile : définir la recette 'test' (selector : '{{selector}}')" >&2; exit 1

# Tests d'IHM de spec/acceptance ; grep = @<story de spec>, vide = suite complète.
acceptance grep='':
    @echo "justfile : définir la recette 'acceptance' (grep : '{{grep}}')" >&2; exit 1

# Exemple avec Playwright, l'application étant lancée par la suite via 'just serve' sur le port
# de la story, que le moteur exporte dans DELIVERY_PORT (3999 en CI) :
#   cd spec/acceptance && npm ci --no-audit --no-fund && npx playwright install chromium
#   cd spec/acceptance && BASE_URL="http://localhost:$DELIVERY_PORT" APP_CMD="just serve $DELIVERY_PORT" \
#     npx playwright test --grep '{{grep}}'
# Le résumé de Playwright (« N passed ») sert au verdict : 0 test exécuté vaut échec.

# Lance l'application de la copie de travail courante, en mode test, sur le port donné.
serve port:
    @echo "justfile : définir la recette 'serve' (port : {{port}})" >&2; exit 1
