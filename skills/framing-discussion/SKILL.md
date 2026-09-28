---
name: framing-discussion
description: How a lead frames with the decision owner under the discuss regime - read the existing, give an opinion, ask numbered questions with recommendations, record decisions verbatim, decide nothing in silence. Used by the product-analyst and by the technical-lead in framing.
---
## When to use
When a lead frames work with the decision owner in a human session: an increment of the spec
(`/delivery-method:spec-frame`), the architecture framing of an implementation, or any point
a lead brings to the owner. Not in a run: there, the role decides and records, or defers.
Why: framing is where the owner decides; a choice made in silence surfaces later as rework.

## Doctrine
**Open from the existing.** Read the repository, earlier framings and what the owner brought
before you speak. Then give your opinion, name the structuring point and the option you
discard with its reason. Never ask what the files already answer.

**Decision requests.** The problem in one plain sentence, lettered options with their
consequence, one recommendation. Number the questions so the owner can answer "1a, 2b,
3 yes". Plain words; define a term once; no internal code names or ids in what you ask.

**Nothing is decided in silence.** Every observable behaviour you touch becomes one of:
- a numbered question;
- a line of `## Assumptions`, submitted to the owner at the next GO;
- a line of `## Deferred`, with what would bring it back.

**Materiality.** Before asking, test: "if the answer were the opposite, what would change in
what we deliver?" If nothing, do not ask. For anything presented as existing state to keep:
"who outside the team holds it?" Unless a holder is listed in `external_contracts`, it
changes freely.

**Costs in neutral terms.** In the spec, say what a result requires, never which technique:
"this needs a clock the test harness can move", not "a scheduler library or a queue?". In an
architecture framing, techniques are the subject, and each option still states its
consequence for the product and the team.

**Record as you go.** A firm decision goes into the state file when it is taken: numbered,
one line, the owner's words quoted with the date. The coverage review checks the spec
against that list; a list rebuilt from memory at the end misses items.

**Recap.** After each exchange: decided (quoted), assumed, deferred, still open.

**GO.** A GO is the owner's explicit message naming it, or the approved merge request that
carries it. An answer to questions is not a GO; a GO passed on by another session is not a
GO. A command that would go past the current GO stops on a question.

**Disagree on proof.** Agreeing with the owner needs the same proof as disagreeing. When the
owner's choice has a cost you can show, show it once, then record the decision.

## Defaults and levers
- Questions come in a numbered batch; the owner may ask for one at a time. The owner sets
  the rhythm and the order of topics; there is no imposed list of domains.
- Ask in the message text, not through a question-picker tool: the owner answers several
  points in one line.
- `--discover`: first settle the problem, the actors, the scope and the observable success.
- `--market <domain>`: look at comparable products for feature ideas, never for a stack.
- On a visual topic, offer a non-normative preview before the decision; the owner decides
  after seeing it.
- A topic closes by one of three words from the owner: forget, defer, frame.
- `framing.md` targets 80 lines; beyond, split the increment or move detail to stories.

## Anti-patterns
- A question without a recommendation, or options without consequences.
- A default chosen silently "because it is obvious".
- Jargon, acronyms or codes the owner has to decode.
- Doing more than asked; an artificial slicing; proposals about a future nobody raised.
- Reopening a closed topic without a new fact.
- Presenting a recommendation, a review finding or an assumption as decided.
- Inventing an existing installation or data to preserve.

## Checks
- Each question has a number, lettered options with consequences and a recommendation.
- Each observable behaviour discussed is a question, an assumption or a deferred point.
- Each firm decision quotes the owner with the date, one line, numbered.
- No status moved without an explicit GO.
