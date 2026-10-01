# delivery-method

Plugin Claude Code qui apporte une méthode de livraison en trois phases : **spécifier**,
**implémenter** story par story, **recetter**. Stricte sur les livrables (formats, verdicts,
gestes réservés à l'humain), souple sur la manière : chaque borne est un défaut réglable, et
chaque rôle proportionne son effort au risque en le disant.

Le plugin réunit un moteur en ligne de commande, `deliveryctl`, huit rôles (agents), des
commandes, des skills et des gabarits. Ce que le moteur, les rôles et les humains s'échangent
est fixé dans [`CONTRACTS.md`](CONTRACTS.md), qui fait foi.

## Principes

- **Trois régimes.** En spécification, on discute : rien ne se tranche en silence. En
  implémentation, on tranche et on documente, ou on diffère. En recette, on constate et on
  consigne.
- **Un decision owner.** L'humain qui décide : lui seul approuve, fusionne (sauf réglage
  contraire), tague, pousse, publie une version de spec et change la méthode.
- **L'état est dans git.** Cartes, ordres de travail, comptes rendus et verdicts sont commités ;
  une session neuve reprend depuis eux, jamais depuis une mémoire ou une fenêtre.
- **Une story, une copie de travail, des sessions jetables.** Chaque story vit dans sa copie de
  travail git (`<dépôt>-wt/<id>`, à côté du dépôt), où le moteur enchaîne un exécutant, une
  vérification, un relecteur neuf et une demande de fusion.
- **Un moteur par projet.** `deliveryctl` (Python, bibliothèque standard seule) est copié dans le
  projet : sessions, CI et tâches planifiées exécutent la même version.
- **Des noms qui se lisent.** Une carte, une story, une anomalie, un contrôle de recette ou une
  décision se nomme toujours `<id> : <titre court>` (`s004 : Partager une liste`), jamais par
  son seul identifiant : comptes rendus, commits, notifications, sorties du moteur. Le titre
  court est le `title:` de la carte, obligatoire, en quelques mots (3 à 8 visés). Les noms
  techniques gardent l'identifiant seul : branche `story/s004`, dossier `docs/stories/s004/`,
  argument `deliveryctl story open s004`.

## Pour qui

Des équipes, ou une personne seule, qui construisent un produit web avec Claude Code et veulent
une spec versionnée, neutre en technologie et jugée par une suite de tests d'IHM partagée, des
stories vérifiées, relues et livrées par demande de fusion, et une recette avant chaque livraison.
Un dépôt porte la spec (`spec`), une implémentation (`impl`) ou les deux (`single`) ; plusieurs
implémentations peuvent suivre la même spec. Moins adapté : un prototype jetable, une IHM non web.

## Prérequis

| Outil | Pour quoi |
|---|---|
| Claude Code (`claude`) | sessions humaines et sessions de rôle |
| git | dépôts et copies de travail des stories (`git worktree`) |
| Python 3.11 ou plus | moteur `deliveryctl`, sans dépendance à installer |
| just | recettes `check`, `acceptance`, `serve` (paquet de la distribution, ou `pipx install rust-just`) |
| Node.js, version LTS | suite d'acceptation Playwright |
| gh ou glab, authentifié | demandes de fusion sur GitHub ou GitLab |
| herdr, facultatif | fenêtres de suivi des stories ; sans lui, mode terminal |
| psql et Docker, facultatifs | journal d'expérience en PostgreSQL |

Sous Windows, travaillez dans WSL 2, avec les copies de travail de préférence sur le système de
fichiers Linux (`~/src/…`) plutôt que sous `/mnt/c/…` : git et les tests y sont nettement plus
rapides, et le bit exécutable de `.delivery/deliveryctl` y est conservé.

## Installation

**1. Installer le plugin.**

```sh
claude plugin marketplace add peugene/delivery-method
claude plugin install delivery-method@delivery-method
```

L'installation pour l'utilisateur suffit : le plugin ne sert qu'à équiper un dépôt (`/delivery-method:init`),
`init` copie ensuite la méthode dans le dépôt lui-même. Pour un essai sans installation : `claude --plugin-dir /chemin/vers/delivery-method`.

**2. Équiper le dépôt.** Dans une session Claude ouverte à la racine de la copie principale,
tapez `/delivery-method:init`. La commande pose cinq questions (contenu du dépôt ; langue du
contenu ; forge `github` ou `gitlab` ; commande `check` ; commandes `acceptance` et
`serve`), recommande une réponse pour chacune, lance `deliveryctl init` et affiche le bilan.
`init` n'écrase rien et ne commite rien. Il pose `delivery.toml` (réglages du projet),
`.delivery/` (copie du moteur, règles communes, gabarits, manifeste `method.json`),
`.claude/agents/`, `.claude/skills/` et `.claude/commands/` (copie des agents, skills et commandes de
la méthode, sans espace de noms : `/spec-frame`, `/impl-frame`, `/run-campaign`…), un `justfile` d'amorce dont les
recettes échouent tant qu'elles ne sont pas écrites, la CI de la forge
(`.github/workflows/delivery.yml` ou `.gitlab/delivery-ci.yml`) et, pour un dépôt `spec` ou
`single` qui n'en a pas encore, un squelette `spec/` (`spec.toml`, contrat du harnais, libellés,
harnais Playwright et application vide, `CHANGELOG.md`, brief, glossaire) ; il complète par ajout
`CLAUDE.md` (import `@.delivery/rules.md`, section `## Project conventions`), `.gitignore` et
`.claude/settings.json` (plugin désactivé dans le projet, y compris si une installation à la portée
projet l'avait activé, car sa copie ferait doublon avec celle du projet ; hooks `Stop` et
`SessionStart` ; messagerie entre sessions refusée ; confirmation pour les gestes humains). Écrivez
les recettes du `justfile` pour votre pile, relisez, puis commitez : toute session Claude Code qui
clone le dépôt, y compris une session cloud qui n'installe aucun plugin, y trouve la méthode
entière. Ne modifiez pas à la main les fichiers copiés sous `.claude/` : `--upgrade` refuse
d'écraser une copie modifiée (les fichiers que vous y ajoutez vous-même ne sont jamais touchés).

**3. Raccourci dans le shell.** Dans un projet, le moteur s'exécute toujours depuis sa copie,
`.delivery/deliveryctl`. Pour votre shell, ajoutez à `~/.bashrc` ou `~/.zshrc` :

```sh
[ -n "$CLAUDECODE" ] || deliveryctl() { "$(git rev-parse --show-toplevel)/.delivery/deliveryctl" "$@"; }
```

La garde sur `CLAUDECODE` laisse les sessions Claude hors de cette fonction : Claude Code rejoue
les fonctions de votre fichier de démarrage dans son outil Bash, où elle masquerait la copie du
projet. Dans ces sessions, `deliveryctl` est déjà dans le `PATH` : le hook `SessionStart` du projet y met
`.delivery/`, et c'est donc la copie du projet. Vérifiez enfin avec
`deliveryctl doctor`, qui ne modifie rien : chaque ligne vaut `ok`, `note` ou `warn`.

**Mettre à jour.** Mettez à jour le plugin (`/plugin` dans Claude Code), puis relancez
`/delivery-method:init` : sur un dépôt équipé, il lance `deliveryctl init --upgrade`, qui
rafraîchit `.delivery/`, la copie sous `.claude/` (en retirant les fichiers que la nouvelle version
n'a plus), les hooks et la version épinglée dans `.claude/settings.json`, et désactive le plugin
dans le projet. Si un fichier copié a été modifié à la main, il refuse, en les listant, avant
d'écrire quoi que ce soit. Relisez, commitez.

**Publier une version du plugin** (mainteneurs). `init` épingle la marketplace sur l'étiquette
`delivery-method--vX.Y.Z` : sans elle, un coéquipier ne peut pas installer le plugin. Montez la
même version dans `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` et
`engine/deliveryctl/__init__.py`, complétez `CHANGELOG.md`, commitez, puis lancez
`claude plugin tag --push`, qui crée et pousse l'étiquette.

## Démarrage rapide

Pour un parcours complet et illustré, une spec et deux implémentations d'une liste de tâches,
avec le schéma de chaque phase et ses commandes : [`docs/guide.md`](docs/guide.md).

Dans un dépôt équipé, les commandes `/spec-frame`, `/impl-frame`… se tapent dans une session Claude, les commandes
`deliveryctl …` dans le shell. Avant un `/clear`, `/handoff` range dans les
fichiers ce qui a été décidé et donne la ligne de reprise.

Pour réfléchir à une idée avant d'en faire du travail, à n'importe quelle phase :
`/brainstorm <idée>`. Rien n'est écrit pendant la discussion ; à la fin, vous
choisissez d'oublier, d'archiver dans `docs/maybe/` (dossier qu'aucun agent ne lit de lui-même)
ou de cadrer, et seules les décisions que vous avez validées passent au cadrage.

### Spécification (dépôt `spec` ou `single`)

Une spécification se construit par incréments (`01-core`, `02-partage`…), mûris dans
`refinement/<incr>/framing.md` puis écrits dans `spec/`. Quatre GO humains jalonnent un
incrément : cadrage, revue, clôture, publication. En équipe, un GO est l'approbation de la
demande de fusion qui porte le changement.

1. Une fois par dépôt, dans le squelette `spec/` posé par `init`, renseignez `name` et `locales`
   dans `spec/spec.toml`, puis installez la suite d'acceptation ;
   `.delivery/templates/spec/acceptance/tests/example.spec.ts` montre la forme d'un test :
   ```sh
   (cd spec/acceptance && npm install && npx playwright install chromium)
   ```
2. `claude --agent product-analyst`, puis `/spec-frame 01-core`.
   L'analyste lit l'existant, donne son avis, pose des questions numérotées avec sa
   recommandation, et consigne vos décisions mot pour mot. Le **GO de cadrage** se donne
   explicitement.
3. `/spec-write 01-core` : stories, contrat d'IHM, libellés ;
   `deliveryctl spec lint` doit être vert.
4. `/spec-review 01-core` : taille et angles annoncés, votre **GO de revue**,
   puis un relecteur par angle, un réfuteur par constat et un rapport daté dans
   `refinement/01-core/reviews/`.
5. `/spec-write 01-core` applique vos réponses ; au **GO de clôture**, les
   stories passent en `ready`.
6. `/spec-write 01-core --acceptance`, puis
   `/spec-review 01-core --acceptance` : les tests, tous rouges contre
   l'application vide.
7. **Publication** : `deliveryctl spec release` calcule la version (critère retiré ou modifié :
   majeure ; ajouté : mineure ; sinon corrective ; `0.x` tant que `release_stage` vaut
   `pre-release`), écrit l'entrée de `spec/CHANGELOG.md` et affiche les commandes de commit, de
   tag `spec-vX.Y.Z` et de push, que vous lancez.

### Implémentation (dépôt `impl` ou `single`)

1. Dépôt `impl` : `deliveryctl spec sync 0.1.0 --source <url du dépôt de spec>` copie une version
   publiée (un commit : `spec/`, `spec.lock`, `docs/conformance.md`) ; `deliveryctl spec verify`
   contrôle ensuite, sans réseau, que `spec/` n'a pas bougé.
2. Cadrage : `claude --agent technical-lead`, puis
   `/impl-frame <campagne>` : `docs/architecture.md`, un ADR par choix
   structurant, les cartes de `backlog/` en `draft`, et les `## Project conventions` proposées
   pour `CLAUDE.md`, que vous collez et commitez.
3. **GO des cartes** : passez les cartes validées en `status: ready`, commitez, et amenez ce
   commit sur la branche cible. Le run ne lit que les cartes de la branche cible.
4. `deliveryctl run --campaign <campagne>` : le `technical-lead` démarre en session de rôle et
   enchaîne les cartes lançables dans l'ordre des dépendances. Pour chacune, il ancre les faits
   dans le code réel, écrit l'ordre de travail et ouvre la story ; le moteur enchaîne alors
   `story-implementer` (plan, une tâche par commit vert, compte rendu), `deliveryctl verify`
   (`check`, puis les tests d'IHM de la story), un `story-reviewer` neuf (relecture, contrôles
   renforcés selon les risques de la carte), les corrections bornées, puis `deliveryctl submit`
   (contrôle d'intégration, push de `story/<id>`, demande de fusion).
5. Notifié de chaque demande de fusion à relire, vous la relisez et fusionnez par
   `deliveryctl merge <id>`, qui pose un commit de fusion porteur des trailers de traçabilité.
   En `integration = "ai"`, le moteur fusionne lui-même quand la CI est verte : au moins un
   contrôle, tous réussis ; tant qu'aucun contrôle n'a rendu son résultat, il attend.
6. Quand plus rien n'est lançable, le lead réécrit la section `## Run` de
   `docs/campaigns/<campagne>.md` (stories faites, décisions prises en route, cartes différées,
   points pour vous) et vous êtes notifié.

`deliveryctl story status [--watch]` donne l'état de chaque story
(`s004 : Partager une liste — to-review`), la prochaine étape du moteur et votre prochain geste.
Une story s'arrête sur un point qui vous revient :

| Arrêt | Votre geste |
|---|---|
| `plan-ready` (carte `show_plan: true`) | lire `plan.md`, puis `deliveryctl story next <id> --go` |
| `blocked`, `deferred` | lire `report.md`, et `spec-question.md` pour une question produit à porter à la spec |
| `verify-exhausted`, `review-exhausted` | lire `verification.md` et `work/verify.log`, ou `review.md` |
| `submitted` (notification « demande de fusion à relire ») | relire et fusionner la demande de fusion |

`deliveryctl story close <id>` ferme une story arrêtée et garde sa branche pour lecture ; pour
la relancer de zéro après correction de la carte, supprimez aussi cette branche.

### Recette (dépôt `impl` ou `single`)

Une par implémentation et par version livrée, obligatoire avant toute livraison à un tiers.

1. `claude --agent qualification-lead`, puis `/qualify 0.2.0`.
   Le lead ouvre la recette (branche `qualification/0.2.0`), dresse la surface depuis le code
   (routes, commandes, tâches planifiées, installation, retrait, mise à jour), écrit les
   contrôles (`Q17 : un compte non invité ne lit pas une liste partagée`), confronte la
   documentation au code et prépare `qualification/order.md`, qu'il commite avant de lancer
   l'exécution.
2. `deliveryctl qualify run 0.2.0` (refusé tant que l'ordre a des modifications non commitées)
   lance un `qualification-runner` jetable : il installe le produit depuis sa documentation, joue
   les contrôles, écrit une carte d'anomalie `to-triage` par défaut du produit, démonte et prouve
   qu'il ne reste rien.
3. Le lead synthétise `qualification/reports/0.2.0.md` et propose un verdict (`accepted`,
   `accepted-with-reserves`, `rejected`) ; `deliveryctl qualify lint 0.2.0` doit être vert.
4. **Verdict** : vous lancez `deliveryctl qualify submit 0.2.0` ; votre approbation de la demande
   de fusion vaut verdict. Les anomalies se trient dans cette relecture : corriger (la carte
   mûrit, puis passe `ready`), reporter (`deferred`), abandonner (`dropped`), ou porter une
   question à la spec.

### Suite complète de nuit

La vérification d'une story ne joue que ses propres tests d'IHM. `deliveryctl nightly` joue la
suite complète sur la tête de la branche cible, dans une copie jetable. Verte : un résumé au
journal. Rouge : un `qualification-runner` écrit une carte d'anomalie par défaut distinct sur la
branche `anomalies/<date>`, le moteur ouvre la demande de fusion « Anomalies du <date> » et vous
notifie ; le tri du matin est la relecture de cette demande. Aucun test exécuté compte comme
rouge. Exemple de `crontab -e`, du lundi au vendredi à 2 h 30 :

```cron
PATH=/home/moi/.local/bin:/usr/local/bin:/usr/bin:/bin
30 2 * * 1-5 cd /home/moi/src/mon-projet && ./.delivery/deliveryctl nightly >> "$HOME/delivery-nightly.log" 2>&1
```

Le `PATH` doit contenir `claude`, `just`, `node` et `gh` ou `glab`, authentifiés pour cet
utilisateur ; si le moteur ne trouve pas le plugin, renseignez `plugin_dir`. Sous WSL, le service
cron doit tourner (`sudo service cron start`) et la machine virtuelle être active à l'heure dite.

## Commandes du plugin

Dans un dépôt équipé, les commandes sont celles de la copie du projet, sans espace de noms ; seule
`init`, qui équipe le dépôt, reste une commande du plugin (`/delivery-method:init`).

| Commande | Session | Effet |
|---|---|---|
| `/delivery-method:init [--upgrade]` | humaine, racine du dépôt | équipe le dépôt, ou met à jour sa copie de la méthode (moteur, agents, skills, commandes) |
| `/spec-frame <incr> [--discover] [--market <domaine>]` | `product-analyst` | cadrage d'un incrément jusqu'au GO de cadrage |
| `/spec-write <incr> [<story>] [--acceptance]` | `product-analyst` | stories, corrections jusqu'au GO de clôture ; `--acceptance` : les tests |
| `/spec-review <incr> [deep\|standard\|light] [--acceptance]` | `product-analyst` | relecture contradictoire, rapport daté |
| `/impl-frame <campagne> [sujet]` | `technical-lead` | architecture, ADR, cartes en brouillon |
| `/run-campaign <campagne>` | `technical-lead`, de rôle | le run ; lancée par `deliveryctl run`, jamais à la main |
| `/qualify <incr>` | `qualification-lead` | recette d'un incrément |
| `/handoff [<incr>\|<campagne>]` | tout lead, humaine | passation avant `/clear` |
| `/brainstorm <idée>` | humaine, tout dépôt | explorer une idée sans rien engager ; clôture : oublier, archiver dans `docs/maybe/` ou cadrer |

## Rôles

| Rôle | Phase | Session | Ne fait jamais |
|---|---|---|---|
| `product-analyst` | spec | humaine | trancher une question produit ; choisir une technique |
| `spec-reviewer` | spec | sous-agent | corriger |
| `refuter` | spec, recette | sous-agent | proposer un correctif |
| `technical-lead` | impl | humaine (cadrage), de rôle (run) | écrire du code |
| `story-implementer` | impl | de rôle | poser une question ; approuver ; pousser |
| `story-reviewer` | impl | de rôle, toujours neuve | commiter une modification de code |
| `qualification-lead` | recette | humaine | corriger le produit |
| `qualification-runner` | recette | de rôle, jetable | corriger le produit ; pousser |

Un lead en session humaine se lance par `claude --agent <rôle>`. Une session de
rôle, lancée par le moteur, ne pose jamais de question : elle tranche et documente, ou elle
diffère. Rédacteur et relecteur ne sont jamais la même session, et les sessions ne se parlent
pas : elles passent par les fichiers du dépôt.

## Verbes de `deliveryctl`

**H** : geste humain, refusé dans une session de rôle et soumis à confirmation dans une session
Claude, sauf `story close` : une règle de confirmation ne distingue pas une story arrêtée d'une
story fusionnée, que le lead ferme pendant le run ; le moteur seul refuse à un rôle la fermeture
d'une story arrêtée.

| Verbe | Effet |
|---|---|
| `init [--role R] [--upgrade] [--dry-run]` **H** | pose ou met à jour moteur, règles, réglages, CI ; n'écrase rien, ne commite rien |
| `doctor` | diagnostic en lecture seule |
| `cards list`, `cards order` | lire, ordonner les cartes de la branche cible, celles que lit le run |
| `cards lint` | contrôler les cartes de la copie de travail, avant de les commiter |
| `campaign open <nom> --phase P` | crée `docs/campaigns/<nom>.md` et son dossier de travail |
| `run [--campaign N]` **H** | lance le `technical-lead` en mode run |
| `story prepare <id>` | copie de travail et squelette d'ordre ; rien n'est commité |
| `story open <id>` | contrôle et commite l'ordre, lance l'exécutant |
| `story status [<id>] [--watch]` | état, prochaine étape du moteur, prochain geste humain |
| `story next <id> [--go]` | enchaîne la suite ; `--go` (**H**) relance après `plan-ready` |
| `story wait <id> [--timeout S] [--until merged]` | attend un arrêt, ou la fusion |
| `story close <id>` | supprime la copie de travail d'une story fusionnée, ou arrêtée (**H**) |
| `verify <id>`, `gate <id> [--head R]`, `submit <id>` | vérification et verdict commité ; contrôle d'intégration ; push et demande de fusion (refusé si elle est déjà fusionnée) |
| `merge <id> [--keep]` **H** | fusionne une demande de fusion à CI verte (au moins un contrôle, tous réussis ; sinon code 3, ou 2 si elle est rouge) dont la tête est celle contrôlée |
| `spec lint`, `spec verify` | contrôle de `spec/` ; conformité de `spec/` à `spec.lock` |
| `spec release [<version>]` **H** | calcule la version, prépare le CHANGELOG, affiche commit, tag et push |
| `spec sync <version> [--source URL]` **H** | copie une version publiée de la spec, en un commit |
| `qualify open`, `qualify run`, `qualify lint <incr>` | ouvrir une recette, lancer son exécution, contrôler plan et rapport |
| `qualify submit <incr>` **H** | pousse la recette et ouvre sa demande de fusion |
| `qualify close <incr>` | supprime la copie de travail de la recette (la branche reste) |
| `nightly` **H** | suite complète des tests d'IHM sur la branche cible |
| `note "<texte>" [--story ID]` **H** | remarque au journal d'expérience |
| `journal setup`, `journal flush`, `journal report` (**H**) | mise en place, envoi de la file locale, lecture hors de tout dépôt (voir Journal d'expérience) |
| `kit lint [chemin]` | contrôle du plugin lui-même |

`hook stop` et `hook session-start` sont appelés par les hooks du projet (`.claude/settings.json`). Codes de sortie :
0 succès ; 1 erreur d'usage ou interne ; 2 contrôle rouge ; 3 précondition non remplie ou délai
écoulé ; 4 refusé ; 5 outil externe indisponible.

## Réglages

### Projet : `delivery.toml`

Commité et tenu par l'humain ; une clé inconnue fait échouer toute commande. Les commentaires du
fichier posé par `init` décrivent chaque clé : `repo_role`, `content_language`, `release_stage`
(`released` après la première livraison à un tiers : la compatibilité compte),
`external_contracts` (détenteurs externes d'un état ou d'une API), `forge`, `integration`
(`human`, ou `ai` : le moteur fusionne quand la relecture dit oui et que la CI est verte),
`implementer` (`cloud` ou `local` : où tourne le `story-implementer`, voir « Exécutant dans le cloud »),
`max_in_flight` (stories en cours en même temps, `1` par défaut ; une story arrêtée ne compte
pas), `agent_prefix`, `port_prefix`, `[commands]` (`check`, `acceptance` avec `{grep}`, `serve`
avec `{port}`, `test` avec `{selector}`, facultatif : le test ciblé permis aux rôles,
`just test <selector>`) et `[permissions] extra_allow` (règles ajoutées aux rôles, par exemple
`"Bash(./gradlew *)"`).

Chaque story a son port, `<port_prefix><numéro>` ou le suivant libre. Le moteur le substitue à
`{port}` dans ce qu'il lance (vérification, suite de nuit) et l'exporte dans `DELIVERY_PORT`, que
les sessions de rôle ont aussi : une recette `acceptance` qui lit `DELIVERY_PORT` sert
l'application de la story sur son port, sans collision entre stories. La CI utilise 3999.

Leviers de `[levers]`, vide par défaut ; toute clé écrite est visible en revue :

| Levier | Défaut | Effet |
|---|---|---|
| `review_loops` | `2` | corrections après une relecture `no` avant l'arrêt |
| `verify_attempts` | `3` | corrections après une vérification `fail` avant l'arrêt |
| `short_path_max_lines` | `50` | taille visée d'un changement en voie courte, sans plan |
| `stall_minutes` | `20` | minutes sans avancée avant l'alerte « agent bloqué » |
| `reinforced_risks` | `authz` : morsure (casser la protection, voir un test échouer, restaurer) et relecture contradictoire ; `data-write`, `file-upload`, `data-leak` : relecture contradictoire | contrôles renforcés par risque ; une clé écrite remplace le défaut de ce seul risque (liste vide : aucun contrôle) ; une clé nouvelle déclare un risque du projet |
| `doc_globs` | `["docs/**", "*.md"]` | un diff entièrement dans ces chemins se vérifie par `check` seul |
| `max_order_lines` | `60` | `story open` avertit au-delà |

### Machine : `~/.config/delivery-method/machine.toml`

Personnel, jamais commité, facultatif :

```toml
window = "auto"                       # auto | herdr | terminal
notify_cmd = "~/bin/notifier"         # exécutable appelé avec deux arguments : titre, message
notify_story_end = false              # true : une notification à chaque story fusionnée
journal_dsn = ""                      # postgresql://… ; vide : le journal reste local
plugin_dir = ""                       # racine du plugin, si le moteur ne la trouve pas seul
```

`notify_cmd` est le chemin d'un exécutable (absolu, ou commençant par `~`) : un petit script qui
reçoit le titre et le message et les porte au canal de votre choix. `notify-send` convient sur un
bureau Linux, mais n'affiche rien sous WSL ni depuis cron, faute de service de notification :
sous WSL, le script peut appeler `powershell.exe` pour un toast Windows. Essayez-le une fois à la
main. Vide ou introuvable : les notifications s'affichent sur la sortie d'erreur du moteur ; en
échec, la sortie d'erreur montre `[notification failed: …]` suivi de la notification, qui n'est
pas renvoyée. `DELIVERY_WINDOW=terminal` remplace `window` le temps d'une commande.

Seul le moteur notifie, une fois par événement : ⚠ décision attendue (story arrêtée, plan à voir,
demande de fusion à relire, borne atteinte, contrôle ou CI rouge, run arrêté), 🚨 agent bloqué,
⭐ run terminé ou anomalies de nuit à trier. Le titre nomme la story :
`⚠ <dépôt> — s004 : Partager une liste — demande de fusion à relire`. Une session humaine qui
s'arrête sur une dernière ligne `Outcome: question` vous envoie aussi une notification ⚠
« décision attendue » (hook `Stop`), une par message : en spécification, chaque question de
l'analyste.

### Journal d'expérience

Le moteur y note ce qui renseigne sur la méthode (agent bloqué, refus de permission, reprise,
borne atteinte, anomalies de nuit, fin de run) ; vous y ajoutez vos remarques par
`deliveryctl note "…"`. Les agents ne le lisent jamais. Sans réglage, il reste dans une file
locale, `~/.local/state/delivery-method/journal-queue.jsonl`. `deliveryctl journal setup` affiche
la commande Docker d'une base PostgreSQL locale (volume nommé) et la ligne `journal_dsn` à
ajouter ; `journal flush` envoie la file en attente.

`journal report` lit le journal hors de tout dépôt équipé, par le lanceur du plugin appelé par
son chemin : `<racine du plugin>/bin/deliveryctl journal report`, la racine étant sur la ligne
`plugin` de `deliveryctl doctor`.

## Exécutant dans le cloud

Sur un projet GitHub, `implementer = "cloud"` (le défaut) lance chaque `story-implementer` comme
une session cloud de Claude Code : l'implémentation continue quand votre ordinateur dort ou se
déconnecte. Les autres rôles et la vérification restent locaux. Avec GitLab, `implementer` vaut
`local` ; `cloud` y est refusé au chargement, une session cloud ne poussant que sur GitHub.

Le moteur pousse `story/<id>` sur `origin`, puis lance `claude --cloud` depuis la copie de
travail de la story, dans un pseudo-terminal (la commande refuse de tourner sans terminal). La
session cloud ne reçoit que le dépôt à la branche poussée : ni fichier de rôle, ni plugin, ni
variable d'environnement du moteur, ni fichier local. Elle travaille sur sa propre branche
`claude/<nom>`, créée depuis `story/<id>`, et ne peut pousser que celle-ci. `deliveryctl story
status` affiche son URL.

Prérequis : `claude auth login` avec un compte claude.ai (pas une clé d'API) et `origin` sur
github.com. La session s'exécute dans l'environnement par défaut choisi par `/remote-env` dans
Claude Code : celui-ci doit atteindre la chaîne d'outils du projet (les commandes `check`,
`acceptance` et `serve`, leurs dépendances). `deliveryctl doctor` vérifie la connexion et
`origin`, pas l'environnement.

## Fenêtres

Le moteur lit l'état des stories dans git et dans les fichiers, jamais dans une fenêtre : une
fenêtre montre et lance les sessions, rien de plus. `window = "auto"` prend herdr s'il répond en
moins de 5 secondes, le terminal sinon.

**herdr.** Un espace de travail par story, `<dépôt>-<id> : <titre>`, ouvert sur sa copie de
travail, avec trois volets : `agent` (la session de rôle en cours, exécutant puis relecteur),
`status` (`deliveryctl story status <id> --watch`) et `tests` (la sortie de la vérification en
direct, `work/verify.log`). L'état de la story s'affiche dans la barre latérale ; le
`technical-lead` d'un run a son espace `<dépôt>-lead`. Regardez sans intervenir : ce qui se tape
dans une session de rôle ne laisse aucune trace dans les fichiers ; passez par la carte ou par
l'ordre.

**Terminal.** Le `technical-lead` d'un run s'exécute dans le terminal qui a lancé
`deliveryctl run`. Les sessions des stories tournent en arrière-plan ; leur sortie va dans
`.delivery/run/logs/<id>-<role>.log`. Pour suivre : `deliveryctl story status --watch` et, dans
la copie de travail, `tail -F docs/stories/<id>/work/verify.log`.

### Quand herdr est bloqué

L'état des stories ne dépend pas de herdr : rien n'est perdu.

1. Ne fermez rien. Dans un terminal hors herdr, capturez l'état pour un rapport :
   `timeout 5 herdr status`, `timeout 5 herdr status server`, une copie des journaux de
   `~/.config/herdr/`, et `deliveryctl story status`, qui lit l'état des stories dans git.
2. Arrêtez le serveur plutôt que la machine : `herdr server stop`, ou, s'il ne répond pas,
   `pkill -f 'herdr server'`, puis relancez `herdr`. Ne redémarrez la machine (ou WSL) que si
   cela ne suffit pas.
3. Reprenez les sessions humaines restaurées. Une session de rôle ne se reprend jamais : quittez
   celles qui ont été restaurées (`/exit`), puis `deliveryctl story next <id>` lance une session
   neuve, qui repart de `order.md`, `plan.md`, `work/notes.md` et `git status`. Pour le lead d'un
   run, `deliveryctl run --campaign <campagne>` reprend depuis la campagne et termine d'abord
   les stories ouvertes.
4. Si herdr ne repart pas : `window = "terminal"` dans `machine.toml` (ou
   `DELIVERY_WINDOW=terminal` devant la commande), puis `deliveryctl story next <id>`.
5. Gardez-en trace : `deliveryctl note "herdr bloqué : …"`.

## CI et protection de branche

`init` pose la CI des demandes de fusion. Sur une branche `story/<id>` : `check`, les tests d'IHM
de la story, puis `deliveryctl gate <id> --head <sha de tête>` (ordre seul dans le premier
commit, vérification et relecture valides pour l'arbre de code de la tête, aucun fichier protégé
touché). Sur toute autre branche : `check` seul. Complétez l'installation de votre pile (JDK,
Node, navigateurs Playwright…) à l'endroit marqué. Sur GitLab, ajoutez à `.gitlab-ci.yml` :
`include: [{local: .gitlab/delivery-ci.yml}]`. Sans CI qui tourne sur les demandes de fusion, le
moteur n'en fusionne aucune (une demande sans contrôle n'est pas verte) : `deliveryctl doctor`
signale une CI absente ou non commitée.

Protégez la branche cible :

- pas de push direct : tout passe par une demande de fusion, y compris vos commits de GO et le
  travail des leads ;
- CI verte obligatoire : le job `checks` du workflow `delivery` sur GitHub, « Pipelines must
  succeed » sur GitLab ;
- **branches à jour obligatoires** (GitHub : *Require branches to be up to date before merging* ;
  GitLab : *Merge commit with semi-linear history*), pour que la CI juge exactement ce qui sera
  fusionné. Mettre une story à jour change son arbre de code, et ses verdicts ne valent plus :
  `deliveryctl story next <id>` reprend le cycle sur le nouvel arbre ;
- fusion par commit de fusion (squash et rebase désactivés) ; en `integration = "human"`, une
  approbation obligatoire.

## Dépannage

Premier réflexe : `deliveryctl doctor`, puis `deliveryctl story status`.

| Symptôme | Remède |
|---|---|
| `unknown key` à chaque commande | corrigez la clé citée de `delivery.toml` ou de `machine.toml` |
| `origin/HEAD is not set` | `git remote set-head origin --auto` |
| `.delivery/deliveryctl` non exécutable dans git | `git update-index --chmod=+x .delivery/deliveryctl`, puis commit |
| `init` refuse une valeur de `.claude/settings.json` | corrigez à la main la valeur citée, relancez ; rien n'a été écrit |
| aucune notification | `notify_cmd` vide ou non exécutable : les messages vont sur la sortie d'erreur du moteur ; si la commande échoue, la sortie d'erreur montre `[notification failed: …]` |
| `forge unreachable: retry` dans `story status` | la forge ou le dépôt distant ne répond pas (réseau, `gh auth status`, `glab auth status`) ; le moteur réessaie au balayage suivant |
| une story reste `submitted` en `integration = "ai"` | la CI de la demande de fusion n'est pas verte : aucun contrôle (CI absente, voir `deliveryctl doctor`) ou un contrôle en cours ; rouge, vous êtes notifié |
| alerte 🚨 « agent bloqué » | regardez la session (volet `agent`, ou `.delivery/run/logs/`) ; quittez-la (`/exit`, ou `kill` du `pid` noté dans `.delivery/run/sessions/<id>.json`), puis `deliveryctl story next <id>` |
| un rôle se voit refuser une commande légitime | le refus figure dans `report.md` ; ajoutez la règle à `[permissions] extra_allow` |
| `nightly` : `anomalies/<date> already exists with anomaly cards` | triez la demande de fusion en cours, ou lancez la commande de suppression affichée pour relancer |

## Limites de la version 0.1

- Le tri des anomalies se fait en éditant les cartes dans la demande de fusion qui les porte,
  sans outil dédié.
- Un seul decision owner. En solo, les GO de la spec reposent sur le statut que l'analyste pose
  sur votre message ; seule une demande de fusion approuvée les rend vérifiables.
- Une story fusionnée dans l'interface de la forge ne porte pas le trailer `Spec:`, et
  `docs/conformance.md` la montre non fusionnée : fusionnez par `deliveryctl merge`.
- Deux stories en parallèle peuvent choisir le même numéro de carte d'anomalie : renumérotez au tri.
- Le moteur lit les titres des cartes sur la branche cible : une carte qui n'y est pas encore
  (une anomalie écrite sur une branche de story) se nomme par son identifiant seul jusqu'à sa
  fusion.
- Forges : GitHub et GitLab. Suite d'acceptation : Playwright, donc interfaces web. Aucun suivi
  du coût des sessions.

## Licence

MIT, voir [`LICENSE`](LICENSE).
