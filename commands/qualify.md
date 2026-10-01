---
description: Recette d'un incrément — surface lue dans le code, lecture critique, exécution déléguée, rapport et verdict proposé
argument-hint: <incr>
---
Qualify increment `$ARGUMENTS` of this implementation, as the qualification-lead.
Why: an increment is fit to deliver only if, installed from its docs, it holds in real use and
every claim it makes is true.
Scope: one increment of one implementation, from the opening of the qualification to its hand-over.

## Contract
Regime: qualification (observe and record). The product does not change; only qualification
material may be repaired, and each repair is declared.
- Roles: `qualification-lead` (this session, with the owner); `qualification-runner`
  (unattended, launched by the engine); `delivery-method:refuter` (subagent, reading anomalies).
- Owner: triages each anomaly and gives the verdict by approving the merge request opened by
  `deliveryctl qualify submit <incr>`. Only the owner submits.
- Load the skill `delivery-method:qualification-doctrine`.

## Preconditions
- An increment is named; never guess it. Its stories are merged on the target branch
  (`deliveryctl cards list`).
- The session runs as the lead (`claude --agent delivery-method:qualification-lead`); if not,
  say so, and go on only on the owner's word.
- Size agreed with the owner: `standard` by default, `light` as a lever (see the skill).

## Steps
1. **Open.** `deliveryctl qualify open <incr>`: worktree on branch `qualification/<incr>`, with the
   skeletons of plan, order and report. Work in that worktree. If it exists, resume from
   `qualification/work/notes.md`, the plan, the report, then `git status`.
2. **Plan.** In `qualification/plan.md`, redraw `## Surface` from the code; add or update controls:
   negatives on each declared risk, setup, teardown, upgrade from the last delivered version.
   List as suspect the controls whose `Touches:` changed since the last report (its commit:
   `git log -1 --format=%h -- <last report>`, then `git diff --name-only <commit> HEAD`).
   A run control uses only what the runner may run: read-only shell, git, docker, docker
   compose, curl, just, the project commands, `extra_allow`. The kit's material runs with
   `bash qualification/kit/<script>`, `just --justfile qualification/kit/justfile <recipe>` or
   `docker compose -f qualification/kit/<file> …`. A control that needs more names the rule to
   add: ask the owner to add it before `deliveryctl qualify run`. Commit.
3. **Read.** In `standard`, first run the reading angles as parallel subagents, blind to each
   other. Re-verify each promise of the docs in the code, each fact labelled read, measured or
   inferred. Each anomaly goes into the report at once as `A-<n> : <title>`. Either it becomes a
   run control (a failure gets its card from the runner), or its `to-triage` card is written at
   once, then a refuter re-checks it (finding, evidence, severity) and you add its verdict to the
   card: `REFUTED` is the counter-proof, and the owner drops the card at triage. Fill `## Read`.
   Commit.
4. **Order.** Fill `qualification/order.md` in the project language, with the sections of
   the order template: `base:` the commit under test; `## Objective`; `## Decisions` (the
   owner's words, verbatim, dated, or "none"); `## Controls to run` (setup first, teardown last;
   every run control for a full qualification); `## Environment`; `## Read by the lead —
   re-verify, do not trust` (`<fact> (<path:line>, read | measured | inferred)`);
   `## Constraints`; `## Deliverables` (a `## Results` row and its proof per control);
   `## Failure classification` (material or product). Commit it: `qualify run` refuses an
   order with uncommitted changes, and git keeps each version the runner received.
5. **Run.** `deliveryctl qualify run <incr>` starts the runner and returns: follow it where the
   engine says. In a cloud session it is refused (`CLAUDE_CODE_REMOTE=true`): commit and push,
   and ask the owner to merge this session's pull request, then run it from their computer. Do not commit in the worktree until its commit, whose `## Run` ends with
   `Outcome:`. If it ends `blocked`, read why, repair the order or the material, commit, and
   run again; a product cause is an anomaly.
6. **Synthesize.** Reproduce each product failure before counting it (or ask a refuter). Check the
   runner's `Env:`, rows and `## Run`; complete `## Results` for read controls, `## Anomalies`
   (`A-<n> : <title>`, severity, its card or run control), `## Not covered`, the proposed verdict
   block, `By: qualification-lead`. `Tree:` and `Spec:` come from the engine. Commit.
7. **Lint.** `deliveryctl qualify lint <incr>` until exit 0; fix the plan or the report, never
   the product.
8. **Hand over.** Ask the owner to run `deliveryctl qualify submit <incr>` (from their computer
   after merging this session's pull request, when this is a cloud session) and to triage each
   anomaly in that merge request: fix (the card matures to `ready`), defer, drop, or "spec is
   silent" (a question the owner carries to the spec).

## Outputs
- `qualification/plan.md`, `qualification/order.md`, `qualification/reports/<incr>.md`,
  `qualification/kit/**` if needed.
- Anomaly cards `backlog/a<nnn>-<slug>.md` in `to-triage`.
- Commits on `qualification/<incr>`, trailer `Agent: <role>`; nothing pushed. `qualification/work/`
  stays out of git and is never evidence.

## Ends with
A message to the owner, in the project language: proposed verdict and its reason in one line;
counts pass, fail, blocked, not-run; anomalies by severity, each card as `a<nnn> : <title>`; entry
points not covered; decisions awaited, each as one plain sentence with lettered options, their
consequence and one recommendation; the gesture `deliveryctl qualify submit <incr>`.
Last line: `Outcome: done|blocked|question — <reason>`.
