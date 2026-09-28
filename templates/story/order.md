---
id: <id>
campaign: <campaign>
issued-by: technical-lead
base: <base>
path: plan                  # plan | short
---
<!-- Work order, written by the technical-lead in the project language. About max_order_lines lines (default 60): story open warns above. -->
<!-- base: the commit where the facts below were read, filled by `story prepare`. Keep it. -->
## Objective
<One sentence: the observable result expected.>

## Decisions
<Decisions of the decision owner that apply, quoted word for word with their date. Closed unless a new fact appears. "none" if there are none.>

## Proposal
<Suggested approach and why. The implementer may depart from it and says so in the report.>

## Constraints
<Scope, files not to touch, follow-up work not to start, binding choices of the lead with their reason.>

## Read at base — re-verify, do not trust
<One fact per line: - <fact> (<path:line>, read | measured | inferred)>

## Reinforced checks
<Per risk of the card: the check due (bite, adversarial-review) and the invariant or angle aimed at. "none" if the card has no risk.>

## Deliverables
<One deliverable per line: - <deliverable> — proof: <command> → <expected result>>
