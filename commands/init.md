---
description: "Équipe le dépôt avec la méthode, sans question : la disposition en argument (single, spec ou impl <dépôt de spec>), un résumé, un seul « ok ? » ; --upgrade met à jour la copie du moteur"
argument-hint: "[single|spec|impl <spec>] [--upgrade]"
---
Target: $ARGUMENTS

## Contract
- Regime: setup (human gesture). The engine deduces everything but the layout, which the
  owner gives as an argument; you show the plan, ask one "ok?", and run it.
- Equip this repository with the method through `deliveryctl init`, or refresh its engine copy
  with `--upgrade`.
- Why: sessions, CI and scheduled jobs must run one engine version and read one set of
  settings, and equipping must take one gesture, not a questionnaire.
- Scope: a human session at the root of the main checkout. Never edit what init writes.

## Preconditions
Fail closed: on the first failure, say why and stop.
1. `printenv DELIVERY_ROLE` prints nothing: init is a human gesture.
2. The current directory is the first path printed by `git worktree list` (the main checkout).
3. `python3 --version` is 3.11 or later, and `command -v deliveryctl` finds the plugin
   launcher. If not, the plugin is not loaded: point to the installation section of the README.
4. Mode: `--upgrade` given → upgrade; otherwise install (`delivery.toml` present: init keeps it).

## Steps
**Install**
1. Run `deliveryctl init $ARGUMENTS --dry-run` and show its summary as printed: each file with
   its status, then the notes (layout and forge deduced).
2. Ask the owner one question: "ok?". Do not ask about language, forge, check or UI tests: the
   engine deduces them, and the owner edits `delivery.toml` afterwards if needed.
3. On "ok", run `deliveryctl init $ARGUMENTS` and show its next steps.
4. Exit 1 (usage, e.g. `impl` without a spec repository) or 3 (a value of
   `.claude/settings.json` that diverges, no `origin` remote, a forge it cannot tell): show the
   engine's message and stop; a refused init has written nothing.

**Upgrade**
1. Compare `DELIVERY_USE_PLUGIN_ENGINE=1 deliveryctl --version` (plugin) with
   `.delivery/VERSION` (project). Not newer: run `deliveryctl doctor`, show it, and stop.
2. Run `DELIVERY_USE_PLUGIN_ENGINE=1 deliveryctl init --upgrade`, so that the plugin's engine,
   not the project copy, performs it. It refreshes `.delivery/`, the copy of the agents, skills
   and commands in `.claude/`, the method's hooks and the marketplace ref, and disables the
   plugin in the project settings. It refuses, with the list, a copied file edited by hand.
3. Show the summary; the owner reviews the diff of `.delivery/` and `.claude/`.

## Outputs
- Files written by the engine only: `delivery.toml`, `.delivery/`, `CLAUDE.md`,
  `.claude/settings.json`, `.claude/agents|skills|commands/` (the method's copy), `.gitignore`,
  `justfile`, the CI file of the forge, a `spec/` skeleton for `spec` and `single`.

## Ends with
`Outcome: done — <installed | upgraded to X.Y.Z>` or `Outcome: question — ok? awaited` or
`Outcome: blocked — <reason>`.
