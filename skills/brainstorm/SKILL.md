---
name: brainstorm
description: Explore an idea with the decision owner without committing to anything - no memory, no note, no file - then close on the owner's word - forget, archive or frame. Invoked by the owner only, in a human session, on any topic and at any phase.
argument-hint: "[--vision] <the idea to explore>"
disable-model-invocation: true
---
Idea: $ARGUMENTS (`--vision` sets the vision objective; a path to a draft resumes it)

## When to use
When the owner wants to think an idea through before it becomes work: a product idea, a
technical option, a change of method, any topic, in any repository. Not in a run, not in
framing: framing records every decision, a brainstorm none until the owner says frame.
Why: an idea kept as a note or a memory steers later sessions that never heard the discussion.

## Doctrine
**Discuss as in framing, record nothing.** Read the existing before you speak, give your
opinion, challenge, recommend, plain words, `<id> : <short title>`: the doctrine of
`delivery-method:framing-discussion`, without its records, its batch of questions or its GO.

**Objective.** Announce it at the opening. **Vision** (`--vision`): wide and shallow, a long
session: who the product is for, the problem, a few principles, the big blocks in order. When
the owner dives into the detail of one feature, offer to set it aside for a targeted brainstorm
and note it, instead of digging. **Targeted** (default): narrow and deep, short, one idea. In a
`spec` or `single` repository whose `spec/product/brief.md` holds only its title and whose
`spec/stories/` holds no story, propose the vision objective in one sentence, never impose it.
The objective sets how the session is led, never how it closes: every closing word stays open.

**Open.** Restate the idea in one or two sentences. Give an honest opinion: what holds, what is
fragile, the most visible unknowns; never lukewarm out of politeness. Offer two or three
distinct angles (feasibility, value, impact on what exists, alternatives) and ask which comes
first. Without an idea, ask in one sentence what to talk about.

**Slow rhythm.** One or two questions a turn. Bring counter-examples, hidden assumptions and
neglected alternatives; recommend when you lean ("I would take X because…"). No implementation
plan: when the owner starts listing steps, offer to close with frame.

**Write nothing.** No memory, no note, no command that changes state; exactly two files may
be written: the draft at a checkpoint and the archive the owner chose. Read only what feeds
the discussion. Never bring up an earlier brainstorm or draft yourself.

**Checkpoint on the owner's word** (`checkpoint`, in the owner's language, e.g. « point »).
Why: a long session is summarised automatically and the summary can paraphrase the owner's
words, which frame must quote. Write `docs/maybe/<YYYY-MM-DD>-<slug>.draft.md` (date from
`date +%F`, slug of the idea; one file per brainstorm, rewritten whole each time), in the
project language. First line: the draft of a brainstorm in progress, outside every decision.
Then four sections: decisions the owner validated, each quoted word for word; discarded; open;
set aside (topics kept for a targeted brainstorm). Confirm in one line: the path and the
number of validated decisions. A vision brainstorm offers one when several decisions were
validated since the last, or before a change of topic; a targeted one only on the owner's word.
**Resume**: when the owner names a draft (argument or message), read it and continue from it.

**Close on the owner's word.** When the owner signals the end, offer the three words and wait:
- **forget**: nothing is kept; delete the draft if there is one.
- **archive**: write `docs/maybe/<YYYY-MM-DD>-<slug>.md` (date from `date +%F`; suffix `-2`
  if taken), in the project language. It opens with a line saying it is an archive outside
  every decision, then: the idea, the points discussed, for and against, open questions, leads
  for later, from the draft and the discussion since, then delete the draft. Faithful to the
  discussion, disagreements included, never embellished. Change no other file; the commit is
  the owner's gesture.
- **frame**: list the decisions the owner validated, quoted, from the draft and since, then
  delete the draft. Only they carry over:
  `/delivery-method:spec-frame` for a product idea (spec repository),
  `/delivery-method:impl-frame` for a technical one, or the session the owner names.
Say in one line what became of the draft.

## Defaults and levers
- The owner sets the pace: a numbered batch or a faster close on request.
- `docs/maybe/` is read only when the owner names a file, or for the draft this session wrote;
  role sessions are refused it. The draft is git-ignored; the archive stays tracked.

## Anti-patterns
- Agreeing by default; an opinion without its reason.
- A batch of questions, a plan, a recap turned into decisions.
- A memory, a note or a `## Deferred` line "to remember".
- Closing without the owner's word, or choosing the closing word for the owner.

## Checks
- No file changed, except the draft and the archive the owner chose; no draft left after a closing.
- The archive keeps disagreements; frame carries only validated decisions, in the owner's words.
