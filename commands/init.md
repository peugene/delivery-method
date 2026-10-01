---
description: "Équipe le dépôt avec la méthode, ou met à jour sa copie du moteur : cinq questions, deliveryctl init, puis relecture et commit par le decision owner"
argument-hint: "[--upgrade]"
---
Target: $ARGUMENTS

## Contract
- Regime: setup (human gesture). The owner answers, reviews and commits; you recommend and
  run the engine.
- Equip this repository with the method through `deliveryctl init`, or refresh its engine copy
  with `--upgrade`.
- Why: sessions, CI and scheduled jobs must run one engine version and read one set of
  settings, and the owner sees every file the method adds before it enters history.
- Scope: a human session at the root of the main checkout. Never edit what init writes,
  never commit.

## Preconditions
Fail closed: on the first failure, say why and stop.
1. `printenv DELIVERY_ROLE` prints nothing: init is a human gesture.
2. The current directory is the first path printed by `git worktree list` (the main checkout).
3. `python3 --version` is 3.11 or later, and `command -v deliveryctl` finds the plugin
   launcher. If not, the plugin is not loaded: point to the installation section of the README.
4. Mode: `delivery.toml` absent → install; present, or `--upgrade` given → upgrade.

## Steps
**Install**
1. Read before you ask: `git remote get-url origin`, the root listing, an existing `justfile`,
   build files (`package.json`, `build.gradle*`, `pom.xml`, `pyproject.toml`, `go.mod`,
   `Cargo.toml`), `spec/`, `refinement/`, `CLAUDE.md`, `.claude/settings.json`.
2. Ask five numbered questions in one message, each with its options, their consequence and
   your recommendation drawn from step 1; "defaults" accepts every recommendation.
   1. Layout (`--role`): `single` (spec and code here), `spec` (the spec only, built
      elsewhere), `impl` (builds a spec published by another repository).
   2. Content language (`--language`): code of the language of every text a human reads
      (cards, orders, reports); recommend the language the owner writes in.
   3. Forge (`--forge`): `github` or `gitlab`; recommend the one of `origin`. Without an
      `origin` remote, stop: the repository needs one on GitHub or GitLab first.
   4. Check (`--check`): lint, build, unit and integration tests, judged on its exit code.
      Default `just check`; in a `spec` repository, a recipe running
      `./.delivery/deliveryctl spec lint` is enough.
   5. UI tests (`--acceptance`, `--serve`): the Playwright suite filtered by `{grep}` (a spec
      story tag, empty for the full suite) and the app of a story served on `{port}`.
      Defaults `just acceptance {grep}` and `just serve {port}`.
   Recommend `just` recipes: init lays down a justfile whose recipes fail until written, so
   an unconfigured check is red, never green.
3. Run one command with the answers in single quotes:
   `deliveryctl init --role <r> --language <l> --forge <f> --check '<c>' --acceptance '<a>' --serve '<s>'`.
   Lever: `--dry-run` first when the owner wants to see the plan.
4. Exit 3: show the engine's message (a value of `.claude/settings.json` that diverges, a forge
   it cannot tell); the owner fixes the file or answers, then run again. A refused init has
   written nothing.

**Upgrade**
1. Compare `DELIVERY_USE_PLUGIN_ENGINE=1 deliveryctl --version` (plugin) with
   `.delivery/VERSION` (project). Not newer: run `deliveryctl doctor`, show it, and stop.
2. Run `DELIVERY_USE_PLUGIN_ENGINE=1 deliveryctl init --upgrade`, so that the plugin's engine,
   not the project copy, performs it. It refreshes `.delivery/`, the copy of the agents, skills
   and commands in `.claude/`, the method's hooks and the marketplace ref, and disables the
   plugin in the project settings. It refuses, with the list, a copied file edited by hand.

**Then, in both modes**
1. Show the engine's summary as printed: each file with its status, notes, next steps.
2. Show `git status --short` and `git diff -- CLAUDE.md .gitignore .claude/settings.json` (the copy in `.claude/` is the plugin's own files, listed by `git status`),
   and ask the owner to review. Give the `git add` line of the summary and a commit command;
   the owner commits, because settings, permissions and conventions are the owner's commits.
3. Next steps, one line each: write the justfile recipes for the stack; the shell alias and
   the machine settings of the README; `deliveryctl doctor`; then the first command of the
   phase: `claude --agent product-analyst` and
   `/spec-frame <incr>` for a spec; `deliveryctl spec sync <version> --source <url>`
   (in `impl`) and `claude --agent technical-lead` with
   `/impl-frame <campaign>` for an implementation.

## Outputs
- Files written by the engine only: `delivery.toml`, `.delivery/`, `CLAUDE.md`,
  `.claude/settings.json`, `.claude/agents|skills|commands/` (the method's copy), `.gitignore`, `justfile`, the CI file of the forge. Nothing committed.

## Ends with
The summary and the owner's gestures (review, commit, next command), then a last line:
`Outcome: done — <installed | upgraded to X.Y.Z>, awaiting the owner's review and commit`,
`Outcome: question — <answer awaited>` or `Outcome: blocked — <reason>`.
