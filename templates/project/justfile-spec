# Recettes appelées par le moteur de la méthode ([commands] de delivery.toml).
# Posé par « deliveryctl init spec » : dans un dépôt de spécification, elles marchent d'emblée.

# La vérification d'un dépôt de spec : le lint de la spécification.
check:
    .delivery/deliveryctl spec lint

# Un test d'IHM ciblé de spec/acceptance ; selector : son titre, ou un morceau de son titre.
test selector: _install
    cd spec/acceptance && BASE_URL="http://localhost:${DELIVERY_PORT:-3999}" APP_CMD="just serve ${DELIVERY_PORT:-3999}" npx playwright test --grep '{{selector}}'

# Tests d'IHM de spec/acceptance ; grep = @<story de spec>, vide = suite complète.
# L'application est lancée par la suite via 'just serve' sur le port de la story, que le moteur
# exporte dans DELIVERY_PORT (3999 en CI). Le résumé de Playwright (« N passed ») sert au
# verdict : 0 test exécuté vaut échec.
acceptance grep='': _install
    cd spec/acceptance && BASE_URL="http://localhost:${DELIVERY_PORT:-3999}" APP_CMD="just serve ${DELIVERY_PORT:-3999}" npx playwright test --grep '{{grep}}'

# Lance l'application vide de la suite, sur le port donné : tant qu'aucune implémentation n'est
# branchée, les tests échouent contre elle, ce qui est leur état normal avant le code.
serve port:
    PORT={{port}} node spec/acceptance/fixtures/empty-app/server.mjs

# Installe la suite (dépendances et navigateur) quand node_modules manque.
_install:
    cd spec/acceptance && { [ -d node_modules ] || { npm install --no-audit --no-fund && npx playwright install chromium; }; }
