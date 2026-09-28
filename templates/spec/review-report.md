---
increment: <increment id>
size: deep               # light | standard | deep
reviewed-commit: <short commit of the spec repository that was reviewed>
lint: <green | red, n findings>
---
<!-- refinement/<increment>/reviews/<date>.md, in the project language. The review finds; it does not fix. -->
<!-- Mandate: the Firm decisions stand; everything the writer derived (bounds, thresholds, assumptions) may be attacked. -->
<!-- A compatibility finding with no external holder named in external_contracts is a note. -->

## Angles
<One line per angle kept, removed or added for this increment, with the reason in a few words.>

## Findings
<!-- Most severe first; refuted findings go to "Refuted". Severity: blocking | to-decide | note. -->
<!-- Refuter: CONFIRMED, or NUANCED with the severity it corrected. -->
| # | Severity | Target | Finding | Evidence | Recommendation | Refuter |
|---|---|---|---|---|---|---|
| 1 | <severity> | <s001 AC2, framing.md Scope…> | <fact, then what breaks> | <path:line, or command and exit code> | <change> | <verdict> |

## For the decision owner
<Each to-decide finding: the problem in one plain sentence, lettered options with their consequence, one recommendation. "none" if there is none.>

## Refuted
<One line per refuted finding: - <finding> — <the refuter's reason>. "none" if there is none.>

## Synthesis
<Two or three sentences: what holds, what blocks, what the next GO needs.>

<!-- Spec ready: yes only without a blocking or to-decide finding. -->
Max severity: <blocking | to-decide | note | none>
Spec ready: <yes | no>
