---
name: brainstorm
description: Explore an idea with the decision owner without committing to anything - no memory, no note, no file - then close on the owner's word - forget, archive or frame. Invoked by the owner only, in a human session, on any topic and at any phase.
argument-hint: "<the idea to explore>"
disable-model-invocation: true
---
Idea: $ARGUMENTS

## When to use
When the owner wants to think an idea through before it becomes work: a product idea, a
technical option, a change of method, any topic, in any repository. Not in a run, not in
framing: framing records every decision, a brainstorm records none until the owner says frame.
Why: an idea said aloud and kept as a note, an assumption or a memory steers later sessions
that never heard the discussion.

## Doctrine
**Discuss as in framing, record nothing.** Read the existing before you speak, give your
opinion, challenge, recommend, plain words, `<id> : <short title>`: the doctrine of
`delivery-method:framing-discussion`, without its records, its batch of questions or its GO.

**Open.** Restate the idea in one or two sentences. Give an honest opinion: what holds, what is
fragile, the most visible unknowns; never lukewarm out of politeness. Offer two or three
distinct angles (feasibility, value, impact on what exists, alternatives) and ask which comes
first. Without an idea, ask in one sentence what the owner wants to talk about.

**Slow rhythm.** One or two questions a turn. Bring counter-examples, hidden assumptions and
neglected alternatives; recommend when you lean ("I would take X because…"). No implementation
plan: when the owner starts listing steps, offer to close with frame.

**Write nothing.** No memory, no note, no file created or changed, no command that changes
state. Read only what feeds the discussion. Never bring up an earlier brainstorm yourself.

**Close on the owner's word.** When the owner signals the end, offer the three words and wait:
- **forget**: nothing is written; say that nothing is kept.
- **archive**: write `docs/maybe/<YYYY-MM-DD>-<slug>.md` (date from `date +%F`; suffix `-2`
  if taken), in the project language. It opens with a line saying it is an archive outside
  every decision, then: the idea, the points discussed, for and against, open questions, leads
  for later. Faithful to the discussion, disagreements included, never embellished. Change no
  other file; the commit is the owner's gesture.
- **frame**: list the decisions the owner validated, quoted. Only they carry over:
  `/delivery-method:spec-frame` for a product idea (spec repository),
  `/delivery-method:impl-frame` for a technical one, or the session the owner names. Discarded
  alternatives stay behind.

## Defaults and levers
- The owner sets the pace: a numbered batch or a faster close on request.
- `docs/maybe/` is read only when the owner names a file (common rules); role sessions are
  refused its reading.
- The archive is written in the project language, its section names too.

## Anti-patterns
- Agreeing by default; an opinion without its reason.
- A batch of questions, a plan, a recap turned into decisions.
- A memory, a note or a `## Deferred` line "to remember".
- Closing without the owner's word, or choosing the closing word for the owner.

## Checks
- No file changed, except the archive the owner chose.
- The archive reflects the discussion, disagreements and open points included.
- Frame carries only the decisions the owner validated, in the owner's words.
