---
description: Run autonome du technical-lead - enchaîne les cartes prêtes dans l'ordre des dépendances, un ordre de travail par story, sans s'interrompre
argument-hint: "<campagne>"
---
Target: $ARGUMENTS

## Contract
- Regime: impl (decide and record, or defer). The run never stops for a question: decide and
  record it in the order, or defer the card with a written reason, and go on.
- Chain the ready cards of the target branch, in dependency order, until nothing is launchable.
- Why: the owner's attention goes to decisions and merges; each story starts from an order
  anchored in the real code.
- Scope: the `technical-lead` in run mode, an unattended role session started by
  `deliveryctl run`; skills `delivery-method:anchoring` and `delivery-method:work-orders`. The
  engine chains the roles of each story; you prepare, anchor, write orders, open, wait, decide.

## Preconditions
Fail closed: on the first failure, say why and end with `Outcome: blocked — <reason>`.
1. `printenv DELIVERY_ROLE` prints `technical-lead`: a run is started by the owner.
2. The campaign is the argument, else `printenv DELIVERY_CAMPAIGN`; `docs/campaigns/<name>.md` exists.
3. Resuming (crash, `/clear`, compaction): read `## Next` of the campaign file, then
   `docs/campaigns/work/<name>/notes.md` and `deliveryctl story status`; finish open stories first.

## Steps
1. Read the campaign file, `delivery.toml` (`max_in_flight`, `integration`, `[levers]`),
   `CLAUDE.md` and `docs/architecture.md`.
2. `deliveryctl cards order`: a line without `(waits for …)` is launchable, unless the story is
   already open or you deferred the card in this run.
3. For each launchable card, in that order:
   a. `deliveryctl story prepare <id>`, right before opening: it creates the worktree from the
      head of the target branch and prints the order skeleton in it.
   b. Anchor in that worktree without `cd` (your shell stays in the main checkout, where you
      commit): read its files by absolute path; search with `git grep <pattern> story/<id>`
      and `git ls-tree -r --name-only story/<id>` (the base until it opens): the card, its spec
      story, every file, symbol and route it names, their callers; re-check the facts anchored
      ahead. Probe what the card depends on with what your role may run; else the fact line says
      `not probed — to probe by the implementer: <mechanism>`.
   c. Write the order in place: fill `campaign:` and `path:`, keep `base:` (the worktree head,
      `git rev-parse story/<id>`). A card that needs a product decision is deferred (step 4).
   d. `deliveryctl story open <id>`, then loop on `deliveryctl story wait <id>` with a Bash
      timeout of 10 minutes; read each exit code with step 7. Between two waits, step 5.
   e. On the state returned:
      - `merged`: `deliveryctl story close <id>` (`closed`: nothing to do); next card.
      - `submitted`: open another card if `max_in_flight` allows and it does not depend on this
        story; otherwise `deliveryctl story wait <id> --until merged`.
      - `blocked`, `deferred`, `verify-exhausted`, `review-exhausted`: read `report.md` and the
        file it points to (`spec-question.md`, `verification.md`, `review.md`), then defer the
        card with that reason (step 4); the story stays stopped for the owner.
      - `plan-ready`: the owner reads the plan; note it for the owner and go on.
   f. Read the report with the grid of `work-orders`; carry what it teaches into the next orders.
4. To defer a card: `status: deferred` in its `backlog/` file, a line `Deferred: <reason>` under
   `## Technical notes`, one commit (subject `defer <id> : <title>`, never `story/<id>`: a target
   history naming the branch counts as merged), pushed with step 8; its dependents wait for the owner.
5. The next card, while waiting, and only it: do not prepare it. Read it at the head of the
   target branch with `git fetch`, then `git show origin/<target>:<path>` and
   `git grep <pattern> origin/<target>`, never in the main checkout, which may lag behind.
   Anchor only the facts independent of the running story, declared (`depends_on`) or implicit
   (a file, type, port, schema or migration it creates or changes); keep the others in your
   notes as "to reconfirm after merge". Prepared after the merge, it starts from the new head.
6. Sequential is the default; open a second story while one runs only when sure they cannot
   conflict (disjoint code zones, no `depends_on`, no implicit dependency: file, type, port,
   schema, migration), never beyond `max_in_flight`; in doubt, sequential. Rewrite
   `docs/campaigns/work/<name>/notes.md` at each transition: in flight, next, deferred, decisions, refusals.
7. Exit codes of `deliveryctl`. 2: a red check; fix what it names in the order. 3: read the
   `deliveryctl:` line or the printed state: a dependency or `max_in_flight` → wait for the
   running story; `anchored before … was merged` → re-anchor at the target head, update `base:`;
   `already open` → `story wait`; `still running` → wait again. 1: a malformed command or an
   internal error. Other failures and refused commands: note them; go on without, or end blocked.
8. When nothing is launchable: rewrite `## Run` of the campaign, each card as `<id> : <title>`
   (stories merged or submitted, decisions taken and where they are written, deferred cards and
   why, refusals met, points for the owner with the gesture each needs) and `## Next`; commit on
   `campaign/<name>` (trailers `Campaign: <name>`, `Agent: technical-lead`), `deliveryctl campaign
   push`, and give the URL in `## Run` and your last message.

## Outputs
- `order.md` per story, deferred cards, campaign file: commits on `campaign/<name>`, pushed by `campaign push`.

## Ends with
The last line of your last message, and nowhere before, ends the run: `Outcome: blocked — <reason>`
or `Outcome: done — <n> merged or submitted, <n> deferred, <n> stopped`.
