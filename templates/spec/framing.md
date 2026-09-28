---
id: <increment, e.g. 01-first-lists>
status: discussing       # discussing | framed | closed
scope: []                # spec stories of the increment, e.g. [s001, s002]
---
<!-- refinement/<increment>/framing.md: the only state file of the increment. 80 lines aimed at; rewrite, never pile up. -->
<!-- Four human GOs: framing (framed), review, closing (closed), publication (tag). Solo: the analyst sets the status on an explicit message of the decision owner; team: the approved merge request. -->
<!-- Product only: a technical question goes to "To investigate", worded in neutral terms, for the technical-lead. -->
<!-- A story or a decision is always named `<id> : <short title>` (`s004 : Share a list`, `D3 : <short title>`), never by its bare id. -->

## Purpose
<The problem and the observable result expected, in two or three sentences.>

## Firm decisions
<Product decisions of the decision owner, one line each: - D1 : <short title> — <decision> — "<owner's words>" (<date>). Closed unless a new fact appears. "none" if there are none.>

## Scope
<What the increment delivers, one line per capability.>

## Exclusions
<What it deliberately does not deliver, with the reason in a few words.>

## To investigate
<Technical questions for the technical-lead only, in neutral terms, each stated as the observable result it conditions. Product questions are asked to the owner, never parked here.>

## Assumptions
<What the writer derived and the owner has not approved yet (bounds, thresholds, defaults). Each is accepted or rejected at the next GO.>

## Deferred
<Points left for a later increment, with what triggers their return.>

## Story map
<One line per story: - s001 : <short title, 3 to 8 plain words> — <user goal> — depends on: <s00n : short title, or none> — covers: <D<n> : short title, or none>.>

## Next
<Next step and the files to read first. Rewritten at every handover.>
