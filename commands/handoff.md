---
description: Passation avant /clear, qui consigne dans leurs fichiers ce qui a été décidé sans être écrit, réécrit la section Next et donne la ligne de reprise
argument-hint: "[<incr> | <campaign>]"
---
Target: $ARGUMENTS

## Contract
- Regime: spec (discuss). The owner sees the list before anything is written as decided;
  the same in any human session of a lead.
- Before a `/clear`, move what this session knows but the files do not into the files, then
  leave the next step where a fresh session finds it.
- Why: the files are the state; a fresh session resumes from them, not from memory or from
  a compacted conversation.
- Scope: human sessions of a lead (`product-analyst`, `technical-lead` in framing,
  `qualification-lead`). Rewrites only the `## Next` section of the state file.

## Preconditions
Fail closed: on the first failure, say why and stop.
1. `printenv DELIVERY_ROLE` prints nothing: an unattended role ends with its report instead.
2. The state file is known: `refinement/<incr>/framing.md` for an increment of the spec,
   otherwise `docs/campaigns/<campaign>.md`. Without an argument, take the one this session
   worked on; if two are possible, ask which.

## Steps
1. List what this session decided, assumed, deferred or found that no file holds yet. For
   each point: one line, its destination (file and section), and for a decision the owner's
   words quoted with the date. A card, story or decision is named `<id> : <short title>`.
   - product decision, assumption, deferred point: `framing.md`, its section;
   - open product question: `## Open questions` of the story;
   - technical decision: the card, the order or an ADR; campaign question: `## Questions`;
   - defect found: an anomaly card or a finding line of the report in progress.
2. Submit the list to the owner, numbered. Write only what the owner confirms, as corrected.
   Nothing goes into memory.
3. Write each confirmed point into its file and section.
4. Rewrite `## Next` of the state file, and only that section:
   - the next step in one line, and the command that performs it;
   - questions waiting for the owner, if any;
   - `Read first:` at most five files, most useful first.
5. Commit the files written, with trailers `Campaign: <incr or campaign>` and
   `Agent: <role of this session>`; never push.

## Outputs
- The confirmed points in their files; `## Next` rewritten; one commit.

## Ends with
The exact line to paste after `/clear`, on its own line: the command of the next step with its
argument (for example `/delivery-method:spec-write 01-core`), or
`Read docs/campaigns/<campaign>.md, section Next first, then continue.`
Then `Outcome: done — handoff written, resume with the line above`.
