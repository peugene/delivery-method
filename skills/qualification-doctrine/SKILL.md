---
name: qualification-doctrine
description: Doctrine of the qualification phase (observe and record) - surface drawn from the code, negatives by default, material versus product failures, replay rather than date, installation and removal as tests, evidence as a verdict plus one line. Load it to plan, run or synthesize a qualification.
---
Doctrine of the third regime: observe and record.
Why: stories are verified one diff at a time; only a qualification shows what the assembled
product does off the planned path and whether what it claims is true.
Scope: the `qualification-lead`, the `qualification-runner` and the refuters the lead calls.

## When to use
- Planning, running or synthesizing the qualification of an increment, in one implementation.
- Writing an anomaly card from a control, a reading or the night run of the full UI suite.

## Doctrine
- **Observe and record.** The product does not change during a qualification. Only the
  qualification material (plan, kit, test data) may be repaired, and every repair is declared.
- **Object.** The whole increment, installed from its docs, in real use, and every claim it makes
  (docs, error messages, announced checks). The acceptance suite is the starting point, not replayed.
- **Surface over requirement matrix.** Spec criteria already have their tests. Gaps hide in entry
  points of the code that nothing exercises. `## Surface` is drawn from the code (routes,
  commands, scheduled tasks, triggers, installation, removal, upgrade), redrawn every time; each
  row names its controls or `not covered — <reason>`.
- **Negatives by default** on each risk declared in the increment's cards:

  | Risk | Default negative |
  |---|---|
  | `authz` | the same request by a third account, and by no account |
  | `migration` | upgrade over a populated base, then read the old data |
  | `scheduling` | move the clock; restart during and after the due time |
  | `data-write`, `data-leak` | what a non-privileged account reads or changes, errors and exports too |
  | `file-upload` | oversized, wrong type, hostile name |
  | other | one control that tries to break the promise the risk names |

- **Two modes.** Reading: every promise of the docs is re-verified in the code; a reading anomaly
  gets its card at once, then a refuter's verdict added to it, or becomes a run control. Running:
  the runner re-verifies what the committed order says, and gives a proof per control.
- **Material or product.** A failure is `material` (stale test data or request: repaired during
  the qualification and declared) or `product` (the product disagrees with its docs, the spec or
  the expected result: an anomaly). When unsure, it is `product`.
- **Replay rather than date.** A full qualification replays every run control: stale material
  breaks at once. Between two qualifications, `Touches:` marks controls as suspect: a signal, not a gate.
- **Installation and removal are tests.** Setup follows the installation doc to the letter on a
  clean environment; a gap is a doc anomaly. Teardown proves nothing is left: containers,
  volumes, files, secrets. Upgrade starts from the last delivered version when there is one.
- **Test data** comes with the kit and goes through the public paths (UI, API, CLI), which are
  tested on the way; never through the acceptance harness, never in the product's catalogue.
- **Evidence** is the verdict plus one line per control (command, decisive observed value). Raw
  outputs are disposable and re-playable; working state lives in `qualification/work/`, never `/tmp`.
- **Anomalies** are written as cards at once (`kind: anomaly`, `status: to-triage`), never only
  in a message or a memory. A security anomaly is `blocking` by default. An anomaly where the
  spec is silent goes back to the spec: the card says `spec is silent`, the owner carries the
  question to the next spec increment, and it is checked in every implementation.

## Defaults and levers
- Size: `standard` by default (reading by parallel angle subagents blind to each other: docs
  against code, security negatives, operations, coverage; then a refuter per finding; then a
  runner). Lever: `light` (the lead reads alone, then a runner) for a small increment.
- Frequency: every increment, in every implementation; a full qualification per delivered
  version, before any delivery to a third party.
- Verdict proposal: open `blocking` → `rejected`; open `to-decide` → `accepted-with-reserves`.
  The owner's approval of the merge request is the verdict.
- Qualification material stays out of CI by default. Lever: a regression seen twice in
  qualification earns a card that moves its control into the project tests.

## Anti-patterns
- Fixing the product during a qualification, even one line or a doc typo.
- A surface copied from the docs or the spec; only the nominal path; negatives left to chance.
- A pass without a proof line; a proof under `/tmp`; raw logs committed as evidence.
- Trusting an order, a plan or a reading without re-verifying it; dating instead of replaying.
- Working around a doc gap or a refused command; skipping teardown because the run failed.
- An anomaly left in a conversation or a memory.

## Checks
- Every row of `## Surface` names controls or `not covered — <reason>`.
- Every risk declared in the increment's cards has at least one negative control.
- Setup, teardown and every run control have a result and a one-line proof; the counts add up.
- Every product failure has a `to-triage` card with `found: <incr>/Q<n>@<commit>`.
- `## Read` and `## Run` are filled or say why they are empty.
- `git status` shows no change outside `qualification/` and new anomaly cards.
- `deliveryctl qualify lint <incr>` exits 0.
