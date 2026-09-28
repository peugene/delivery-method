---
name: testing-doctrine
description: What to test in a story, at which layer, which checks run when (targeted tests, check, the story's UI tests, the nightly full suite), how a check guards its own preconditions, and how to investigate a red build. Used by the story-implementer and the story-reviewer.
---
## When to use
When you write, run or judge tests in a story.
Why: a suite can grow by dozens of tests and still ship its central rule untested; volume is
not a net, and a false red costs as much as a false green.
Scope: the tests of one story, in its worktree; the full UI suite belongs to the night.

## Doctrine
**When each check runs**
- During the work: the targeted tests of what you change (the `test` command of
  `delivery.toml`), then the `check` command before each commit. Never commit red.
- Unit and integration tests run at every story (`check`). The story's UI tests (`acceptance`
  with `@<spec>`) block its integration; the engine runs both at verification.
- Never the full UI suite per story: it runs at night (`deliveryctl nightly`) and its failures
  become anomaly cards.
- The reviewer does not replay what `verification.md` proved on the same tree; it runs only the
  tests a bite targets, on the broken tree: the `test` command, or without one `check`, whose
  output must show that the aimed test is the one failing.

**What a test is worth**
- A test that stays green when the rule it names is removed is worse than no test: it hides the
  hole it claims to cover.
- One rule, one test, at the layer where the rule lives: business rules and access policy in the
  domain; adapters test parsing and mapping, never a refusal again; the permission matrix once.
- Shapes that do not bite: a hand-written query instead of the code under test; a payload the
  real interface never sends; a catch that swallows the failure; an end-to-end check green on
  zero rows; a fixture that lets another guard answer; a mock that replays the clause.

**How a check behaves**
- A check first asserts its own preconditions (server up, fixture present, at least one test
  run) and fails loudly when one is missing. Zero tests run is red.
- Acceptance starts from a new client's state: data through the interface and the harness
  routes only.
- Setup and teardown are tests: they have expected results.
- The suite under `spec/acceptance/` is never edited in an implementation repository.
- No test is deleted, skipped or disabled without saying so in the report, with the reason and
  the condition that brings it back.

**A red build** is investigated from its cause, not from its symptom: read the exit code and the
first error, reproduce the smallest failing case, check the premise (environment, port, stale
build or fixture: a false red) before touching code. Fix the code or the premise, never the
assertion to match the code. After about three honest attempts on the same red, stop and
report the evidence.

## Defaults and levers
- Default: the targeted test is the `test` command of `delivery.toml` (`just test <selector>`);
  the `## Project conventions` of `CLAUDE.md` give the selector syntax and the layers. In a
  role session, another test command is refused unless `[permissions] extra_allow` allows it.
- Lever: a test at a second layer when that layer adds a behaviour of its own; say which.
- Lever: a performance or volume threshold is tested only when the card's Oracle names it.

## Anti-patterns
- `--passWithNoTests`, skipped tests, a `check` that exits 0 without running a test.
- The whole suite after every edit; the full UI suite in a story.
- Weakening an assertion, a timeout or a gate to go green.
- A test named after an invariant it never reaches.

## Checks
- Each business rule of the story has one test at its layer, and it fails when the rule is removed.
- Each acceptance criterion of the spec story is covered by its tagged spec test, unchanged.
- The report's `## Proof` lists every command run with its exit code and counts.
- No test was removed, skipped or disabled silently.
