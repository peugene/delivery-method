---
description: Cadrage d'architecture d'une implémentation avec le technical-lead - architecture, ADR, cartes en brouillon, conventions proposées
argument-hint: "<campagne> [sujet]"
---
Target: $ARGUMENTS

## Contract
- Regime: impl (decide and record, or defer) — framing itself is discussed with the owner:
  each structuring choice is a numbered question with your recommendation, or a listed assumption.
- Frame the architecture of this repository and write the cards of the next run in `draft`.
- Why: in a run, a mid-range agent executes each card without question or decision; every
  decision it would need is taken here, with the owner, or written into the card.
- Scope: the `technical-lead` in framing mode, in a human session; skills
  `delivery-method:framing-discussion` and `delivery-method:anchoring`. The product is not
  reframed here: a product question is put to the owner, who carries it to the spec.

## Preconditions
Fail closed: on the first failure, say why and stop.
1. `printenv DELIVERY_ROLE` prints nothing, and this session runs the `technical-lead` agent.
   Otherwise print `claude --agent delivery-method:technical-lead` and stop.
2. `delivery.toml` has `repo_role` `impl` or `single`, and the spec to build is in `spec/`
   (in `impl`, `deliveryctl spec verify` is green).
3. The campaign is named: `docs/campaigns/<name>.md` exists, else run
   `deliveryctl campaign open <name> --phase impl`. When it exists, read its `## Next` first.

## Steps
1. Read before you speak: `delivery.toml`, `CLAUDE.md`, `spec/` (brief, glossary, stories,
   harness contract), `docs/architecture.md`, `docs/adr/`, `backlog/`, and the code, if any.
2. Open with your view: the structuring point, the option you set aside and why, then numbered
   questions with lettered options, their consequence and your recommendation. The owner sets
   the pace. Record each answer at once, quoted with its date, where it applies (an ADR, a
   card), and until then under `## Questions` of the campaign.
3. Write `docs/architecture.md`, one page, from `.delivery/templates/impl/architecture.md`, and
   one ADR per structuring choice, `docs/adr/<nnnn>-<slug>.md` from `adr.md`. Technology lives
   here, never in `spec/`.
4. Write the cards in `backlog/`, all `status: draft`, from `card-story.md` and `card-task.md`:
   - one story card per spec story, same id, `spec:` set; its Oracle refers to the spec
     criteria and adds only the implementation measures, each with its threshold, then
     `Not tested by this card:`;
   - task cards for technical work outside the spec (project skeleton, CI, test harness routes);
   - each card executable without a question: files, routes and components named,
     `depends_on` and `risks` set, sized for one order of 60 lines; `show_plan: true` only
     as an exception the owner asks for.
   Then `deliveryctl cards lint` must be green.
5. Propose the `## Project conventions` for `CLAUDE.md` (layers, naming, code language, the
   commands of `delivery.toml`) as a ready-to-paste block. The targeted test is named
   `just test <selector>`, with the selector syntax of the stack and the body of the `test`
   recipe of the `justfile`: roles may run it (implementer's work, reviewer's bite). A test
   command other than `just test` comes with its `[permissions] extra_allow` rule, proposed
   with it. The owner edits `CLAUDE.md`, the `justfile` and `delivery.toml`, and commits them.
6. Commit the architecture, the ADRs, the cards and the campaign file, trailers
   `Campaign: <name>` and `Agent: technical-lead`, without push. Rewrite `## Next`.

## Outputs
- `docs/architecture.md`, `docs/adr/`, draft cards in `backlog/`, the campaign file; content in
  the project language, section names in English.
- The conventions text, the `test` recipe and any `extra_allow` rule, in the conversation only.

## Ends with
A summary: files written, draft cards in dependency order, questions still open, and the
owner's next gestures: commit the conventions, pass the cards to `ready` by a commit on the
target branch, then `deliveryctl run --campaign <name>`. Last line:
`Outcome: done — <summary>`, or `Outcome: question — <what the owner must decide>`.
