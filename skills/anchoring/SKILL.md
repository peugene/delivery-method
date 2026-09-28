---
name: anchoring
description: How to establish a fact before passing it on or acting on it - code over documentation, a guard read from its real input, searches that can fail, state checked after a change, level 2 probes, and the read / measured / inferred label. Used by the technical-lead, the story-implementer and the story-reviewer.
---
## When to use
Before you write a fact into an order, a plan, a report, a review or a card; before you act on
what a document, a card or another session says; after any command meant to change state.
Why: work built on an imagined picture of the code is coherent, green and wrong; lint and tests
check that the code matches *a* plan, never that it is the right one.
Scope: every fact you pass on or rely on, in any phase.

## Doctrine
**Label every fact**: *read* (`path:line`), *measured* (command and exit code) or *inferred*.
Write "not verified" rather than guess. One source read twice is one confirmation.

**Code over documentation.** Check every documentation claim you rely on against the code, and
list every page that makes it: the code decides; a page that disagrees is a finding.

**Read a guard from its real input**: the value that actually reaches it (the request the real
client sends, the row the real writer stores, the file the real tool produces), not the one
you imagine.

**Search the subject, not the symptom**: the route, the table, the permission, under several
spellings; not the words of the error message.

**An empty search proves nothing** until the same search, same flags, finds a known positive.

**After a state-changing command, check the state**, not the exit code: `git log -1 --stat`
after a commit, `deliveryctl story status <id>` after `story open`, a query after a migration.

**Measure what you publish.** No number without a measurement when the source is reachable;
keep the command next to the figure. Read the exit code before the output; never silence
stderr on a measurement.

**Two levels.** Level 1 reads: `path:line` says what the code says, not what it does. Level 2
probes: every mechanism the work depends on (a build step, a guard, a migration tool, a test
filter, a harness route) gets a throwaway probe with a witness both ways, one case that must
pass and one that must fail, and its result is written down. A probe beats a paragraph.

**Facts expire.** A fact is true at a commit: give the commit. A fact that depends on work not
merged yet is not acquired: write it "to reconfirm after merge".

**Agreeing needs the same proof as disagreeing**, with the decision owner as with a card.

## Defaults and levers
- Default: level 1 for every fact you pass on; level 2 for every mechanism the work depends on
  that the commands your role may run can exercise (in a role session: the `[commands]` of
  `delivery.toml` and `extra_allow`). Otherwise the fact line (`Read at base` in an order) says
  `not probed — to probe by the implementer: <mechanism>`.
- Lever: skip a probe whose cost exceeds the risk, and write "not probed — <reason>" where the
  fact is used; the next reader re-verifies it.
- Probes and their notes live in the `work/` folder of your story or campaign, not only in `/tmp`.
- A probe you are not allowed to run is not worked around: note the refusal in your report
  (`report.md`; for the technical-lead, the campaign notes, then `## Run`).

## Anti-patterns
- Facts written from memory of "how such projects usually look".
- A `path:line` taken from a search result without opening the file.
- `grep -c` or a filter that prints 0 when the tool fails; `2>/dev/null` on a measurement.
- A document, a card or a report quoted as proof of what the code does.
- Confirming the owner's opinion, or a reviewer's, without reading the input it is about.
- A figure from memory in an order or a card: it ends up quoted as a fact.

## Checks
- Every fact passed on carries its label and its source.
- Every empty search has its known positive; every state change is followed by a state read.
- Every probe is written down with its command, its two witnesses and its result.
