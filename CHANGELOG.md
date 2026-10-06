# Journal des versions

Chaque version liste ses ajouts, changements et corrections. La rubrique `Contracts` recense
tout changement de [`CONTRACTS.md`](CONTRACTS.md) : tant que le plugin est en `0.x`, un
changement de contrat monte la version mineure ; après 1.0.0, la version majeure.

## 0.4.0

### Ajouts

- `init` en un seul geste : `mkdir todo-spec && cd todo-spec && deliveryctl init spec`. La
  disposition est l'argument (`single`, `spec`, `impl <spec>`, avec un nom pour créer le dossier et
  le dépôt) ; aucune question, un résumé et un seul « o » (`--yes`, `--dry-run`). Sur ce « o », il
  crée le dépôt sur GitHub ou GitLab (`--private`, `--public`, `--internal`), règle l'adresse
  privée d'un dépôt GitHub public, pose les fichiers (avec GitLab, l'`include:` de la CI), commite,
  pousse, protège la branche par défaut, lance `doctor` et donne le prochain geste.
- Les réglages de machine `language`, `visibility`, `forge`, `gitlab_host` et `gitlab_group`, et la
  clé `spec_source` de `delivery.toml` (dépôt `impl` : la spec que lit `spec sync`).
- Un `justfile` qui marche d'emblée dans un dépôt `spec` (`check` lance `spec lint`, `acceptance`
  et `serve` jouent la suite et l'application vide).
- `spec push` : une branche `spec/<incr>` et une seule demande de fusion par incrément de spec,
  ouverte ou mise à jour à chaque GO (commit au trailer `Go:`).
- `spec release` en un seul geste : commit de la version, push, attente des contrôles, fusion de la
  demande, tag `spec-vX.Y.Z` et push du tag ; relancé après un arrêt, il reprend.
- `/impl-frame` propose les quatre recettes du `justfile` et les lignes d'installation de la CI.
- Le raccourci de shell du README marche hors d'un dépôt équipé : il lance le plugin installé le
  plus récent, et `init` passe toujours par lui.

### Changements

- **Rupture.** `init --role` est remplacé par la disposition en argument positionnel
  (`init spec`, `init impl <spec>`) ; `single` reste le défaut.
- **Rupture.** La règle de push des commandes de spec change : `/spec-frame`, `/spec-write` et
  `/spec-review` travaillent sur `spec/<incr>` (elles s'arrêtent sur toute autre branche, en
  donnant la commande pour y passer) et poussent par `spec push` à chaque GO, au lieu de ne jamais
  pousser. L'analyste ne lance toujours ni `git push`, ni tag, ni `spec release`, ni `spec sync`.
- Les cinq questions de `/delivery-method:init` et la relecture avant commit disparaissent : `init`
  déduit tout, commite et pousse lui-même ; la commande Claude montre le résumé, demande « ok ? »
  et passe `--yes`.
- `spec sync` ouvre une demande de fusion (branche `spec-sync/<version>`) sur la branche par défaut ;
  `init --upgrade` fait de même sur une branche protégée (`delivery-method/upgrade-<version>`).
- Les contrôles de CI deviennent obligatoires dans la protection après la première fusion à CI
  verte de `merge` ; dans un dépôt `spec`, dès la création.
- Documentation remise d'accord avec le plugin : équipement, phase de spécification, `spec_source`,
  réglages de machine, verbes et options (README, `CONTRACTS.md` §12.2, guide) ; plus de mention des
  anciennes questions ni de « `init` ne commite rien ».

### Contracts

- §2 : l'équipement par `init` (résumé, « ok », création, adresse, commit, push, protection,
  `doctor`), la protection de la branche par défaut, le `justfile` d'un dépôt `spec`.
- §3 : `spec_source`, la création du dépôt à l'équipement.
- §4 : les réglages de machine `language`, `visibility`, `forge`, `gitlab_host`, `gitlab_group`.
- §12.2 : `init` (disposition, nom, `--private|--public|--internal`, `--yes`), `merge`, `spec push`,
  `spec release`, `spec sync`.
- §14.1 : la branche `spec/<incr>`, `spec push`, le trailer `Go:`.
- §14.4 : `spec release` en un geste.
- §14.5 : `spec sync` par demande de fusion, sa source.

## 0.3.0

### Ajouts

- L'objectif d'un brainstorm : `/brainstorm --vision` (large et peu profond, une longue session)
  ou ciblé (étroit et profond, court), annoncé à l'ouverture ; l'objectif règle la conduite, jamais
  la clôture.
- Les points d'enregistrement : au mot « point », le brainstorm écrit un brouillon
  `docs/maybe/<date>-<slug>.draft.md` (non suivi par git) qui garde les décisions validées mot pour
  mot, qu'un résumé automatique d'une longue session pourrait paraphraser ; le brouillon se reprend
  en le nommant et se supprime à la clôture.
- Le mot de clôture « vision » (dépôt `spec` ou `single`) : les décisions validées passent à
  `/spec-frame <incr> --discover`, et le brief `spec/product/brief.md` est écrit par l'analyste
  produit, commité avec `framing.md` au GO de cadrage. Une décision ferme qui contredit le brief le
  met à jour dans le même cadrage.
- `spec lint` contrôle la neutralité technologique du brief, avec le lexique des stories.

### Changements

- Le guide dit où brainstormer une idée qui sera cadrée : dans la session de l'analyste produit ou
  du lead technique, qui seules ouvrent `/spec-frame` et `/impl-frame`.
- Documentation remise d'accord avec le plugin : verbes et options du moteur (`init`, `campaign`,
  `story open`, `story wait`, `gate`, `merge`, `journal`, `note`), tableau des défauts de
  `delivery.toml`, tableau des skills, sessions et arguments des commandes du guide, installation
  pour l'utilisateur seulement ; plus de titre ni de phrase qui nomme une ancienne version.
- L'aide du moteur : `campaign` ouvre le fichier de campagne d'un lead (il n'y a pas de branche de
  campagne), `qualify` cite `close`, les options de `story` ont leur ligne d'aide.

### Contracts

- §2 : le brainstorm (objectif, brouillon, quatre mots de clôture) et la session où il se tient.
- §3 : les défauts des clés de `delivery.toml`.
- §10 : l'option `--base` de `gate`.
- §12.2 : les options de `init`, `campaign`, `story open`, `story wait`, `merge`, `note`, `journal`
  et `kit lint`.
- §14.1 : le brief, ses deux circuits et son écriture par `--discover`.
- §14.2 : le gabarit du brief.
- §14.3 : la neutralité du brief.

## 0.2.2

### Changements

- Chaque rôle sans surveillance peut lancer `<exécutable> --version` pour l'exécutable de chaque
  commande de `[commands]`, ainsi que `git`, `python3`, `node` et `java` : des règles exactes,
  jamais un motif `* --version`. Une commande chaînée est refusée en entier dès qu'une de ses
  parties sort de la liste : les règles communes demandent une commande par appel Bash.
- Une demande de fusion sans aucun contrôle de CI s'affiche `CI not started yet` pendant les
  `stall_minutes` qui suivent, puis `no CI check for <n> min` (au lieu de `none`).

### Contracts

- §11.1 : les sondes de version du socle commun.
- §12 : la ligne `merge request` de `story status` et ses deux formules.

## 0.2.1

### Changements

- `max_in_flight` vaut `3` par défaut (au lieu de `1`) : c'est un plafond, sous lequel le
  `technical-lead` choisit lui-même entre séquentiel et parallèle ;
  séquentiel est le défaut, et il n'ouvre une seconde story pendant qu'une tourne que s'il est sûr
  qu'elles ne peuvent pas entrer en conflit (zones de code disjointes, aucune dépendance déclarée
  ni implicite), jamais au-delà du plafond.
- Un projet équipé avant garde la valeur écrite dans son `delivery.toml` : passer à `3` est le
  choix du propriétaire. Le nouveau défaut atteint les nouveaux projets et tout `delivery.toml`
  sans cette clé.

### Contracts

- §3 : défaut de `max_in_flight`.
- §12.4 : le choix du lead entre séquentiel et parallèle.

## 0.2.0

Mise à jour d'un projet équipé en 0.1.0 : installez la nouvelle version du plugin, lancez
`/delivery-method:init` (ou `DELIVERY_USE_PLUGIN_ENGINE=1 deliveryctl init --upgrade` depuis le
lanceur du plugin), relisez le diff, commitez. `init --upgrade` copie la méthode dans `.claude/`,
désactive le plugin dans le projet et renomme `/delivery-method:run` en `/run-campaign`.

### Ajouts

- La méthode dans le projet : `init` copie les agents, skills et commandes du plugin sous
  `.claude/` et inscrit leur empreinte dans `.delivery/method.json` ; `init --upgrade` les
  rafraîchit, retire ceux que la version n'a plus et refuse, en les listant, d'écraser un fichier
  modifié à la main. Une session Claude Code sans plugin y trouve toute la méthode.
- Exécutant dans le cloud : réglage `implementer` (`cloud` par défaut avec GitHub, `local` avec
  GitLab) ; le `story-implementer` tourne dans une session cloud (`claude --cloud`), dont le moteur
  rapatrie et contrôle les commits, alerte sur un arrêt de progression et relance sur demande
  (`story next --relaunch`) ; `story status` en montre l'URL.
- Sessions humaines dans le cloud : le moteur du projet y tourne, les hooks du projet aussi ;
  script d'installation de l'environnement cloud (`templates/project/cloud-setup.sh`).
- Hook `PreToolUse` du projet (`deliveryctl hook pre-tool`) : dans une session cloud, il refuse
  sans demande de permission les gestes du propriétaire.
- `doctor` vérifie la copie de la méthode, la confiance accordée au dépôt par Claude Code,
  la connexion `claude.ai` et `origin` avec l'exécutant cloud, et avertit quand un dépôt GitHub
  public publierait l'adresse de commit du propriétaire.

### Changements

- La commande `run` devient `/run-campaign` (`run` prenait le nom d'une commande native de Claude
  Code) ; les commandes copiées n'ont plus d'espace de noms (`/spec-frame`, `/impl-frame`…),
  seule `init` reste `/delivery-method:init`.
- `.claude/settings.json` : plugin désactivé dans le projet dès le premier `init`, hooks `Stop`,
  `SessionStart` et `PreToolUse`.
- Les sessions de rôle lancent l'agent de la copie du projet, sans plugin ; `deliveryctl` y est
  la copie du projet, mise en tête du `PATH` par le moteur et par le hook `SessionStart`.
- Les trailers d'un commit sont lus dans tous les paragraphes consécutifs de fin de message.
- Le lanceur d'un exécutant cloud s'arrête au dialogue de confiance de Claude Code (code 3).
- Une session cloud retrouve sa story sans branche cible, par le commit d'ordre le plus récent.
- Notification ⚠ « commits du cloud refusés ».

### Contracts

- §2 : `.delivery/method.json` et `.claude/{agents,skills,commands}/` ; `.claude/settings.json`
  (plugin désactivé, trois hooks) ; `deliveryctl` du projet en tête du `PATH` ; session cloud ;
  copie de la méthode et refus d'écraser une copie modifiée.
- §3 : réglage `implementer` et son défaut.
- §8 : lecture des trailers dans tous les paragraphes de fin de message.
- §9 : entrées du registre de sessions avec `window` et champs cloud ; rapatriement des commits du
  cloud (candidats, contrôle à la réception, acceptation, refus) ; avancée et alerte d'un
  exécutant cloud.
- §9.2 : hooks dans une session cloud (story servie, arrêt, `session-start`, `pre-tool`).
- §11.1 : lancement du rôle par l'agent du projet, `PATH` du lancement, exécutant dans le cloud.
- §12.1 : gestes refusés dans une session cloud, `story next --relaunch`, `story next --go`.
- §12.2 : `init`, `doctor` et `hook` (diagnostics, copie de la méthode, adresse publique).
- §13 : notification des commits du cloud refusés ; événements `refusal`, `resume` et `stall`
  d'un exécutant cloud.

## 0.1.0

### Ajouts

- Moteur `deliveryctl` (Python 3.11 ou plus, bibliothèque standard seule), copié dans chaque
  projet et lancé par `.delivery/deliveryctl` ; lanceur du plugin `bin/deliveryctl`.
- Installation et diagnostic : `init` (avec `--upgrade` et `--dry-run`, squelette de `spec/`
  pour un dépôt `spec` ou `single`), `doctor` (dont la CI des demandes de fusion et la confiance
  accordée au dépôt par Claude Code), et la commande `/delivery-method:init`, qui pose les cinq
  questions de l'installation.
- Cartes du backlog (`story`, `task`, `anomaly`) : `cards list`, `cards lint`, `cards order`.
- Cycle d'une story dans sa copie de travail git : `story prepare`, `open`, `status`, `next`,
  `wait`, `close` ; vérification (`verify`), contrôle d'intégration (`gate`), demande de fusion
  (`submit`) et fusion (`merge`), sur GitHub ou GitLab ; toute story passe par une demande de fusion.
- Run du `technical-lead` (`run`, `campaign open`) et commande `/delivery-method:run`.
- Sessions de rôle lancées par le moteur, avec un fichier de permissions généré par rôle ;
  enchaînement par le hook `Stop`, rappel de l'état après une compaction, alerte sur un agent
  sans avancée ; refus de permission et reprises portés au journal.
- Port propre à chaque story, et à la suite de nuit, pour tout ce que lance le moteur (`{port}`,
  `DELIVERY_PORT`) ; commande facultative `test` (`just test {selector}`), permise aux rôles pour
  le test ciblé et la morsure.
- Phase de spécification : `spec lint`, `spec release`, `spec sync`, `spec verify` ; commandes
  `spec-frame`, `spec-write`, `spec-review`, `handoff` ; gabarits du cadrage, des stories, du
  rapport de revue, du contrat du harnais, de la suite Playwright et de l'application vide.
- Phase d'implémentation : commande `impl-frame` ; gabarits des cartes, de l'ordre de travail,
  du plan, du compte rendu, de la relecture, de l'architecture, des ADR et de la campagne.
- Phase de recette : `qualify open`, `run`, `lint`, `submit` ; commande `qualify` ; gabarits du
  plan, de l'ordre et du rapport ; suite complète de nuit (`nightly`), dont les cartes
  d'anomalie arrivent par demande de fusion.
- Rôles : `product-analyst`, `spec-reviewer`, `refuter`, `technical-lead`, `story-implementer`,
  `story-reviewer`, `qualification-lead`, `qualification-runner`.
- Skill `brainstorm`, lancé par le seul decision owner : explorer une idée sans rien engager,
  puis oublier, archiver dans `docs/maybe/` ou cadrer ; ce dossier est hors de portée des
  sessions de rôle et hors de toute décision.
- Skills : `framing-discussion`, `spec-writing`, `acceptance-by-role`, `adversarial-review`,
  `anchoring`, `testing-doctrine`, `work-orders`, `qualification-doctrine`.
- Règles communes à toutes les sessions d'un projet (`rules/rules.md`).
- Fenêtres de suivi : un multiplexeur de terminal quand il répond (voir le README), le terminal
  sinon.
- Notifications par une commande de la machine ; journal d'expérience en PostgreSQL, avec une
  file locale de secours (`note`, `journal setup`, `flush`, `report`).
- Gabarits de projet : `delivery.toml`, `CLAUDE.md`, `justfile`, CI GitHub et GitLab.
- Contrôle du plugin lui-même : `kit lint`.
- Noms lisibles : une carte, une story, une anomalie, un contrôle de recette ou une décision se
  nomme `<id> : <titre court>` (`s004 : Partager une liste`) dans les sorties du moteur, les
  notifications, le journal, les sujets de commit, les demandes de fusion, l'espace de travail
  d'une story, les consignes des rôles, les prompts et les gabarits ; titre court obligatoire,
  contrôlé par `cards lint`.

### Contracts

- Première version de `CONTRACTS.md` : vocabulaire ; emplacements dans un projet ;
  `delivery.toml` et réglages de machine ; cartes ; dossier de story (ordre, plan, compte rendu,
  relecture, question produit, état de travail) ; bloc de verdict et identifiant d'arbre de
  code ; voie courte et plan montré ; commits et trailers ; états d'une story et enchaînement ;
  contrôle d'intégration ; rôles et permissions des sessions de rôle ; gestes humains et verbes
  du moteur ; campagne et run ; notifications et journal ; spécification, versions et copie
  dans un dépôt d'implémentation ; recette ; suite de nuit ; codes de sortie. Points notables :
  - référence lisible `<id> : <titre court>` dans tout texte lu par un humain ; identifiant seul
    dans les noms techniques (branche, chemin, trailer, argument) ou quand le titre est inconnu
    (§1) ;
  - substitutions de `[commands]` : `{grep}` et `{port}` par le moteur, qui exporte
    `DELIVERY_PORT` ; `{selector}` par les rôles (§3) ;
  - `reinforced_risks` : une clé écrite remplace le défaut de ce seul risque ; une liste vide
    retire ses contrôles (§3) ;
  - `notify_cmd` en échec : message sur la sortie d'erreur, sans nouvel essai (§4) ;
  - `spec:` d'une carte : un identifiant de story de spec `s<nnn>` (§5) ;
  - `title:` d'une carte obligatoire (`cards lint` : `title: a short title is required`), 3 à 8
    mots visés, noté au-delà de 60 caractères (§5) ;
  - auteur d'un verdict : ligne `By:` et trailer `Agent:` du commit ; registre du moteur de ses
    vérifications et de ses lancements de relecteur, `.delivery/run/verdicts.json` (§6, §10) ;
  - sujets des commits du moteur `order <id> : <titre>` et `verify <id> : <titre> — pass|fail` ;
    fusion `Merge story/<id> : <titre>` ; titre de la demande de fusion
    `<id> : <titre> (story/<id>)` ; report d'une carte `defer <id> : <titre>` (§8) ;
  - `submitted` exige la tête poussée ; fusion automatique sur CI verte seulement (au moins un
    contrôle, tous réussis) ; forge injoignable : `ready-to-submit` sans suite (§9, §12.2) ;
  - relecture sans verdict valide comptée dans `review_loops` ; au plus `review_loops` + 1
    relecteurs par arbre de code (§9) ;
  - session dont la fenêtre ne sait pas dire si elle vit : comptée vivante (§9.1) ;
  - hook `Stop` : `Outcome:` lu sur la dernière ligne non vide ; `done` ou `blocked` seuls
    terminent le run ; `review.md` invalide bloque le premier arrêt du relecteur ; refus de
    permission portés au journal ; question d'une session humaine notifiée (§9.2, §13) ;
  - permissions : écriture des verdicts refusée à l'exécutant, de `verification.md` au
    relecteur ; `--amend`, `git commit -n`, `-f` et `--force` de git, `sort -o` refusés ; lecture
    des copies de stories pour le lead ; scripts de `qualification/kit/` pour le runner (§11.1) ;
  - `story close` d'une story arrêtée : refusé aux rôles par le moteur, hors règles `ask`
    (§12.1) ;
  - `cards list` et `cards order` lisent la branche cible, `cards lint` la copie de travail
    (§12.2) ;
  - format des sorties de `cards list|order|lint`, `story status|wait|next`, `verify` et `gate`
    (§12.2) ;
  - `max_in_flight` ne compte ni les stories arrêtées ni les fusionnées (§12.4) ;
  - notifications une par événement, journal indépendant du canal ; `journal report` par le
    lanceur du plugin, hors de tout dépôt (§13) ;
  - titres des notifications `<id> : <titre> — <quoi>`, titre abrégé au-delà de 90 caractères
    (§13) ;
  - ordre de recette commité : `qualification/order.md` (§2, §15.3) ;
  - décision ferme `D<n> : <titre court> — …` (§14.1) ; contrôle de recette
    `### Q<n> : <titre court>`, lignes de résultat `Q<n> : <titre court>`, anomalies
    `A-<n> : <titre court>` (§15.1, §15.2) ;
  - suite de nuit : son propre port ; reste d'une nuit du même jour supprimé (§16).
