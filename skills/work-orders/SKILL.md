---
name: work-orders
description: How the technical-lead writes a work order (docs/stories/<id>/order.md) that a mid-range agent carries out without a question, and how it reads the report that comes back. Used before every `deliveryctl story open` and after every story stop.
---
## When to use
Before `deliveryctl story open <id>`, and each time a story comes back with its `report.md`.
Why: the order is the only channel to the implementer and outlives both sessions; what it
leaves out becomes a guess, what it gets wrong becomes code.
Scope: one order per card, in the prepared worktree; one card, one logical change.

## Doctrine
**Writing the order.** Start from the skeleton written by `story prepare`; project language,
section names in English, about `max_order_lines` lines (default 60).
- Frontmatter: keep `id` and `base` (the commit where you read the facts); fill `campaign`;
  `path: short` only when the card has no risk, the change stays under `short_path_max_lines`,
  no data schema or API changes, and `show_plan` is false; otherwise `path: plan`.
- `## Objective`: one sentence, the observable result.
- `## Decisions`: the owner's decisions that apply, quoted word for word with their date and
  where they are written; closed unless a new fact appears; "none". Never your own.
- `## Proposal`: the approach you suggest and why; the implementer may depart and says so.
- `## Constraints`: scope, files not to touch, the follow-up work not to start (name it), your
  binding technical choices with their one-line reason, and what to do with a surprise:
  inside the story, decide and record it under `## Deviations`; outside (another module, an
  external contract, the product), a `## Findings` line or `Outcome: deferred`.
- `## Read at base — re-verify, do not trust`: one fact per line, `path:line`, labelled read,
  measured or inferred. Give what the implementer would otherwise search for: entry points,
  signatures, guards, fixtures, the commands that work and how long they take.
- `## Reinforced checks`: for each risk of the card, the checks listed under
  `[levers] reinforced_risks` of `delivery.toml` (default: `authz` gets bite and
  adversarial-review; `data-write`, `file-upload`, `data-leak` get adversarial-review), each
  with the invariant or the angle aimed at. Another risk: "noted in the report". No risk: "none".
- `## Deliverables`: one per line with its expected proof, `command → result`. Every Oracle
  line of the card is a deliverable; the spec criteria are referred to, never copied.

**Anticipation.** While a story runs, anchor the next card only, at the head of the target
branch, without preparing it. A fact that depends on a card not merged yet, declared in
`depends_on` or implicit (a file, type, port, schema or migration that card changes), never
enters an order: keep it in your notes as "to reconfirm after merge" and write the order after
that merge.

**Reading the report**, in this order:
1. `Outcome:` and its reason; then `## Verified points`: each refuted fact is a lesson for the
   next orders (what you read wrong, and where).
2. `## Deviations`: each one acceptable? A choice that binds later cards goes into your notes
   and into the next orders.
3. `## Oracle`: every line measured, or "not measured" with a reason you accept.
4. `## Findings` and `## For the decision owner`: carry them to `## Run` of the campaign; a
   defect not yet in `backlog/` becomes an anomaly card.

## Defaults and levers
- `path: plan` by default; `short` only under the four conditions above.
- An order over `max_order_lines` is a signal, not a stop (`story open` only warns). If the
  card holds two logical changes, defer it with that reason; otherwise cut `Read at base` down
  to what the implementer cannot find quickly, then open it.
- The owner may change `max_order_lines`, `short_path_max_lines` or `reinforced_risks` in
  `[levers]`: read `delivery.toml`, do not assume the defaults.

## Anti-patterns
- Rephrasing an owner decision, or presenting your recommendation as the owner's.
- Copying the spec criteria into the order instead of referring to the spec story.
- Facts from memory, or a `path:line` copied from a search result without opening the file.
- Anchoring several cards ahead; writing a fact that depends on an unmerged card.
- "TBD", "as usual", "see the code": an order that needs a question is not an order.
- Two logical changes in one order, or one change spread over two orders.

## Checks
- `deliveryctl story open <id>` accepts the order (sections, frontmatter, `base` containing the
  dependencies of the card).
- Every `Read at base` line has its `path:line` and its label; every deliverable its proof.
- Every risk of the card has its reinforced check, or the line saying it is only noted.
- Nothing in the order depends on an unmerged card.
