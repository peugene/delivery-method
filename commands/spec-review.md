---
description: Relecture contradictoire de la spec d'un incrément, avec taille et angles annoncés, un relecteur par angle, un réfuteur par constat et une synthèse datée
argument-hint: "<incr> [deep|standard|light] [--acceptance]"
---
Target: $ARGUMENTS

## Contract
- Regime: spec (discuss). The review finds and recommends; the decision owner decides at the
  GO close.
- Review the stories (or, with `--acceptance`, the tests) of one increment from independent
  angles, re-check every finding, and write one dated report.
- Why: the writer cannot see its own gaps; unchecked findings flood the owner with noise.
- Scope: the session of the lead (usually `product-analyst`) orchestrates and synthesises;
  `spec-reviewer` and `refuter` subagents; skill `delivery-method:adversarial-review`.
  Nothing in `spec/` or `framing.md` changes during the review.

## Preconditions
Fail closed: on the first failure, say why and stop.
1. The current branch is `spec/<incr>`, else stop and print `git switch spec/<incr>`.
   `refinement/<incr>/framing.md` has status `framed` and the stories of its scope exist; with
   `--acceptance`, status `closed` and the tests exist.
2. `git status` shows no change under `spec/` or `refinement/<incr>/`: the review reads one
   commit. Otherwise: "commit first".
3. Run `deliveryctl spec lint` and keep its result for the report.

## Steps
1. Announce, then wait for the owner's GO review:
   - size: `deep` by default (angles, refuters, completeness pass), `standard` (angles and
     refuters) or `light` (one reviewer for all angles, refuters); no cap on agents;
   - angles: coverage of the firm decisions and the scope; technology-neutral
     implementability (what product questions would two teams on two stacks ask?);
     testability (observable by role and label, numbered thresholds, time through `tick`);
     neutrality and slicing (leaks the lexicon misses, one story per user goal); plus angles
     specific to the increment (for sharing: "what does an account without rights see?").
   - With `--acceptance`: `light` by default; does each Then have its assertions, are tags,
     locators and harness use as the skill `delivery-method:acceptance-by-role` says?
2. Build each reviewer prompt: the angle, the file paths (stories, copy, `framing.md`), the
   mandate (firm decisions firm, all derived detail attackable), `release_stage`,
   `external_contracts`, the bound of 12 findings. The coverage angle receives the numbered
   firm decisions, the scope and the exclusions, verbatim. Never your own summary.
3. Launch the reviewers in parallel with the Workflow tool, agent type
   `delivery-method:spec-reviewer`, one per angle; play the implementability angle at the
   implementer's range (model `sonnet`, effort `medium`). Without Workflow, use the Agent tool,
   one reviewer after another.
4. Send each non-conforming finding, as soon as it arrives, to a fresh
   `delivery-method:refuter` with the finding, its paths and the mandate, never the reviewer's
   reasoning. With `deep`, one more reviewer then receives the confirmed findings and looks
   only for what no angle covered; its findings go to refuters too.
5. Synthesise yourself: re-check the heavy points on the files; drop `REFUTED`; keep
   `CONFIRMED` and `NUANCED` (with the corrected severity); merge duplicates.
6. Write `refinement/<incr>/reviews/<date>.md` (`date +%F`; add `-2` on a second review that
   day), in the project language:
   - head: size, angles, reviewed commit (`git rev-parse --short HEAD`), lint result;
   - findings by severity, each with target (`s004 : Share a list, AC2`), evidence and
     recommendation;
   - each `to-decide` as a decision request: the problem in one sentence, lettered options
     with their consequence, one recommendation;
   - refuted findings, one line each with the reason;
   - last two lines: `Max severity: <blocking | to-decide | note | none>` and
     `Spec ready: <yes | no>` (`yes` only without a blocking or to-decide finding).
7. Commit the report (`Campaign: <incr>`, `Agent: product-analyst`, `Go: review`, or
   `Go: acceptance` with `--acceptance`), then run `deliveryctl spec push` and give the pull
   request URL. Correct nothing now; if the owner asks for a correction during the review,
   rerun the angles it touches.

## Outputs
- `refinement/<incr>/reviews/<date>.md`, committed on `spec/<incr>` and pushed.

## Ends with
The numbered `to-decide` points with their recommendation, the blocking ones, and the next
step (`/delivery-method:spec-write <incr>` for the corrections and the GO close), then
`Outcome: question — <n> points for the decision owner` or
`Outcome: done — spec ready, awaiting the GO close`.
