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
  (`submit`) et fusion (`merge`), sur GitHub, GitLab ou sans forge.
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
- Skills : `framing-discussion`, `spec-writing`, `acceptance-by-role`, `adversarial-review`,
  `anchoring`, `testing-doctrine`, `work-orders`, `qualification-doctrine`.
- Règles communes à toutes les sessions d'un projet (`rules/rules.md`).
- Fenêtres de suivi : un multiplexeur de terminal quand il répond (voir le README), le terminal
  sinon.
- Notifications par une commande de la machine ; journal d'expérience en PostgreSQL, avec une
  file locale de secours (`note`, `journal setup`, `flush`, `report`).
- Gabarits de projet : `delivery.toml`, `CLAUDE.md`, `justfile`, CI GitHub et GitLab.
- Contrôle du plugin lui-même : `kit lint`.

### Contracts

- Première version de `CONTRACTS.md` : vocabulaire ; emplacements dans un projet ;
  `delivery.toml` et réglages de machine ; cartes ; dossier de story (ordre, plan, compte rendu,
  relecture, question produit, état de travail) ; bloc de verdict et identifiant d'arbre de
  code ; voie courte et plan montré ; commits et trailers ; états d'une story et enchaînement ;
  contrôle d'intégration ; rôles et permissions des sessions de rôle ; gestes humains et verbes
  du moteur ; campagne et run ; notifications et journal ; spécification, versions et copie
  dans un dépôt d'implémentation ; recette ; suite de nuit ; codes de sortie. Points notables :
  - substitutions de `[commands]` : `{grep}` et `{port}` par le moteur, qui exporte
    `DELIVERY_PORT` ; `{selector}` par les rôles (§3) ;
  - `reinforced_risks` : une clé écrite remplace le défaut de ce seul risque ; une liste vide
    retire ses contrôles (§3) ;
  - `notify_cmd` en échec : message sur la sortie d'erreur, sans nouvel essai (§4) ;
  - `spec:` d'une carte : un identifiant de story de spec `s<nnn>` (§5) ;
  - auteur d'un verdict : ligne `By:` et trailer `Agent:` du commit ; registre du moteur de ses
    vérifications et de ses lancements de relecteur, `.delivery/run/verdicts.json` (§6, §10) ;
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
  - `max_in_flight` ne compte ni les stories arrêtées ni les fusionnées (§12.4) ;
  - notifications une par événement, journal indépendant du canal ; `journal report` par le
    lanceur du plugin, hors de tout dépôt (§13) ;
  - ordre de recette commité : `qualification/order.md` (§2, §15.3) ;
  - suite de nuit : son propre port ; reste d'une nuit du même jour supprimé (§16).
