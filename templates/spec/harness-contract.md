# Contrat du harnais de test

Seule surface technique que la spécification impose. Chaque implémentation sert ces routes **en
mode test seulement**, sur l'origine de `BASE_URL` ; hors mode test, elles n'existent pas. Chaque
implémentation choisit comment elle active son mode test et le dit dans sa commande `acceptance`.

| Route | Effet | Réponse |
|---|---|---|
| `POST /__test__/reset` | vide toutes les données | 2xx |
| `POST /__test__/users`, corps `{"name": "alice"}` | crée la personne nommée si elle n'existe pas | 2xx |
| `GET /__test__/login-as/<name>` | ouvre une session pour cette personne, puis affiche l'accueil | 2xx ou redirection |
| `POST /__test__/tick`, corps `{"by": "PT2H"}` | avance l'horloge de l'application de la durée donnée (ISO 8601) et exécute ce qui est dû | 2xx |

`tick` n'est dû que si une story dépend du temps.

## Règles

- Toute autre donnée passe par l'interface : ni route d'amorçage, ni accès direct au stockage.
- La suite n'atteint l'application que par `BASE_URL`, ces routes et l'interface.
- Les tests trouvent les éléments par `getByRole`, `getByLabel` et `getByText`, avec les libellés
  de `copy('<clé>')`, lus dans `spec/ui/copy.<locale>.json`. Ni sélecteur CSS, ni identifiant de
  test, ni attente d'une durée fixe.
- Un test couvre un critère par l'étiquette `@<id>-ac<n>` dans son titre et porte `@<id>`, dans
  son titre ou dans celui du `test.describe` qui l'englobe. `deliveryctl spec lint` le vérifie.
- Le temps ne passe que par `tick`.
- Chaque test part de `reset` : aucun test ne dépend d'un autre ni de l'ordre d'exécution.

## Application vide

`fixtures/empty-app/` sert le harnais et rien d'autre. La suite y est 100 % rouge : un test vert
contre l'application vide ne prouve rien.

```sh
node fixtures/empty-app/server.mjs &          # port PORT, 3999 par défaut
BASE_URL=http://localhost:3999 npx playwright test
```

## Lancer la suite

```sh
npm ci && npx playwright install chromium
BASE_URL=<origine> npx playwright test --grep @s004   # une story
BASE_URL=<origine> npx playwright test                # suite complète
```

`APP_CMD`, s'il est défini, lance l'application à tester : Playwright la démarre, attend
`BASE_URL`, joue les tests, puis l'arrête.
