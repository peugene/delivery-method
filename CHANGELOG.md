# Journal des versions

Chaque version liste ses ajouts, changements et corrections. La rubrique `Contracts` recense
tout changement de [`CONTRACTS.md`](CONTRACTS.md) : tant que le plugin est en `0.x`, un
changement de contrat monte la version mineure ; après 1.0.0, la version majeure.

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
