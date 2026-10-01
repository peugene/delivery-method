# Contrats de delivery-method

Ce document fixe tout ce que le moteur `deliveryctl`, les rôles et les humains s'échangent :
fichiers, formats, verdicts, états, gestes. Il fait foi. Tout changement de contrat figure dans
la rubrique `Contracts` du `CHANGELOG.md`. Tant que le plugin est en `0.x`, un changement de
contrat monte la version mineure ; le passage en 1.0.0 est un geste du decision owner, et
ensuite un changement de contrat est une version majeure.

Conventions : identifiants, clés, noms de section et mots-clés en anglais ; tout texte lu par un
humain (cartes, ordres, comptes rendus, plans) dans la langue du projet (`content_language`).
Dans un texte lu par un humain, une carte, une story, une anomalie, un contrôle de recette ou une
décision se nomme par sa référence lisible `<id> : <titre court>`, jamais par son seul
identifiant (§1).

## 1. Vocabulaire

| Terme | Valeurs ou sens |
|---|---|
| `phase` | `spec`, `impl`, `qualification` : spécifier, implémenter, recetter |
| régime | spec : on discute, rien ne se tranche en silence ; impl : on tranche et on documente, ou on diffère ; qualification : on constate et on consigne |
| `repo_role` | `single`, `spec`, `impl` : ce que contient le dépôt |
| `release_stage` | `pre-release`, `released` : avant ou après la première livraison à un tiers |
| carte | fichier de `backlog/` : `story` (issue de la spec), `task` (travail technique hors spec), `anomaly` (défaut constaté) |
| référence lisible | `<id> : <titre court>` (identifiant, espace, deux-points, espace, titre court) : `s004 : Partager une liste`, `a003 : Le partage accepte un compte supprimé`, `Q17 : un compte non invité ne lit pas une liste partagée`, `D3 : la règle de partage`. Nom d'une carte, d'une story, d'une anomalie, d'un contrôle de recette ou d'une décision dans tout texte lu par un humain : comptes rendus, ordres, relectures, plans, messages de commit, campagnes, sorties du moteur, notifications, messages au decision owner. Titre inconnu : l'identifiant seul. Les noms techniques gardent l'identifiant seul : branche `story/s004`, chemin `docs/stories/s004/`, trailer `Story: s004`, frontmatter, étiquette de test `@s004`, argument de commande |
| `Outcome` | fin de travail d'une session : `done`, `blocked`, `deferred`, `plan-ready`, `question` |
| lead | session de conduite d'une phase : `product-analyst`, `technical-lead`, `qualification-lead` |
| campagne | objectif d'un lead avec son critère de fin (incrément tagué, lot de cartes fusionné, recette rendue) ; une session de lead par campagne, reprise après `/clear` depuis `## Next` |
| morsure (`bite`) | casser volontairement la protection visée (un ou deux invariants), constater qu'un test échoue, restaurer, prouver la restauration par `git diff --exit-code` |
| relecture contradictoire (`adversarial-review`) | le relecteur attaque en plus l'angle du risque nommé : succès vide, régression cachée, mesure polluée, chacun avec son résultat |
| `integration` | `human`, `ai` : qui fusionne les demandes de fusion de story |
| `window` | `auto`, `herdr`, `terminal` : où le moteur montre et lance les sessions |

**Decision owner** : l'humain qui décide. Seul lui approuve, fusionne en mode `human`, tague,
synchronise une version de spec, pousse, et change la méthode.

## 2. Emplacements dans un projet

| Chemin | Suivi par git | Écrit par | Contenu |
|---|---|---|---|
| `delivery.toml` | oui | humain | réglages du projet (§3) |
| `.delivery/deliveryctl` | oui | `deliveryctl init` | point d'entrée du moteur du projet (exécutable, Python standard) |
| `.delivery/engine/`, `.delivery/templates/`, `.delivery/VERSION` | oui | `deliveryctl init` | copie du moteur et des gabarits, figée par projet |
| `.delivery/method.json` | oui | `deliveryctl init` | manifeste de la copie de la méthode : version et empreinte (sha1) de chaque fichier copié sous `.claude/`, tel qu'écrit |
| `.claude/agents/`, `.claude/skills/`, `.claude/commands/` | oui | `deliveryctl init` (copie du plugin), puis `--upgrade` | agents, skills et commandes de la méthode, copiés du plugin sauf la commande `init` (qui équipe le projet et reste une commande du plugin) ; dans chaque fichier copié, `delivery-method:<nom>` et `/delivery-method:<nom>` perdent l'espace de noms quand `<nom>` est un agent, un skill ou une commande copiés. Une session Claude Code sans plugin (session cloud) y trouve toute la méthode. Les fichiers absents du manifeste sont ceux du projet : jamais touchés |
| `.delivery/rules.md` | oui | `deliveryctl init` | règles communes, importées par `CLAUDE.md` |
| `.delivery/run/` | non | moteur seul | fichiers de rôle, sessions, ports, notifications, registre des verdicts (`verdicts.json`, §6), journaux de sortie ; aucun rôle n'y écrit |
| `CLAUDE.md` | oui | `init` (crée ou ajoute `@.delivery/rules.md`), puis humain | règles et conventions du projet |
| `.claude/settings.json` | oui | `init` (fusion par ajout), puis humain | plugin désactivé dans le projet (`enabledPlugins` à `false`, dès le premier `init`, même si une installation du plugin à la portée projet l'a écrit à `true` : sa copie ferait doublon avec celle du projet), hooks `Stop`, `SessionStart` et `PreToolUse` (matcher `Bash`, filtré par `if` sur les commandes `deliveryctl *` et `.delivery/deliveryctl *`), refus de `SendMessage` pour toute session du projet, `ask` sur les gestes humains |
| `.gitignore` | oui | `init` (ajout) | `.delivery/run/`, `.delivery/**/__pycache__/`, `docs/stories/*/work/`, `docs/campaigns/work/`, `qualification/work/`, sorties de tests (`test-results/`, `playwright-report/`, `spec/acceptance/node_modules/`) |
| `backlog/<id>-<slug>.md` | oui | leads (`draft`), humain (`ready`), rôles (anomalies) | cartes (§5) |
| `docs/stories/<id>/` | oui | rôles, moteur | dossier de story (§6) |
| `docs/stories/<id>/work/` | non | rôles ; moteur pour `verify.log` | état de travail de la story (§6.7) |
| `docs/campaigns/<nom>.md` | oui | lead | état d'une campagne (§12.3) |
| `docs/campaigns/work/` | non | lead | brouillons d'une campagne, dont les ordres de travail |
| `docs/architecture.md`, `docs/adr/` | oui | `technical-lead` | cadrage d'architecture |
| `spec/`, `spec.lock` | oui | `init` (squelette de `spec/`, dépôt `spec` ou `single`, si `spec/` est absent), puis analyste ; `spec sync` (dépôt d'impl) | spécification (§14) |
| `refinement/<incr>/` | oui | `product-analyst` | maturation d'un incrément (§14.1) |
| `qualification/` | oui, sauf `work/` | `qualification-lead`, `qualification-runner` | recette (§15) : `plan.md`, `order.md` (ordre du runner, commité par le lead avant `qualify run`), `reports/`, `kit/` (matériel de recette : scripts, données, mise en place et retrait) |
| dossier temporaire de session (`/tmp`) | non | tous | jetable uniquement ; jamais une preuve |

Copie de travail d'une story : `<parent>/<dépôt>-wt/<id>`, branche `story/<id>`, hors du dépôt.
`git worktree list` est la seule source de vérité sur les stories ouvertes.

**Où tourne `deliveryctl`.** Dans un projet, c'est toujours `.delivery/deliveryctl` : le shell de
l'humain (un alias suffit), la CI, les tâches planifiées. Dans une session Claude du
projet, le hook `SessionStart` met `.delivery/` en tête du `PATH` (via `$CLAUDE_ENV_FILE`), si bien
que `deliveryctl` y est la copie du projet, en local comme dans le cloud ; les hooks du projet
l'appellent par son chemin. Le `deliveryctl` du plugin (`bin/`) n'est qu'un lanceur : il exécute la
copie du projet si elle existe, celle du plugin hors de tout projet ; `init` et `init --upgrade`
exécutent celle du plugin. Appelé pour un hook sans Python 3.11 ou plus, il rend la main en
silence.

Dans une session cloud (`CLAUDE_CODE_REMOTE=true`), le moteur est cette même copie du projet, avec
Python 3.11 de l'image : la fenêtre est `terminal`, sans sonder herdr ; il n'y a ni réglages de
machine, ni commande de notification, ni plugin, et `doctor` ne vérifie pas ces points (§12.1).
`templates/project/cloud-setup.sh` (copié sous `.delivery/templates/`) est le script d'installation
de l'environnement cloud : il ajoute `just` et le navigateur Playwright de la recette, rien de ce
que l'image contient déjà.

**La méthode dans le projet.** `init` copie les agents, skills et commandes du plugin sous
`.claude/` et inscrit leur empreinte dans `.delivery/method.json`. Les commandes y sont
`/spec-frame`, `/impl-frame`, `/run-campaign`… sans espace de noms (`run` aurait pris le nom d'une
commande native de Claude Code ; `init` reste `/delivery-method:init`). `init --upgrade` rafraîchit
la copie, retire les fichiers que la nouvelle version n'a plus, et refuse, avant d'écrire quoi que
ce soit et en listant les fichiers, d'écraser un fichier copié dont l'empreinte ne correspond plus
au manifeste (modifié à la main). Un premier `init` voit un fichier différent à un chemin de copie
comme un conflit. Les sessions de rôle du moteur lancent l'agent de cette copie, si bien qu'il n'y
a qu'une source par projet. Le `hooks/hooks.json` du plugin ne sert qu'aux sessions hors d'un
projet équipé.

## 3. `delivery.toml`

```toml
repo_role = "impl"             # single | spec | impl
content_language = "fr"
release_stage = "pre-release"  # pre-release | released — humain seulement
external_contracts = []        # détenteurs externes d'un état ou d'une API — humain seulement
forge = "github"               # github | gitlab ; toute story passe par une demande de fusion
integration = "human"          # human | ai
implementer = "cloud"          # cloud | local ; défaut : cloud avec forge = github, local avec gitlab
max_in_flight = 3              # plafond des stories que le lead peut mener à la fois (§12.4) ; défaut : 3
agent_prefix = "tk"            # noms de session : <prefix>-<id>-<role>
port_prefix = 31               # 10 à 64 ; port d'une story : <port_prefix><numéro sur 3 chiffres>, ou le suivant libre

[commands]                     # substitutions : voir sous ce bloc
check = "just check"                       # lint, build, tests unitaires et d'intégration ; jugé sur son code de sortie
test = "just test {selector}"              # facultatif, permis aux rôles : un test ciblé (travail en cours, morsure)
acceptance = "just acceptance {grep}"      # tests d'IHM Playwright ; {grep} = @<story de spec> ou vide (suite complète)
serve = "just serve {port}"                # lance l'application d'une story

[permissions]
extra_allow = []               # règles ajoutées aux fichiers de rôle, par exemple "Bash(./gradlew *)"

[levers]                       # vide par défaut ; toute clé écrite ici est visible en revue
```

**Substitutions.** Le moteur substitue `{grep}` et `{port}` dans ce qu'il lance (`verify`, suite
de nuit) et exporte `DELIVERY_PORT` ; les rôles substituent `{selector}`, et
`{port}` par la valeur de `DELIVERY_PORT`, présente dans leur session. Le port d'une story lui est
réservé de `story open` à `story close` ; la suite de nuit prend `<port_prefix>999`, ou le suivant
libre. La CI posée par `init` substitue `{grep}`, et `{port}` par `DELIVERY_PORT` (3999 par défaut).

| Levier | Défaut | Effet |
|---|---|---|
| `review_loops` | `2` | corrections après une relecture `no` avant l'arrêt `review-exhausted` |
| `verify_attempts` | `3` | corrections après une vérification `fail` avant l'arrêt `verify-exhausted` |
| `short_path_max_lines` | `50` | taille visée d'un changement en voie courte (§7.3) |
| `stall_minutes` | `20` | minutes sans avancée avant l'alerte « agent bloqué » (§9.3) |
| `reinforced_risks` | `{authz = ["bite", "adversarial-review"], data-write = ["adversarial-review"], file-upload = ["adversarial-review"], data-leak = ["adversarial-review"]}` | contrôles automatiques par risque ; une clé écrite remplace le défaut de ce seul risque, les autres risques gardent le leur ; une clé nouvelle déclare un risque propre au projet ; une liste vide retire ses contrôles (risque noté au compte rendu) |
| `doc_globs` | `["docs/**", "*.md"]` | un diff entièrement dans ces chemins se vérifie par `check` seul |
| `max_order_lines` | `60` | `story open` avertit au-delà, sans refuser |

Une clé inconnue fait échouer toute commande. La branche cible se déduit de `origin/HEAD` ; à
défaut, de la branche cible fournie par la CI (`GITHUB_BASE_REF`,
`CI_MERGE_REQUEST_TARGET_BRANCH_NAME`) ; sinon `main`, puis `master`.

**`implementer`** : où tourne le `story-implementer` (§11.1). `cloud` : une session cloud de
Claude Code, qui continue quand la machine dort ; `local` : une session locale comme les autres
rôles. Les autres rôles et la vérification restent locaux. Défaut : `cloud` avec `forge =
"github"`, `local` avec `gitlab` ; `cloud` avec `gitlab` fait échouer le chargement (une session
cloud ne pousse que sur GitHub). `init` écrit la clé.

Le dépôt a un remote `origin` sur GitHub ou GitLab ; `init` refuse un dépôt sans `origin`. Il
n'y a pas de fusion locale : une story, une recette ou une suite de nuit passe toujours par une
demande de fusion.

## 4. Réglages de machine

```toml
# ~/.config/delivery-method/machine.toml
window = "auto"                # auto | herdr | terminal ; auto = herdr s'il répond en moins de 5 s
notify_cmd = ""                # commande appelée avec deux arguments (titre, message) ; vide = message sur la sortie d'erreur du moteur ;
                               # en échec : « [notification failed: <erreur>] <titre> — <message> » sur la sortie d'erreur, sans nouvel essai
notify_story_end = false       # true : un toast à chaque story fusionnée, en plus du §13
journal_dsn = ""               # postgresql://… ; vide = la file locale est le journal
plugin_dir = ""                # racine du plugin, si le moteur ne la trouve pas seul
```

`DELIVERY_WINDOW` dans l'environnement remplace `window` pour une commande.

## 5. Cartes

Un fichier par carte dans `backlog/`, nommé `<id>-<slug>.md`. Identifiant : `s<nnn>` (story, même
numéro que la story de spec), `t<nnn>` (tâche), `a<nnn>` (anomalie).

```markdown
---
id: s004
kind: story            # story | task | anomaly
title: Partager une liste   # obligatoire : titre court, quelques mots (3 à 8 visés)
status: draft          # draft | ready | to-triage | deferred | dropped
depends_on: []         # identifiants de cartes
risks: [authz]         # authz | data-write | file-upload | data-leak | migration | api-contract | new-screen | scheduling | realtime | dependency, plus les risques déclarés dans reinforced_risks
spec: s004             # identifiant de story de spec s<nnn> : obligatoire pour une story ; pour une anomalie, la story visée par le test en échec ; facultatif pour une tâche
code: true             # false pour une carte sans code (doc, chapeau)
show_plan: false       # true : l'exécutant s'arrête sur son plan (§7.3)
found: ""              # anomalie seulement : <où>@<commit>, par exemple 0.2.0/Q17@9c1e2a4
---
## Objective
## Context and scope
## Oracle
## Technical notes
```

**Titre court.** `title:` est obligatoire. `cards lint` refuse une carte sans titre, et une carte
`ready` dont le titre est resté un gabarit (`<titre court>`) :
`title: a short title is required`. Au-delà de 60 caractères, il note le titre sans le refuser.
Le titre dit en quelques mots ce que l'utilisateur ou l'équipe obtient, ou le défaut constaté ;
une carte de story reprend l'identifiant et le titre de sa story de spec. Il donne la référence
lisible de la carte (§1). Le moteur lit les titres sur la branche cible : une carte qui n'y est
pas encore se nomme par son identifiant seul.

**Carte `ready`** : exécutable par un agent de gamme moyenne sans question ni décision.
- `## Objective` et `## Context and scope` non vides ; fichiers, routes ou composants nommés.
- `## Oracle` obligatoire si `code: true` : les critères fonctionnels sont un renvoi à la story
  de spec, jamais une copie ; l'Oracle ajoute les mesures propres à l'implémentation, chacune
  avec son seuil, puis une ligne `Not tested by this card:`. Il est figé une fois la carte prête.
- Dépendances connues, sans cycle.

**GO** : un lead écrit ses cartes en `draft` ; le passage en `ready` est un commit du decision
owner, et il compte quand il est sur la branche cible. Le run ne lit que les cartes de la
branche cible. Une anomalie naît en `to-triage` et n'est pas exécutable avant le tri (§15.4).

**Carte faite** : la branche cible contient un commit de fusion dont le sujet nomme
`story/<id>` ou qui porte le trailer `Story: <id>`, ou la demande de fusion de `story/<id>` est
fusionnée sur la forge.

## 6. Dossier de story

`docs/stories/<id>/`, sur la branche `story/<id>`. Chaque fichier a un auteur unique.

| Fichier | Auteur | Rôle |
|---|---|---|
| `order.md` | `technical-lead` (brouillon dans `docs/campaigns/work/`), commité par le moteur | ordre de travail ; seul fichier du premier commit de la branche |
| `plan.md` | `story-implementer` | tâches à cocher ; absent en voie courte |
| `report.md` | `story-implementer` | compte rendu ; se termine par `Outcome:` |
| `verification.md` | moteur | verdict de vérification (§7.1) |
| `review.md` | `story-reviewer` | constats, contrôles renforcés, verdict de relecture |
| `spec-question.md` | `story-implementer` | question produit non tranchée (story différée) |
| `work/` | rôles ; moteur pour `verify.log` | état de travail, ignoré par git |

Un verdict ne compte que s'il est écrit par son auteur : ligne `By:` et trailer `Agent:` du commit
qui l'écrit (`engine` pour `verification.md`, `story-reviewer` pour `review.md`). Le moteur tient
dans `.delivery/run/verdicts.json` ses commits de vérification et ses lancements de relecteur
(arbre relu, tête de lancement) ; il ignore une vérification absente de ce registre et une
relecture qui ne suit pas un lancement de relecteur sur son arbre. Sans ce fichier (CI, clone
neuf), seul le contrôle `By:` et `Agent:` vaut. Les permissions refusent à l'exécutant l'écriture
de `verification.md` et de `review.md`, au relecteur celle de `verification.md` (§11.1).

### 6.1 Ordre de travail — `order.md`

```markdown
---
id: s004
campaign: <nom>
issued-by: technical-lead
base: <commit de la branche cible où les faits ont été lus>
path: plan                  # plan | short (§7.3)
---
## Objective            une phrase ; le résultat observable attendu
## Decisions            décisions du decision owner, citées mot pour mot, avec leur date ; « none »
## Proposal             solution suggérée et sa raison ; l'exécutant peut s'en écarter en le disant
## Constraints          périmètre, fichiers à ne pas toucher, suite prévue à ne pas commencer
## Read at base — re-verify, do not trust
                        - <fait> (<chemin:ligne>, read | measured | inferred)
## Reinforced checks    par risque de la carte : contrôle dû et invariant visé ; « none »
## Deliverables         un livrable par ligne, avec sa preuve attendue (commande → résultat)
```

Un fait qui dépend d'une carte pas encore fusionnée n'entre pas dans un ordre : l'ordre attend la
fusion (§12.4).

### 6.2 Plan — `plan.md`

Une liste `- [ ] …` ; l'exécutant coche une case par tâche terminée et commitée. Une session
reprise recommence à la première case non cochée.

### 6.3 Compte rendu — `report.md`

```markdown
## Delivered            fichiers et commits, une ligne chacun
## Deviations           écarts à l'ordre, tranchés et motivés
## Verified points      chaque ligne de « Read at base » : confirmed | refuted | not checked, avec la preuve
## Oracle               chaque ligne de l'Oracle : mesure (measured) ou « not measured — <raison> »
## Proof                commandes jouées et résultats
## Findings             constats hors périmètre : fait, preuve, severity (blocking | to-decide | note) ; obstacles et refus de permission rencontrés
## For the decision owner   options et recommandation, ou « none »
Outcome: done — <résumé en une ligne>
```

Une session de correction réécrit `report.md` (écarts et preuves de la correction) et le
recommite avec une nouvelle ligne `Outcome:`.

### 6.4 Relecture — `review.md`

`## Findings` : constats numérotés, chacun avec un titre court (`1. <titre court> — …`), sa
preuve (`chemin:ligne` ou commande), sa phrase de matérialité (« ce qui casse si on ne le
corrige pas ») et sa sévérité (`blocking`, `to-decide`, `note`). `## Reinforced checks` : une
ligne par contrôle de l'ordre et par doute nommé :
`bite: <invariant> — bit | did not bite — <commande>` ou
`adversarial-review: <angle> — <résultat>`. Puis le bloc de verdict (§7.1). À partir de la
deuxième boucle, le relecteur ne revoit que les corrections.

### 6.5 Question produit — `spec-question.md`

Le problème en une phrase, ce que la spec dit (renvoi), les options avec leur conséquence, une
recommandation. La story finit en `Outcome: deferred`. Aucun rôle n'écrit dans le dépôt de spec :
l'humain porte la question au cadrage suivant.

### 6.6 Ce que ne contient pas un dossier de story

Aucune décision de méthode, aucune leçon générale, aucun récit : les écarts vont dans
`## Deviations`, les leçons au journal (§13) par l'humain.

### 6.7 État de travail — `work/`

Créé vide par le moteur. Contenu libre : `notes.md` (où j'en suis, réécrit à chaque case cochée
et avant l'`Outcome:`), relance de la pile locale, sondes. `verify.log` y reçoit la sortie de
`verify` en continu. Il survit à un crash de session et à un redémarrage de machine ; il
disparaît avec la copie de travail. Ce n'est jamais une preuve.

## 7. Verdicts

### 7.1 Bloc de verdict

Les dernières lignes d'un fichier de verdict, une clé par ligne, dans cet ordre :

```
Verdict: pass                     # vérification : pass | fail ; relecture : yes | no ; recette : accepted | accepted-with-reserves | rejected
Tree: 3f9a0c1e…                   # identifiant d'arbre de code relu (§7.2), 40 caractères
Command: just check && just acceptance @s004
Result: check exit 0; acceptance exit 0, 12 passed; 2m41s
By: engine                        # engine | story-reviewer | qualification-lead
Evidence: docs/stories/s004/verification.md   # facultatif, répétable ; chemin commité
```

Un verdict est invalide si une ligne manque, si `Evidence:` désigne un chemin absent de l'arbre
ou hors du dépôt (dossier temporaire compris), si `Tree:` n'est pas l'arbre relu, ou si `By:`
n'est pas l'auteur du fichier (§6).

**Vérification** (`deliveryctl verify`) : `check` est jugé sur son seul code de sortie. Les tests
d'IHM tournent avec `{grep} = @<spec>` de la carte et le port de la story (§3) ; une carte sans
`spec:`, avec `code: false`, ou dont le diff reste dans `doc_globs`, se vérifie par `check` seul
et `Result:` le dit (`acceptance: not run — <raison>`). Quand les tests d'IHM tournent, 0 test
exécuté vaut `fail`.

### 7.2 Identifiant d'arbre de code

`Tree:` est l'empreinte SHA-1 des entrées de `git ls-tree -r -z --full-tree <commit>` (séparées
par NUL, chemins jamais cités), privées de celles dont le chemin commence par `docs/stories/`,
jointes par NUL. Écrire un compte rendu ou un verdict ne change pas l'arbre ; toute modification
de code le change.

### 7.3 Voie courte et plan montré

L'ordre porte `path: short` quand la carte n'a aucun risque, que le changement attendu reste
sous `short_path_max_lines` lignes, sans schéma de données ni API modifiés : l'exécutant code
depuis l'ordre, sans `plan.md`. Vérification, relecture neuve et demande de fusion sont
conservées. Si le changement dépasse ce qui était prévu, l'exécutant écrit un `plan.md` et le
dit dans `## Deviations`.

Une carte `show_plan: true` interdit la voie courte : l'exécutant commite `plan.md` avant tout
code et finit sur `Outcome: plan-ready`. L'humain lit le plan, puis relance par
`deliveryctl story next <id> --go` ou modifie l'ordre.

### 7.4 Ligne `Outcome:`

`Outcome: <done|blocked|deferred|plan-ready|question> — <raison en une ligne>` : dernière ligne
non vide de `report.md` et du dernier message de la session. Un rôle sans surveillance ne pose
jamais de question : il tranche et documente, ou il diffère ; `question` n'existe que dans une
session humaine.

## 8. Commits

- **Commit d'un rôle** : message au présent, corps proportionné à la surprise du changement,
  toute carte nommée par sa référence lisible (§1) ; trailers `Story: <id>` et `Agent: <role>`
  (un lead : `Campaign: <nom>` et `Agent: <role>`). Report d'une carte par le lead : sujet
  `defer <id> : <titre>`, jamais `story/<id>` (§5, carte faite).
- **Commit du moteur** : trailers `Story: <id>` (ou `Campaign: <nom>`) et `Agent: engine` ;
  sujets `order <id> : <titre>` et `verify <id> : <titre> — pass|fail`.
- **Commit de recette** : `Campaign: qualification-<incr>` (la nuit : `Campaign: nightly-<jour>`) et
  `Agent: <role>` ; jamais de trailer `Story:`.
- **Fusion par `deliveryctl merge`** : fusion par commit de fusion (jamais squash ni rebase) de
  la tête contrôlée ; sujet `Merge story/<id> : <titre>` ; trailers `Story: <id>`,
  `Spec: <id>@<version>#<blob court>` (ou `none`), `Approved-By: <email humain | story-reviewer>`,
  `Delivery-Method: <version>`. Une fusion faite dans la forge est admise ; sa traçabilité passe
  par la demande de fusion, dont le titre est `<id> : <titre> (story/<id>)` et le corps commence
  par `# <id> : <titre>`.

- **Lecture des trailers** : le moteur lit les trailers d'un commit (`Story`, `Agent`,
  `Claude-Session`, `Version-Override`…) dans tous les paragraphes consécutifs en fin de message
  faits seulement de lignes de trailer (`Clé: valeur`) ; un trailer peut donc se trouver dans
  n'importe lequel de ces paragraphes, par exemple sous celui qu'ajoute une session Claude Code.
  Le premier paragraphe (le sujet) et un paragraphe de prose ne sont jamais lus comme trailers.

## 9. États d'une story

Tous déduits des fichiers commités (HEAD de `story/<id>`) et de la forge, jamais d'un
multiplexeur ni d'une mémoire. Évalués dans cet ordre ; la première ligne vraie l'emporte.

| État | Condition | Suite enchaînée par le moteur |
|---|---|---|
| `merged` | carte faite (§5) | fermer la copie de travail |
| `prepared` | copie de travail sans commit sur la base | attendre `story open` |
| `submitted` | relecture `yes` pour l'arbre courant, tête poussée avec demande de fusion ouverte | `integration = ai` : fusionner quand la CI est verte (au moins un contrôle, tous réussis) ; sinon notifier ⚠ |
| `ready-to-submit` | relecture `yes` valide pour l'arbre courant | `deliveryctl submit`, puis la suite de `submitted` dans le même pas ; contrôle d'intégration rouge : notifier ⚠ |
| `blocked`, `deferred`, `plan-ready` | `Outcome` frais valant `blocked`, `deferred` ou `plan-ready` | notifier ⚠, s'arrêter |
| `verify-exhausted`, `review-exhausted` | correction ou relecture due mais borne atteinte (Bornes, ci-dessous) | notifier ⚠, journal, s'arrêter |
| `fixing` | dernier verdict `fail` ou `no`, sans `Outcome` frais après lui | lancer ou relancer l'exécutant en correction |
| `implementing` | pas d'`Outcome` frais | lancer ou relancer l'exécutant |
| `to-verify` | `Outcome: done` frais, pas de vérification pour l'arbre courant | `deliveryctl verify` |
| `to-review` | vérification `pass` pour l'arbre courant, pas de relecture valide pour cet arbre | lancer un `story-reviewer` neuf |

**`Outcome` frais** : le dernier commit de `report.md` est postérieur au dernier verdict `fail`
ou `no`, et aucun commit postérieur à lui ne change l'arbre de code.

La forge est interrogée même quand la branche distante a disparu (supprimée à la fusion) : une
demande de fusion fusionnée donne `merged`. Forge ou dépôt distant injoignable : `ready-to-submit`
sans suite, détail `forge unreachable: retry` ; le balayage suivant réessaie.

**Bornes** : N_fail compte les commits du moteur de `verification.md` dont le verdict vaut
`fail` depuis la base ; N_no, les commits de `review.md` valant `no` ou sans verdict valide (bloc
absent ou invalide, `Tree:` autre que l'arbre du commit, auteur autre que `story-reviewer`). Une
correction est due tant que N_fail ≤ `verify_attempts` (resp. N_no ≤ `review_loops`) ; une
relecture invalide ne demande pas de correction, elle relance un relecteur neuf, sous la même
borne. Un même arbre de code reçoit au plus `review_loops` + 1 relecteurs : si aucun n'a rendu de
verdict valide, `review-exhausted`.

### 9.1 Sessions de rôle

Une session de rôle ne se reprend jamais : `deliveryctl story next <id>` en lance une neuve,
qui lit `order.md`, `plan.md`, `work/notes.md` puis `git status`. Le moteur ne lance jamais un
rôle dont une session de la story est vivante ; il ferme une session inactive dont le livrable
est écrit avant d'enchaîner. Vivante : la session figure dans `claude agents` (ou son processus
existe) ; une session dont la fenêtre ne sait pas dire si elle vit (par exemple, qui démarre)
compte comme vivante. Chaque entrée du registre (`.delivery/run/sessions/<id>.json`) porte
`window`, la fenêtre qui la détient (`cloud`, `herdr`, `terminal`), et c'est cette fenêtre que le
moteur interroge, non celle de la machine. Une entrée `cloud` porte aussi `session_id`, `url`
(sans paramètres), `head` (le commit poussé) et `pushed_at` ; elle est vivante tant qu'elle n'a
pas de champ `ended`. Une session cloud ne s'arrête pas d'ici (`stop_role` ne fait rien), et le
moteur n'en lit la progression qu'en rapatriant ses commits (ci-dessous) : elle prend fin quand
ses commits sont acceptés et que `report.md` porte un `Outcome` frais (§9), quand ils sont
refusés, ou par `story next --relaunch` (§12.1) ; chaque fin pose `ended` et sa raison
(`ended_reason` : `outcome`, `refused`, `abandoned`). Le moteur ne lance jamais un second
exécutant tant que l'entrée n'a pas de `ended` : deux sessions ne travaillent jamais sur une
même story. `story status` en montre l'URL.

**Rapatriement des commits du cloud.** La session cloud pousse son travail sur sa propre branche
`claude/<nom>`, créée depuis `story/<id>`, et chacun de ses commits porte le trailer
`Claude-Session: https://claude.ai/code/session_<id>`. Pour une story dont l'entrée `story-implementer`
est `cloud` sans `ended`, le moteur récupère `origin` (dont `+refs/heads/claude/*`), au plus une
fois par minute et par story (l'heure est dans l'entrée), avant de lire l'état dans `story next`,
à chaque tour de `story wait`, dans le balayage et dans `story status`. Un échec de réseau ou de
forge s'affiche et le balayage continue. Les candidats sont `origin/story/<id>` et chaque
`origin/claude/*` dont la pointe descend de `head` de l'entrée et dont tous les commits après `head`
portent le trailer `Claude-Session:` de cette session ; le candidat qui a le plus de ces commits
l'emporte ; rien de neuf : rien ne se passe.

*Contrôle à la réception*, sur `head..pointe`, avant que rien n'entre dans la copie de travail :
une session cloud n'obéit à aucune règle de permission du rôle, et l'auteur d'un verdict se
déclare par un trailer que l'exécutant pourrait écrire lui-même. Refus si la plage contient un
commit de fusion ; si la pointe ne descend pas de la tête locale de la story ; si un commit n'a pas
les trailers `Story: <id>` et `Agent: story-implementer` (§8) ; si le diff touche `verification.md` ou
`review.md` de la story, un chemin protégé du contrôle d'intégration, le dossier d'une autre story,
ou `backlog/` autrement que par des cartes d'anomalie à trier ajoutées (les règles 4 et 5 de §10,
les mêmes fonctions).

*Accepté* : la copie de travail de la story, qui doit être propre, avance en avance rapide
jusqu'à la pointe (sinon elle reste en l'état, la raison s'ajoute au détail de la story et le
balayage suivant réessaie) ; l'entrée reçoit le nouveau `head` et l'heure du dernier commit
(`last_commit_at`) ; la branche `claude/*` distante, si elle était le candidat, est supprimée. Si
`report.md` porte alors un `Outcome` frais, l'entrée reçoit `ended` : l'exécutant a fini, la story
s'enchaîne.

*Refusé* : aucune avance rapide ; l'entrée reçoit `ended` et `rejected` (les problèmes) ; la story
est `blocked`, les problèmes en détail, et le prochain geste humain nomme la branche à inspecter et
la relance (`story next <id> --relaunch`) ; une notification ⚠ « commits du cloud refusés » ; un
événement `refusal` du journal (§13) dont la preuve est la branche et l'URL de la session.

*Ce qui se perd* : les refus de permission d'un exécutant cloud n'atteignent pas le journal ; son
transcript reste dans le cloud. Ses obstacles ne se lisent que dans `report.md`.

L'exécutant relancé après une session du même pas finie sans `Outcome`
(crash, arrêt, tour perdu) est une reprise, portée au journal (`resume`).

### 9.2 Enchaînement

`deliveryctl hook stop` n'agit que dans une session de rôle, sauf la question d'une session
humaine (ci-dessous), et rend la main aussitôt. Il lit l'`Outcome:` sur la dernière ligne non vide
du dernier message de la session :
- présent : pour l'exécutant et le relecteur, il lance en détaché `deliveryctl story next <id>`
  puis un balayage des stories ouvertes ; pour le `technical-lead`, seuls `done` (notification ⭐
  « run terminé ») et `blocked` (notification ⚠ « run arrêté ») terminent le run, tout autre
  `Outcome` vaut absent ; pour le `qualification-runner` d'une recette, notification ⚠
  « résultats à synthétiser » (la suite de nuit notifie seule, §16) ;
- absent au premier arrêt : il bloque l'arrêt avec la consigne « finish your work, then end your
  last message with the exact Outcome line your 'Ends with' section gives » (le
  `technical-lead` : `Outcome: done` ou `Outcome: blocked`) ; pour le `story-reviewer`, un
  `review.md` non commité, modifié depuis son commit, sans bloc de verdict valide ou dont `Tree:`
  n'est pas l'arbre de code courant bloque aussi le premier arrêt, avec la liste des problèmes ;
- absent au second arrêt : il ne fait rien ; la détection du §9.3 prend le relais.

Il porte au journal (`refusal`), une seule fois, les refus de permission du transcript de la
session. Dans une session humaine, un arrêt dont la dernière ligne non vide est
`Outcome: question` envoie la notification ⚠ « décision attendue », une par message.

**Dans une session cloud** (`CLAUDE_CODE_REMOTE=true`, sans `DELIVERY_ROLE`), le hook n'enchaîne
jamais et ne notifie jamais : le moteur de l'ordinateur du propriétaire reprend le travail depuis
la branche poussée. La session sert une story quand le premier commit de sa branche après la
base commune avec la branche cible ajoute seulement `docs/stories/<id>/order.md` (première règle
du §10). Quand la branche cible ou la base commune est introuvable (un clone cloud qui ne porte que
la branche de la story, sans `origin/HEAD` ni `main`), la session sert la story du commit d'ordre
le plus récent de l'historique de `HEAD` : sujet `order <id>`, trailer `Agent: engine`, et
`docs/stories/<id>/order.md` pour seul fichier ; sans un tel commit, aucune story. Dans ce cas, au premier arrêt, le hook bloque si le dernier message ne finit pas par une
ligne `Outcome:`, si `docs/stories/<id>/report.md` a des modifications non commitées, ou si la
branche a des commits que son amont n'a pas (ou n'a pas d'amont) ; la raison dit quoi faire
(commiter le rapport, `git push -u origin HEAD`, finir par la ligne `Outcome` de la section
« Ends with » de l'agent). Au second arrêt, il laisse finir. Hors d'une session de story, il se
comporte comme dans une session humaine, sans la notification.

`deliveryctl hook session-start` tourne à chaque démarrage de session (démarrage, reprise,
`clear`, compaction), lit la `source` dans l'entrée du hook et reste silencieux et rapide en cas
d'erreur. Toujours : si `$CLAUDE_ENV_FILE` est défini, il y ajoute
`export PATH="<racine du projet>/.delivery:$PATH"` (§2). Dans une session cloud sur une story, pour les sources `startup` et `resume`, il rappelle que la
session est le `story-implementer` de la story `<id>` : lire `.claude/agents/story-implementer.md`,
puis `order.md`, `plan.md` et `work/notes.md` de la story quand ils existent, puis `git status`.
Seulement pour la source `compact`, dans
une session de rôle, le hook de reprise réinjecte « re-read
order.md, plan.md, work/notes.md, then git status » (le `qualification-runner` :
`qualification/order.md`, `qualification/work/notes.md` ; le `technical-lead` : les sections
`## Next` et `## Run` de sa campagne, puis `deliveryctl story status`).

### 9.3 Détection

`story wait`, `story status --watch` et `hook stop` balaient les stories ouvertes. Une session
vivante sans avancée depuis `stall_minutes` déclenche une seule alerte 🚨 et un événement
`stall` ; avancée = le plus récent de son transcript, de son journal de sortie, du dernier commit
de la branche et des fichiers de `docs/stories/<id>/`. Pour un exécutant cloud, avancée = le plus
récent de `pushed_at` et de l'heure de son dernier commit rapatrié (`last_commit_at`) ; passé
`stall_minutes`, une seule alerte 🚨 (`… — bloqué`, avec l'URL de la session) et un événement
`stall`, comme pour une session locale. Une story dont l'état appelle une suite
et qu'aucune session ne sert est relancée par ces mêmes balayages. Une erreur passagère sur une
story (forge, réseau) est affichée et le balayage continue.

## 10. Contrôle d'intégration — `deliveryctl gate <id> [--head <rev>]`

Porte sur la tête de `story/<id>` (par défaut HEAD de sa copie de travail ; en CI, le sha de
tête de la demande de fusion, jamais le commit de fusion synthétique), avec l'historique complet.
Tous les points sont bloquants :

1. Le premier commit depuis `git merge-base <cible> <tête>` n'ajoute que `docs/stories/<id>/order.md` ;
   `report.md` se termine par `Outcome: done`.
2. `verification.md` : verdict `pass` valide, `Tree:` égal à l'arbre de code de la tête,
   `By: engine` et dernier commit du fichier portant `Agent: engine`.
3. `review.md` : verdict `yes` valide, même `Tree:`, `By: story-reviewer` et dernier commit du
   fichier portant `Agent: story-reviewer`.
4. Le diff ne touche ni `spec/`, ni `spec.lock`, ni `.delivery/`, ni `.claude/`, ni
   `delivery.toml`, ni aucun `CLAUDE.md`, ni le dossier d'une autre story, ni un `work/`.
5. Dans `backlog/`, le diff n'ajoute que des cartes `kind: anomaly` en `to-triage`.
6. Aucune ligne `Evidence:` ne désigne un chemin absent de l'arbre.

**CI d'une demande de fusion** (posée par `init`) : sur une branche `story/<id>`, `check` et
`acceptance @<spec>` sur le résultat de fusion, puis `gate <id> --head <sha de tête>`. Sur toute
autre branche, `check` seul ; l'approbation humaine tient lieu de contrôle. Sans CI qui tourne sur
les demandes de fusion, aucune n'est jamais verte : `doctor` le signale.

## 11. Rôles

| Rôle | Phase | Session | Défaut (frontmatter) | Ne fait jamais |
|---|---|---|---|---|
| `product-analyst` | spec | humaine | opus, high | trancher une question produit ; choisir une technique |
| `spec-reviewer` | spec | sous-agent | sonnet, high | corriger |
| `refuter` | spec, qualification | sous-agent | sonnet, high | proposer un correctif |
| `technical-lead` | impl | humaine (cadrage) ; de rôle (run) | opus, high | écrire du code ; écrire dans une copie de story autre chose qu'un ordre |
| `story-implementer` | impl | de rôle | sonnet, medium | poser une question ; approuver ; pousser (sauf, dans une session cloud, sa propre branche de travail) |
| `story-reviewer` | impl | de rôle, toujours neuve | opus, high | commiter une modification de code |
| `qualification-lead` | qualification | humaine | opus, high | corriger le produit |
| `qualification-runner` | qualification | de rôle, jetable | sonnet, medium | corriger le produit ; pousser |

Rédacteur et relecteur ne sont jamais la même session. Les leads ne se parlent pas : ils passent
par les fichiers du dépôt. La messagerie entre sessions est refusée dans le
`.claude/settings.json` du projet (levier : l'humain retire la ligne). Une équipe sans un modèle
le remplace par les variables d'environnement de Claude Code dans ce même fichier.

### 11.1 Lancement d'une session de rôle

```
claude --agent <role> \
       --permission-mode dontAsk --setting-sources project \
       --settings <main>/.delivery/run/roles/<portée>-<role>.json --session-id <uuid> "<consigne>"
```

`<role>` est l'agent de la copie du projet, `.claude/agents/<role>.md` de la copie de travail du
rôle (absent : erreur de précondition qui nomme `deliveryctl init --upgrade`) ; aucun plugin n'est
passé à la session. `<portée>` est l'identifiant de la carte, `lead` pour le run, ou l'incrément
recetté. Le moteur met aussi `<copie de travail>/.delivery` en tête du `PATH` de l'environnement
du lancement, que chaque fenêtre transmet : `deliveryctl` y est la copie du projet même si le hook
`SessionStart` n'a pas tourné. Le fichier de rôle, généré par le moteur, porte `"env":
{"DELIVERY_ROLE": …, "DELIVERY_STORY": …}`, plus
`DELIVERY_PORT` pour les rôles d'une story : la
session, ses hooks et son outil Bash en héritent,
quel que soit le lanceur. Ses règles de chemin
sont absolues (`//<chemin>/…`).

**Exécutant dans le cloud** (`implementer = "cloud"`, §3). Chaque lancement du `story-implementer`
(implement, resume, fix, plan first, approved plan) est un lancement cloud, fenêtre `cloud` quelle
que soit la fenêtre de la machine :

```
git push --set-upstream origin story/<id>
claude --cloud "<consigne>" --model <modèle> --effort <effort>     # depuis la copie de travail, dans un pseudo-terminal
```

Le lancement surveille la sortie de `claude --cloud` : dès qu'elle montre le dialogue de confiance
(« Is this a project you created or one you trust? »), le moteur arrête le processus et échoue
aussitôt, avec le code 3 (précondition), en nommant le dossier et le remède (lancer `claude` une
fois dans la copie principale du dépôt et accepter le dialogue, dont héritent les copies de travail
des stories, ou faire confiance au dossier de ces copies).

Un push refusé (la branche distante a divergé) échoue avec le code 5 et le message de git. Modèle
et effort viennent de l'en-tête de `.claude/agents/story-implementer.md` (`sonnet` et `medium` à
défaut). La commande, qui refuse de tourner sans terminal interactif, rend la main aussitôt avec
`Created cloud session`, `View: <url>` et `Resume with: claude --teleport <id>` ; le moteur lit
l'identifiant et l'URL (sans paramètres) sur la ligne `View:` ; un code de sortie non nul ou
l'absence de cette ligne échoue avec le code 5 et la sortie. La consigne se suffit, la session
n'ayant ni `--agent` ni fichier de rôle :

```
You are the story-implementer of this repository: read .claude/agents/story-implementer.md and follow
it as your instructions. Story <carte> — read docs/stories/<id>/order.md and carry it out. Mode: <mode>.
Where: cloud — use port <port> wherever DELIVERY_PORT or <port> is asked.
```

Dans la session cloud, l'exécutant pousse sa branche de travail (`git push -u origin HEAD`) après
avoir commité `report.md` et après tout commit ultérieur ; il ne pousse aucune autre branche et
n'ouvre aucune demande de fusion ; trailers et ligne `Outcome` sont inchangés (§9.2 pour le hook).

La session cloud ne reçoit ni fichier de rôle (`--settings`, `--permission-mode`), ni variable
d'environnement du moteur, ni plugin, ni fichier local : le dépôt à la branche poussée seulement.
Elle travaille sur sa propre branche `claude/<nom>`, créée depuis `story/<id>`, et ne peut pousser
que celle-ci ; ses commits portent `Claude-Session: <url>`. Elle tourne dans l'environnement par
défaut choisi par `/remote-env` dans Claude Code.

**Socle commun** : lecture du dépôt, `git` en lecture, commandes de `[commands]` (dont `test`,
le test ciblé) et `extra_allow`, `deliveryctl story status` et `cards list|order|lint`. Refus :
`Agent`, `Workflow`, `SendMessage`, `Monitor`, `CronCreate`, `RemoteTrigger`, `PushNotification`,
`AskUserQuestion`, `WebSearch` ; l'écriture dans `spec/`, `.delivery/`, `.claude/`,
`delivery.toml`, `CLAUDE.md` ; la lecture de `~/.ssh/`, `~/.config/gh/`, `**/.env.secrets`, du
journal et des brainstormings archivés (`docs/maybe/`, outils de lecture et shell) ; `git push`, `git reset --hard`, `--no-verify`, `--amend`, `git commit -n`, les options
`--force` et `-f` de git, les écritures par `sort -o` et `git … --output` ; les gestes humains
(§12.1) ; toute commande du multiplexeur.

| Rôle | En plus du socle |
|---|---|
| `story-implementer` | écriture et commits dans la copie de sa story, sauf `verification.md` et `review.md` |
| `story-reviewer` | écriture dans la copie de sa story (morsure restaurée), sauf `verification.md` ; commit de `review.md` |
| `technical-lead` (run) | écriture dans `backlog/`, `docs/campaigns/`, et dans `docs/stories/*/order.md` d'une copie préparée ; commits sans push ; `deliveryctl story prepare\|open\|status\|wait\|next\|close` ; lecture par le shell des copies de stories (`<parent>/<dépôt>-wt`) |
| `qualification-runner` | écriture et commits dans `qualification/`, cartes d'anomalie dans `backlog/` ; conteneurs locaux ; `curl` ; exécution des scripts de `qualification/kit/` (`bash`, `sh`, `./`) |

Un refus injustifié se note dans le compte rendu ; l'humain complète `extra_allow`.

## 12. Gestes

### 12.1 Gestes humains

`deliveryctl init`, `run`, `merge` (en `integration = human`), `story next --go`, `story next --relaunch`, `story close`
d'une story arrêtée, `spec release`, `spec sync`, `qualify submit`, `nightly`, `note`, `journal report`. Refusés
quand `DELIVERY_ROLE` est défini ; en `ask` dans les réglages du projet, sauf `story close` : une
règle ne distingue pas une story arrêtée d'une story fusionnée, que le lead ferme en run, et le
moteur refuse à un rôle la fermeture d'une story arrêtée. Commits humains : passer
une carte en `ready`, taguer, pousser une branche de lead, passer en `released`, éditer
`external_contracts`, modifier les conventions du projet ou les permissions.

Dans une session cloud (`CLAUDE_CODE_REMOTE=true`), les gestes qui lancent des sessions Claude,
poussent, taguent ou fusionnent sur la forge, ou écrivent le journal du propriétaire sont refusés,
code 4, avec une ligne qui dit de les lancer depuis son ordinateur : `run`, `merge`, `submit`,
`story open`, `story next`, `story wait`, `qualify run`, `qualify submit`, `nightly`,
`spec release`, `init`, `note`, `journal report`. Les verbes qui lisent ou contrôlent et ceux qui
ne touchent que la copie de travail restent permis : `cards`, `story prepare|status|close`,
`verify`, `gate`, `campaign open`, `journal add|flush|setup`, `hook`, `spec lint|sync|verify`,
`qualify open|lint|close`, `doctor`, `kit`. Une session cloud livre par une demande de fusion de
sa branche `claude/<nom>` ; le geste refusé se lance après la fusion de cette demande. La liste de ces
gestes est unique dans le moteur : le hook `PreToolUse` du projet (`deliveryctl hook pre-tool`) la
lit aussi, et refuse la commande Bash qui en appelle un avant toute demande de permission, avec la
même ligne de refus, si bien que les règles `ask` n'ouvrent pas de demande qu'aucun humain ne
validerait.

### 12.2 Verbes du moteur

| Verbe | Effet |
|---|---|
| `init [--role R] [--upgrade]` | pose ou met à jour moteur, règles, copie des agents, skills et commandes sous `.claude/` (manifeste `.delivery/method.json`), réglages, CI, et pour un dépôt `spec` ou `single` sans `spec/`, un squelette de `spec/` ; n'écrase rien, ne commite rien |
| `doctor` | diagnostic en lecture seule (dans une session cloud, il le dit et saute réglages de machine, herdr, commande de notification, plugin et connexion `claude`, ne vérifie pas `gh auth status` (une note : le forge passe par le proxy GitHub de la session, les gestes de forge se font depuis l'ordinateur du propriétaire) et n'avertit pas d'un `origin/HEAD` absent, au plus une note), dont la copie de la méthode (manifeste, version, fichiers modifiés ou absents, plugin désactivé, hooks) et, avec `implementer = "cloud"`, la connexion `claude.ai` et `origin` sur github.com ; pour un `origin` sur github.com dont `gh repo view` dit le dépôt public, il avertit si l'adresse `git config user.email` ne finit pas par `@users.noreply.github.com` (elle est publiée dans chaque commit et dans le trailer `Approved-By` de chaque fusion), `ok` sinon, et ne dit rien si `gh` manque ou ne répond pas ; la confiance de Claude Code pour le dépôt est aussi vérifiée avec `implementer = "cloud"`, quelle que soit la fenêtre de la machine |
| `cards list`, `cards order`, `cards lint` | `list`, `order` : lire, ordonner les cartes de la branche cible, celles que lit le run ; `lint` : contrôler celles de la copie de travail, avant commit ; seules les cartes `ready` dont les dépendances sont faites sont lançables |
| `campaign open <nom> --phase P` | crée `docs/campaigns/<nom>.md` et son dossier `work/` |
| `run [--campaign N]` | lance le `technical-lead` en mode run |
| `story prepare <id>` | copie de travail depuis la tête de la cible, squelette d'ordre ; rien n'est commité |
| `story open <id> [--order <brouillon>]` | contrôle l'ordre, le commite, calcule le port, lance l'exécutant ; refuse si une dépendance n'est pas faite ou n'est pas contenue dans `base:` ; avertit au-delà de `max_order_lines` |
| `story status [<id>] [--watch]` | état, prochaine étape du moteur, prochain geste humain |
| `story next <id> [--go\|--relaunch]` | enchaîne la suite (§9) ; `--go` relance après `plan-ready` ; `--relaunch` abandonne l'exécutant cloud (sans `ended`, ou dont les commits ont été refusés : sinon code 3), pose `ended` (`abandoned`), porte un événement `resume` au journal et lance un nouvel exécutant depuis la tête locale |
| `story wait <id> [--timeout S] [--until merged]` | rend la main à un arrêt (`blocked`, `deferred`, `plan-ready`, bornes, `merged`, et `submitted` si `integration = human`) ou au délai (code 3) |
| `story close <id>` | supprime la copie de travail d'une story fusionnée ou arrêtée ; garde la branche d'une story arrêtée |
| `verify <id>` | lance les vérifications sur le port de la story, écrit `work/verify.log`, commite `verification.md` |
| `gate <id> [--head R]` | contrôle d'intégration (§10) |
| `submit <id>` | contrôle, pousse la branche, ouvre la demande de fusion ; refuse (code 3) une branche dont la demande de fusion est déjà fusionnée |
| `merge <id>` | fusionne une demande de fusion dont la CI est verte (au moins un contrôle, tous réussis ; sans contrôle encore : code 3) et dont la tête est celle contrôlée |
| `spec lint`, `spec release`, `spec sync <version>`, `spec verify` | §14 |
| `qualify open <incr>`, `qualify run <incr>`, `qualify lint <incr>`, `qualify submit <incr>`, `qualify close <incr>` | §15 |
| `nightly` | suite complète des tests d'IHM (§16) |
| `note "<texte>"`, `journal add`, `journal flush`, `journal report`, `journal setup` | §13 |
| `hook stop`, `hook session-start`, `hook pre-tool` | appelés par les hooks du projet (`.claude/settings.json`) ; `hook pre-tool` ne dit rien hors d'une session cloud et, dans une session cloud, rend sur la sortie standard la décision `deny` (`hookSpecificOutput`, `permissionDecisionReason` : la ligne de refus du §12.1) quand la commande Bash appelle, où que ce soit, un geste refusé ; silencieux et rapide en cas d'erreur |
| `kit lint` | contrôle du plugin lui-même |

**Sorties du moteur.** Une carte y est nommée par sa référence lisible (§1) ; plusieurs
références se séparent par `; `, un titre pouvant contenir une virgule :
- `cards list` : `<id> : <titre> — <kind>, <status>[, depends on <références>]` ;
- `cards order` : `<id> : <titre> — <kind>, <status>[ (waits for <références>)]` ;
- `cards lint` : `<id> : <titre> — <problème>`, puis `note: <id> : <titre> — <remarque>`, sans
  effet sur le verdict ;
- `story status`, `story wait`, `story next` : première ligne `<id> : <titre> — <état>` ;
- `verify`, `gate` : `<id> : <titre> — verification <verdict> (<résultat>)`,
  `<id> : <titre> — integration check green|red`.

Les formules auxquelles réagit le lead en run restent en anglais, mot pour mot : `already open`,
`anchored before … was merged`, `still running`, `max_in_flight`, `waits for`.

### 12.3 Campagne

`docs/campaigns/<nom>.md`, 40 lignes visées : `## Objective`, `## Questions`, `## Run` (réécrite
en fin de run, chaque carte nommée `<id> : <titre court>` : stories faites, décisions prises en
route, cartes différées, points pour le decision owner), `## Next` (prochain pas, fichiers à lire
en premier, réécrit à chaque passation). Le lead commite sur la branche courante de la copie
principale, sans pousser ; ce qu'il produit arrive sur la branche cible par un geste humain
(commit, ou demande de fusion approuvée).

### 12.4 Run

L'humain lance `deliveryctl run`. Le `technical-lead`, en session de rôle, enchaîne les cartes
lançables dans l'ordre des dépendances ; pour chacune : ancrage dans le code réel à la tête de la
cible, ordre écrit, `story open`, puis `story wait`. Pendant l'attente, il ancre d'avance la
carte suivante, et seulement elle, à la tête de la cible et sans préparer sa copie :
`story prepare` vient juste avant `story open`. `max_in_flight` compte les stories ouvertes
(ordre commité) qui ne sont ni arrêtées (§9 : `blocked`, `deferred`, `plan-ready`,
`verify-exhausted`, `review-exhausted`) ni `merged` ; une story `submitted` compte. Le lead choisit
entre séquentiel (défaut) et parallèle : il n'ouvre une seconde story pendant qu'une tourne que
s'il est sûr qu'elles ne peuvent pas entrer en conflit (zones de code disjointes, aucune
dépendance déclarée ni implicite), jamais au-delà de `max_in_flight` ; dans le doute, séquentiel. Le run ne
s'interrompt pas pour une question : le lead tranche et documente dans l'ordre, ou il passe la
carte en `deferred` en le motivant. Il se termine quand plus rien n'est lançable, par la section
`## Run` de la campagne et une ligne `Outcome: done`, ou `Outcome: blocked` quand il ne peut pas
continuer.

## 13. Notifications et journal

**Notifications**, envoyées par le moteur seul, une par événement : un événement déjà notifié ne
l'est plus, que `notify_cmd` ait réussi ou non (son échec s'affiche sur la sortie d'erreur, §4).

| Événement | Titre |
|---|---|
| décision attendue (story arrêtée, commits du cloud refusés, plan à voir, demande de fusion à relire, borne atteinte, contrôle d'intégration ou CI rouge, vérification impossible, run arrêté, recette à synthétiser, suite de nuit sans test, sans runner ou sans carte, question d'une session humaine) | `⚠ <dépôt> — <id> : <titre> — <quoi>` ; sans carte : `⚠ <dépôt> — <quoi>` |
| run terminé, avec renvoi à `## Run` | `⭐ <dépôt> — run terminé` |
| agent bloqué (§9.3) | `🚨 <dépôt> — <id> : <titre> — bloqué` |
| anomalies de la nuit prêtes à trier | `⭐ <dépôt> — anomalies à trier` |

Une story fusionnée, avec `notify_story_end` (§4) : `⭐ <dépôt> — <id> : <titre> — fusionnée`.
Au-delà de 90 caractères pour `<id> : <titre> — <quoi>`, le titre est abrégé par « … » ; titre
inconnu : `<id> — <quoi>`.

**Journal d'expérience** : événements JSON, lus par l'humain seul, jamais renvoyés aux agents.

```json
{"schema": "delivery-event/1", "ts": "…", "method_version": "0.2.0", "repo": "…", "story": "s004",
 "role": "engine", "source": "engine | human | agent", "category": "…", "text": "…", "evidence": "…"}
```

`category` : `stall`, `refusal`, `resume`, `compact`, `verify-exhausted`, `review-exhausted`,
`spec-gap`, `night-anomalies`, `summary`, `note`, `other`. Client : `psql`, table
`delivery_journal(id bigserial, recorded_at timestamptz, event jsonb)` de `journal_dsn`, passée à
`psql` par l'environnement, jamais sur la ligne de commande. Base absente ou injoignable (5 s au
plus) : l'événement va dans la file locale, sans jamais faire échouer une commande ;
`journal flush` l'envoie par lots ; sans `journal_dsn`, la file locale est le journal. Un événement mal
formé est gardé et marqué `invalid`. Les rôles sans surveillance n'écrivent pas au journal : ils
signalent un obstacle dans `report.md`, et le moteur porte au journal refus de permission,
reprises, bornes et blocages, qu'une notification soit partie ou non. `journal report` est refusé
dans une session de rôle et dans un dépôt équipé : l'analyse se fait hors de tout projet, par le
lanceur du plugin (`<racine du plugin>/bin/deliveryctl journal report`, racine donnée par la
ligne `plugin` de `deliveryctl doctor`).

## 14. Spécification

### 14.1 Maturation d'un incrément

`refinement/<incr>/framing.md` (80 lignes visées) : frontmatter `id`, `status` (`discussing`,
`framed`, `closed`), `scope` ; sections `## Purpose`, `## Firm decisions`, `## Scope`,
`## Exclusions`, `## To investigate`, `## Assumptions`, `## Deferred`, `## Story map`, `## Next`.
Une décision ferme s'écrit `D<n> : <titre court> — <décision> — « <mots de l'humain> » (<date>)`.
Quatre GO humains : cadrage (`framed`), revue, clôture (`closed`), publication (tag). En solo, le
GO est le statut, posé par l'analyste sur message explicite de l'humain ; en équipe, la demande
de fusion approuvée.

Rapport de revue : `refinement/<incr>/reviews/<date>.md` (`-2`, `-3` pour une autre revue du même
jour), terminé par `Max severity: blocking | to-decide | note | none` et `Spec ready: yes | no`
(`yes` seulement sans constat `blocking` ni `to-decide` ouvert). Taille choisie à chaque revue
(`light`, `standard`, `deep`), `deep` par défaut, sans plafond d'agents.

### 14.2 Livrable `spec/`

```
spec/spec.toml            name, version, locales
spec/product/             brief.md, glossary.md
spec/stories/s004-<slug>.md
spec/ui/copy.<locale>.json
spec/acceptance/          suite Playwright, harness-contract.md, fixtures/empty-app/
spec/CHANGELOG.md
```

Story de spec : frontmatter `id`, `title` (titre court, 3 à 8 mots, repris par la carte de la
story), `status` (`draft`, `ready`) ; sections `## Business rules`, `## Main flow`,
`## Extensions`, `## Acceptance criteria`, `## UI contract`, `## Outcomes`, `## Out of scope`,
`## Open questions`. Une extension est un élément de liste `- <n><lettre>. <condition> : …` de
`## Extensions` ; un critère :
`AC<n> @main|@ext-<n><lettre> — Given … When … Then …` (mots-clés en anglais). Un test couvre un
critère par l'étiquette `@<id>-ac<n>` dans son titre, et porte `@<id>` dans son titre ou dans celui
d'un `test.describe` du même fichier.

**Harnais** (`spec/acceptance/harness-contract.md`) : en mode test seulement, chaque
implémentation sert, sur l'origine de `BASE_URL`, `reset` (vide les données), `users` (crée une
personne nommée), `login-as` (ouvre une session pour elle) et, si une story dépend du temps,
`tick` (avance l'horloge et exécute ce qui est dû). Toute autre donnée passe par l'interface.
`fixtures/empty-app/` est une application qui sert le harnais et rien d'autre : la suite y est
100 % rouge.

### 14.3 `deliveryctl spec lint`

Règles `schema`, `neutrality`, `extension`, `coverage`, `orphan-tag`, `test-tag`. Schéma tolérant en
`draft`, strict en `ready` ; les contrôles de complétude (un critère par extension, un test par
critère) ne visent que les stories `ready`, pour qu'un incrément en cours ne bloque pas une
publication ; lexique de neutralité technologique extensible (`extra` et `allow` sous `[neutrality]`
de `spec.toml`) ; aucune étiquette de test orpheline ; `spec.toml` et les fichiers
`ui/copy.<locale>.json` lisibles. Sortie `chemin:ligne: règle: message`. Un constat se lève par une
ligne `lint-exempt: <règle> — <raison>` dans la story, sauf le schéma d'une story `ready`.

### 14.4 Versions

Tags `spec-vX.Y.Z`. `spec release` calcule le niveau : critère retiré ou modifié → majeur,
ajouté → mineur, sinon correctif ; en `pre-release`, tout reste en `0.x`. En `released`, un tag
inférieur au niveau calculé est refusé sauf trailer humain `Version-Override: <raison>`.
`spec release` refuse une spec inchangée depuis le dernier tag ou des changements non commités
sous `spec/`, écrit la version dans `spec.toml` et un brouillon en tête de `spec/CHANGELOG.md`, puis
affiche les commandes de commit, de tag et de push ; le tag reste un geste humain.

### 14.5 Copie dans un dépôt d'implémentation

`spec sync <version>` (geste humain) : `git fetch --no-tags <source> refs/tags/spec-v<version>`,
`git rm -r -q --ignore-unmatch spec`, `git read-tree --prefix=spec/ -u FETCH_HEAD:spec`, puis
`spec.lock` et `docs/conformance.md`, en un seul commit (trailers `Spec-Version`, `Spec-Commit`,
`Delivery-Method`), aucun si rien ne change. `docs/conformance.md` donne pour chaque story de spec
sa référence et son statut : `conforming` (le blob du trailer `Spec:` de sa fusion est le blob
courant), `outdated` (il diffère) ou `not merged` (aucune fusion portant ce trailer, par exemple une
fusion faite dans la forge).

```toml
# spec.lock
source = "<url du dépôt de spec>"
version = "1.0.0"
commit = "<FETCH_HEAD^{commit}>"
tree = "<FETCH_HEAD:spec>"
```

`spec verify` vérifie sans réseau que `HEAD:spec` a l'arbre du verrou. Référence d'une story :
`s004@1.0.0#9c1e2a4` (identifiant, version, blob court de la fiche) ; le blob décide, la version
informe.

## 15. Qualification

### 15.1 Plan — `qualification/plan.md`

`## Surface` : un tableau dressé en lisant le code (routes, commandes, tâches planifiées,
déclencheurs, installation, retrait, mise à jour), une ligne par point d'entrée avec ses contrôles
(`Q<n> : <titre court>`) ou `not covered — <raison>`. Puis un contrôle par section, son titre
court étant l'affirmation vérifiée :

```markdown
### Q17 : un compte non invité ne lit pas une liste partagée   [run, negative]
Targets: s004 : Partager une liste · GET /lists/{id}
Touches: src/**/share/**
Do: …
Expect: …
```

Numéros stables, jamais réattribués. Mise en place et retrait sont des contrôles.

### 15.2 Rapport — `qualification/reports/<incr>.md`

En tête `Tree:` (arbre de code du commit dont part la branche de recette), `Spec:`, `Env:` ; un
tableau `Q | Mode | Result | Proof`, une ligne par contrôle du plan (`Q` :
`Q<n> : <titre court>` ; `Result` : `pass`, `fail`, `blocked` ou `not-run` ; `Proof` : une ligne
`commande → valeur`) ; les anomalies `A-<n> : <titre court>` ; les points d'entrée non couverts ;
sections `Read` et `Run` (une section vide dit pourquoi) ; en fin, un bloc de verdict proposé
(§7.1), `By: qualification-lead`.

### 15.3 Déroulé et verdict

`qualify open <incr>` : copie de travail `qualification/<incr>` depuis la cible, squelettes du
plan, du rapport et de l'ordre ; rien n'est commité. `qualify run <incr>` : lance un
`qualification-runner` sur l'ordre `qualification/order.md`, commité par le lead ; refusé si
l'ordre a des modifications non commitées. `qualify submit <incr>` (geste humain) : pousse et
ouvre la demande de fusion ; son approbation par l'humain vaut verdict. Recette continue : la
suite de nuit (§16). Recette complète : une par implémentation et par version livrée, obligatoire
avant toute livraison à un tiers ; elle rejoue tous les contrôles `run`. `doctor` signale une
version taguée sans rapport accepté pour son arbre.

### 15.4 Anomalies

L'agent qui trouve écrit la carte `kind: anomaly`, `title:` le défaut en 3 à 8 mots,
`status: to-triage`, tout de suite. Le tri est la relecture de la demande de fusion qui la
porte : corriger (maturation puis `ready`), reporter (`deferred`), abandonner (`dropped`), ou
remonter une question de spec.

## 16. Suite complète de nuit — `deliveryctl nightly`

Sur la tête de la branche cible, dans une copie jetable : `commands.acceptance` avec `{grep}`
vide et le port de la nuit (§3) ; 0 test exécuté vaut échec. En cas d'échec, un
`qualification-runner` écrit une carte d'anomalie par défaut distinct
(`found: nightly-<jour>@<commit court>`, premier identifiant `a<nnn>` libre sur la branche
cible) ; le moteur les commite sur `anomalies/<date>`, pousse et ouvre la demande de fusion
« Anomalies du <date> », puis notifie. Jamais la suite complète à chaque story.

Une branche `anomalies/<jour>` sans commit propre (reste d'une nuit du même jour) est supprimée et
la nuit continue ; avec des cartes, la nuit est refusée avec la commande qui la supprime. Un
runner qui ne démarre pas ne laisse ni copie ni branche ; le journal de la suite est gardé dans
`.delivery/run/logs/`.

## 17. Codes de sortie de `deliveryctl`

| Code | Sens |
|---|---|
| 0 | succès |
| 1 | erreur d'usage ou interne |
| 2 | contrôle rouge (lint, gate, verdict) |
| 3 | précondition non remplie, ou délai d'attente écoulé |
| 4 | refusé : geste humain demandé par un rôle, chemin interdit |
| 5 | outil externe indisponible (git, forge, claude, base) |
