---
id: s001
title: <short title>     # 3 to 8 plain words, what the user gets; cited `s001 : <title>`
status: draft            # draft | ready
---
<!-- spec/stories/<id>-<slug>.md, in the project language; keywords, headings and Given/When/Then in English. -->
<!-- One story = one user goal. Describe what the user sees and does, never how it is built. -->
<!-- ready = implementable on any stack without a product question: lint green, no open question. -->
<!-- Lift a lint finding with one line: lint-exempt: <rule> — <reason>. Rules: schema (draft only), neutrality, extension, coverage, orphan-tag, test-tag. -->

## Business rules
- BR-1 <one observable rule>

## Main flow
1. <actor> <action> (`<area.label-key>`).
2. <what the user observes>.

## Extensions
<!-- One top-level item per extension: "- <step><letter>. <condition>: <what happens>". Each extension has at least one @ext-<label> criterion. Write "none" when there is none. -->
- 2a. <condition>: <what happens>

## Acceptance criteria
<!-- One line per criterion: "- AC<n> @main|@ext-<label> — Given …, When …, Then …". Numbers are never reused: removing a criterion leaves a gap. -->
<!-- A test covers AC<n> with @<id>-ac<n> in its title and carries @<id> (its title or its describe title). -->
- AC1 @main — Given <context>, When <action>, Then <observable result>
- AC2 @ext-2a — Given <context>, When <action>, Then <observable result>

## UI contract
<!-- Every label the tests look for: its key in spec/ui/copy.<locale>.json and its accessible role. -->
| Key | Role | Where |
|---|---|---|
| `<area.label-key>` | button | <screen or area> |

## Outcomes
<!-- Non-functional results with a threshold, each proved by a criterion; "none" otherwise. -->
none

## Out of scope
- <what this story deliberately does not do>

## Open questions
<!-- Empty or "none" before status: ready. -->
