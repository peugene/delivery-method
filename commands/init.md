---
description: "Équipe le dépôt avec la méthode après un seul « ok » : crée le dépôt sur la forge s'il manque, commite, pousse et protège la branche par défaut ; --upgrade met à jour la copie du moteur"
argument-hint: "[single|spec|impl <spec>] [nom] [--public|--private|--internal] [--upgrade]"
---
Target: $ARGUMENTS

## Contract
- Regime: setup (human gesture). The engine deduces everything but the layout, which the
  owner gives as an argument; you show the summary, ask one "ok?", and run it.
- Equip this repository with the method through `deliveryctl init`, or refresh its engine copy
  with `--upgrade`. A name argument (`init spec todo-spec`, `init impl todo-spec todo-kotlin`)
  creates the folder and the repository on the forge; so does a folder that is not a repository,
  or a repository without `origin`. GitHub and GitLab alike.
- Why: sessions, CI and scheduled jobs must run one engine version and read one set of
  settings, and equipping must take one gesture, not a questionnaire and a string of forge steps.
- Scope: a human session. Never edit what init writes.

## Preconditions
Fail closed: on the first failure, say why and stop.
1. `printenv DELIVERY_ROLE` prints nothing: init is a human gesture.
2. In a git repository, the current directory is the first path printed by `git worktree list`
   (the main checkout). A folder that is no repository is fine: init creates it.
3. `python3 --version` is 3.11 or later, and `command -v deliveryctl` finds the plugin
   launcher. If not, the plugin is not loaded: point to the installation section of the README.
4. Mode: `--upgrade` given → upgrade; otherwise install (`delivery.toml` present: init keeps it).

## Steps
**Install**
1. Run `deliveryctl init $ARGUMENTS --dry-run` and show its summary as printed: the folder, the
   repository to create or the `origin` found, the layout, the git address, the branch of the
   commit, the protection, then the files with their status and the notes. It writes nothing and
   changes nothing on the forge.
2. Ask the owner one question: "ok?". Do not ask about language, forge, visibility, check or UI
   tests: the engine deduces them (machine settings, options), and the owner edits
   `delivery.toml` afterwards if needed.
3. On "ok", run `deliveryctl init $ARGUMENTS --yes` (the owner's "ok" is the confirmation) and show
   its output. It creates the repository when there is none, sets the git address of a public
   GitHub repository, commits what it laid down, pushes it and protects the default branch: do
   none of this by hand. Show the notes (a forge that refuses a protection setting names it) and
   the diagnosis it prints.
4. Exit 1 (usage, e.g. `impl` without a spec repository, `--internal` on GitHub), 3 (a value of
   `.claude/settings.json` that diverges, a forge it cannot tell, a folder that is not empty,
   another branch than the default one) or 5 (a forge command failed, a refused push): show the
   engine's message and stop. Exit 1 or 3 wrote nothing; after exit 5 the files are written and
   the message says what remains.

**Upgrade**
1. Compare `DELIVERY_USE_PLUGIN_ENGINE=1 deliveryctl --version` (plugin) with
   `.delivery/VERSION` (project). Not newer: run `deliveryctl doctor`, show it, and stop.
2. Run `DELIVERY_USE_PLUGIN_ENGINE=1 deliveryctl init --upgrade --dry-run`, show the summary,
   ask the owner "ok?", then run it again with `--yes` instead of `--dry-run`, so that the
   plugin's engine, not the project copy, performs it. It refreshes `.delivery/`, the copy of the
   agents, skills and commands in `.claude/`, the method's hooks and the marketplace ref, disables
   the plugin in the project settings, commits that refresh and pushes it. It refuses, with the
   list, a copied file edited by hand.
3. Show the output. On a protected default branch the push is refused: the engine moves the
   refresh commit to the branch `delivery-method/upgrade-<version>`, puts the default branch
   back on its remote head and opens a merge request; give its URL, the owner merges it. When
   even that push is refused, the commit stays local: say so.

## Outputs
- Files written by the engine only: `delivery.toml`, `.delivery/`, `CLAUDE.md`,
  `.claude/settings.json`, `.claude/agents|skills|commands/` (the method's copy), `.gitignore`,
  `justfile`, the CI file of the forge (with GitLab, its `include:` in `.gitlab-ci.yml`), a `spec/`
  skeleton for `spec` and `single`; one commit of those paths, pushed.

## Ends with
`Outcome: done — <installed | upgraded to X.Y.Z>` or `Outcome: question — ok? awaited` or
`Outcome: blocked — <reason>`.
