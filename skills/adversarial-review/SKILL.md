---
name: adversarial-review
description: Mechanics of an adversarial review in any phase - independent angles with evidence, a refuter per finding, verdict before reading the author's, three attacks on a flawless result, read versus probe, no number without measurement. Used by spec-reviewer, refuter, story-reviewer and the leads that synthesise a review.
---
## When to use
When a spec, a change, a qualification report or any result is reviewed against its sources,
and when a finding is re-checked.
Why: a review that restates the author finds what the author already saw; independent
attacks with evidence find the rest.
Scope: spec review, story review, qualification; the session that launches the review
writes the synthesis, never a subagent.

## Doctrine
**Angles, blind to each other.** One reviewer per angle, each reading the sources itself.
Give reviewers the files and the mandate, never your summary of them. The coverage angle
receives the full numbered list of firm decisions, scope and exclusions, and checks each
item: covered, contradicted, or missing.

**Mandate.** The owner's firm decisions are firm. Everything derived from them is attackable:
bounds, thresholds, assumptions, wording, a technical detail inside a decision. A
compatibility finding without an external holder named in `external_contracts` is a `note`.

**Evidence or nothing.** Each finding carries `path:line` or a command with its exit code, and
what breaks if it is not fixed. An absence is shown by the search run and a known positive
the same search finds. A finding names its target story, card, control or decision
`<id> : <short title>` (`s004 : Share a list`), never by its bare id.

**Your verdict first.** Write your own verdict before reading the author's report, summary or
verdict. Then compare, and say where you differ.

**Reproduce the gesture, not the state.** Check what a user does (click, submit, wait), not a
target state set by hand and then observed.

**A flawless result gets three attacks**, each written with its result:
- empty success: it passes because nothing ran (0 tests, an empty list, a skipped step);
- hidden regression: something next to the change broke;
- polluted measurement: the measure saw something else (cache, stale build, other
  environment, stderr silenced).

**Two levels.** Level 1, read: cite what the code or text says. Level 2, probe: what it does
when run. Any mechanism the result depends on is probed when reachable: a one-minute
disposable command with a witness both ways (one case that must pass, one that must fail).
A probe beats a paragraph.

**No number without measurement.** When the source is reachable, count; keep the command
next to the number. A figure written from memory ends up quoted as a fact.

**Refute by default.** Each non-conforming finding goes to a fresh refuter that re-checks from
zero: `CONFIRMED`, `REFUTED` or `NUANCED` (fact right, severity or scope wrong). Two readings
of one source are one confirmation. Only confirmed and nuanced findings reach the synthesis.

**Concede.** When the other side has the better proof, concede and say so.

## Defaults and levers
- Size, chosen at each review: `deep` by default (angles, refuters, then a completeness pass
  that looks only for what no angle covered); `standard` (angles and refuters); `light` (one
  reviewer, all angles, refuters). No cap on the number of agents.
- Story review (the story-reviewer, a single session without subagents): play each angle the
  order names yourself, with the three attacks; no size, no refuter.
- 12 non-conforming findings per reviewer by default; the launcher may set another bound.
- An implementability angle is played at the range of the executor that will build.
- No correction during a review; a correction made anyway reruns the angles it touches.

## Anti-patterns
- A flawless result accepted without the three attacks.
- Findings of style or taste; a finding that restates a firm decision as a defect.
- The reviewer fixing what it reviews; the author reviewing its own work alone.
- A recommendation of the review presented as the owner's decision.
- Counting the same source twice; silencing stderr on a measurement.

## Checks
- Each finding has evidence and a materiality sentence; in a spec review or a qualification,
  each non-conforming one has a refuter verdict.
- Each flawless result lists its three attacks and their results; in a story review, one
  line each under `## Reinforced checks`: `adversarial-review: <angle> — <result>`.
- Each number in the report has its command or is marked "not measured".
