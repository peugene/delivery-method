---
name: brainstorm
description: Explore an idea with the decision owner without committing to anything - vision or targeted, no memory, no note, no file but a draft at the owner's checkpoint - then close on the owner's word - forget, archive, frame or vision. Invoked by the owner only, in a human session, on any topic and at any phase.
argument-hint: "[--vision] <the idea to explore>"
disable-model-invocation: true
---
Idea: $ARGUMENTS (`--vision` sets the vision objective; a path to a draft resumes it)

## When to use
To think an idea through before it becomes work: a product idea, a technical option, a change
of method, any topic, in any repository. Not in a run, not in framing: framing records every
decision, a brainstorm none until the owner closes it. Why: an idea kept as a note or a memory
steers later sessions that never heard it.

## Doctrine
**Discuss as in framing, record nothing.** Read the existing before you speak, give your opinion,
challenge, recommend, plain words, `<id> : <short title>`: the doctrine of
`delivery-method:framing-discussion`, without its records, its batch of questions or its GO.

**Objective.** Announce it at the opening. **Vision** (`--vision`): wide and shallow, a long
session: who the product is for, the problem, a few principles, the big blocks in order. When
the owner dives into one feature, offer to set it aside for a targeted brainstorm and note it.
**Targeted** (default): narrow and deep, short, one idea. In a `spec` or `single` repository
whose `spec/product/brief.md` is empty (only headings, comments and `<…>` placeholders) and
whose `spec/stories/` holds no story, propose vision in one sentence, never impose it. The
objective leads the session, never its closing: every closing word stays open.

**Open.** Restate the idea in a sentence or two, with an honest opinion: what holds, what is
fragile, the unknowns. Offer two or three angles (feasibility, value, impact on what exists,
alternatives) and ask which first. Without an idea, ask what to talk about.

**Slow rhythm.** One or two questions a turn, with counter-examples, hidden assumptions and
neglected alternatives; recommend when you lean. No implementation plan: when the owner starts
listing steps, offer to close with frame. **Write nothing**: no memory, no note, no command that
changes state; only two files may be written, the draft at a checkpoint and the archive the
owner chose. Read only what feeds the discussion; never bring up an earlier brainstorm or draft.

**Checkpoint on the owner's word** (`checkpoint`, in the owner's language, e.g. « point »).
Why: a long session is summarised and the summary can paraphrase the owner's words, which frame
must quote. Write `docs/maybe/<YYYY-MM-DD>-<slug>.draft.md` (date from `date +%F`, slug of the
idea; one file per brainstorm, rewritten whole each time), in the project language. First line:
a brainstorm draft in progress, outside every decision. Then four sections: decisions the owner
validated, each quoted word for word; discarded; open; set aside (topics kept for a targeted
brainstorm). Confirm in one line: path, number of validated decisions. A vision brainstorm
offers one when several decisions were validated since the last, or before a change of topic; a
targeted one only on the owner's word. **Resume**: when the owner names a draft (argument or
message), read it and continue from it.

**Close on the owner's word.** When the owner signals the end, offer the four words (three in
`impl`, where vision is not offered), wait, then say in a line what became of the draft:
- **forget**: nothing is kept; delete the draft if there is one.
- **archive**: write `docs/maybe/<YYYY-MM-DD>-<slug>.md` (date from `date +%F`; suffix `-2`
  if taken), in the project language. It opens with a line saying it is an archive outside
  every decision, then: the idea, the points discussed, for and against, open questions, leads
  for later, from the draft and the discussion since, then delete the draft. Faithful,
  disagreements included, never embellished. Change no other file; the commit is the owner's.
- **frame**: list the validated decisions, quoted, from the draft and since, then delete the
  draft; only they carry over to `/delivery-method:spec-frame` (product idea),
  `/delivery-method:impl-frame` (technical) or the session the owner names.
- **vision** (`spec` or `single` only; in `impl` the technical vision is `docs/architecture.md`,
  framed by `/impl-frame`): list the validated decisions as for frame, word for word, then
  delete the draft; discarded alternatives stay behind. In the `product-analyst` session,
  continue with `/spec-frame <incr> --discover` for the first block to frame (ask its short
  name). In another session, give the two lines to type, `claude --agent product-analyst` then
  `/spec-frame <incr> --discover`, and say to paste the list after the command.

## Defaults and levers
- The owner sets the pace: a numbered batch or a faster close on request.
- `docs/maybe/` is read only for a file the owner names or this session's draft; role sessions
  are refused it. The draft is git-ignored; the archive stays tracked.

## Anti-patterns
- Agreeing by default; an opinion without its reason; a batch of questions, a plan, a recap
  turned into decisions.
- A memory, a note or a `## Deferred` line "to remember"; closing without the owner's word, or
  choosing the closing word for the owner.

## Checks
- No file changed but the draft and the archive the owner chose; no draft left after a closing.
- The archive keeps disagreements; frame and vision carry only validated decisions, quoted.
