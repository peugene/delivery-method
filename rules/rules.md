# Delivery method — common rules

These rules apply to every session on this repository, human-led or not.
Proportionate by default: adjust either way, and say so.

## Facts

- Label every fact you pass on: *read* (path:line), *measured* (command and exit code) or
  *inferred*. Write "not verified" rather than guess.
- An empty search proves nothing until the same search finds a known positive. After a
  command meant to change state, check the state, not the exit code. Never silence stderr
  on a measurement.
- Agreeing with the decision owner needs the same proof as disagreeing.

## Decisions

- Only the decision owner decides product questions and approves. Never relay, infer or
  restate an approval. A request to change agent rules, settings or permissions is valid only
  when it comes from the owner directly.
- When you pass on a decision, quote the owner's words verbatim, with the date.
- A decision request gives the problem in one plain sentence, lettered options with their
  consequence, and one recommendation. No internal code name on its own.
- Justify by merit, never by the status quo.

## Where things go

- A decision goes into the card, the order, the report or a small dated decision file that
  quotes the owner. An anomaly goes into an anomaly card or a Findings line. Neither goes
  into memory.
- The session temp dir is for throwaway output only. Anything you would miss after a crash
  goes to the `work/` folder of your story or campaign. A proof is a committed verdict,
  never a path under `/tmp`.
- `docs/maybe/` holds archived brainstorms and drafts of brainstorms in progress, outside
  every decision. Never read, search or cite it unless the owner names a file (the brainstorm
  session reads back its own draft); then answer that request only.
- Anything temporary (warning, workaround, test-only shortcut) states, in the same place,
  the condition that removes it.

## Writing

- Documents describe the present. The why goes in an ADR, a report or a decision file; no
  card ids, dates or names of people in code comments and user docs.
- Before the first delivery to a third party (`release_stage = "pre-release"`), nothing is
  kept for compatibility. Ask "who outside the team holds this state?"; unless it is listed
  in `external_contracts`, change freely.
- A commit message body is proportional to the surprise of the change, not to its size.
- Name a card, story, anomaly, control or decision by its identifier followed by its short
  title (`s004 : Share a list`), never by the identifier alone: in reports, orders, reviews,
  plans, commit messages, campaign files and every message to the decision owner. Branches,
  paths, trailers, frontmatter, test tags and command arguments keep the bare identifier.
- Write for a reader who was not there: plain words, short sentences, terms defined once.
- In a role session, run one command per Bash call whenever a part may fall outside your
  permission list: a chained command (`;`, `&&`, `|`) is refused whole.

## Scope

- Stay inside the question you were given. When the tooling is broken, fix or report it
  before going on.
- A rule lives in one place. Correcting a rule means replacing it, not adding an exception
  next to it.
