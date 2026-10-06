---
description: Rédige les stories, le contrat d'IHM et les libellés d'un incrément cadré, applique les décisions de revue jusqu'au GO de clôture ; --acceptance écrit les tests
argument-hint: "<incr> [<story id>] [--acceptance]"
---
Target: $ARGUMENTS

## Contract
- Regime: spec (discuss). A product point you cannot take from `framing.md` is a question for
  the decision owner, never a silent choice.
- Write the stories of a framed increment, apply the owner's decisions after a review up to
  the GO close, then, with `--acceptance`, the acceptance tests.
- Why: the stories and the suite are the only contract the implementations receive.
- Scope: the `product-analyst` session; skills `delivery-method:spec-writing` and, for
  `--acceptance`, `delivery-method:acceptance-by-role`.

## Preconditions
Fail closed: on the first failure, say why and stop.
1. `repo_role` is `spec` or `single`; this session runs the `product-analyst` agent; the
   current branch is `spec/<incr>`, else stop and print `git switch spec/<incr>`.
2. `refinement/<incr>/framing.md` has status `framed` (stories, corrections) or `closed`
   (`--acceptance`). Otherwise name the missing GO and stop: a command never goes past the
   current GO.
3. With `--acceptance`: every story of `scope` has status `ready`.

## Steps
Mode: `--acceptance` gives the tests; a review report on the current stories, answered by the
owner, gives the corrections; otherwise, the stories.

**Stories** (status `framed`):
1. Read `framing.md` (firm decisions, scope, exclusions, assumptions, story map),
   `spec/product/`, the existing stories and the copy files.
2. For each story of the map (or the one given), write `spec/stories/<id>-<slug>.md` with
   `status: draft` and the short title of the map as `title:` (3 to 8 plain words): business
   rules, main flow, extensions, criteria, UI contract, outcomes, out of scope, open questions.
3. Add each UI key to every `spec/ui/copy.<locale>.json`; a new domain term to the glossary.
4. Anything you had to settle becomes an open question of the story, or an assumption added
   to `framing.md`, both submitted to the owner.
5. Run `deliveryctl spec lint`; fix; exempt only with a reason.
6. Commit (`Campaign: <incr>`, `Agent: product-analyst`); recap the stories as
   `<id> : <title>`, the open questions numbered with a recommendation, the lint result; propose
   `/delivery-method:spec-review <incr>`.

**Corrections and close** (after a review report in `refinement/<incr>/reviews/`):
1. Quote the owner's answers (`to-decide` points, open questions, assumptions) with the date;
   add them to `## Firm decisions` and empty the answered open questions.
2. Correct the blocking and decided points only. Start from "the structure holds" and name
   what you leave untouched.
3. Re-verify each correction on the files, never on your summary, including the same error
   migrated to other stories.
4. A correction that reaches outside the framed scope or an external holder: stop and put it
   to the owner.
5. Run `deliveryctl spec lint`; commit; recap what changed, per finding.
6. On the owner's explicit GO close, once each story meets the ready criteria: stories of the
   scope `status: ready`, `framing.md` `status: closed`; `deliveryctl spec lint`; commit with the
   trailer `Go: close`; run `deliveryctl spec push` and give the pull request URL.

**Acceptance tests** (`--acceptance`, status `closed`):
1. For each story of the scope, write its tests in `spec/acceptance/`, from its criteria.
2. Run `deliveryctl spec lint` (a test per criterion, no orphan tag), then the suite against
   `spec/acceptance/fixtures/empty-app/`: every test red, on its own step.
3. A criterion that cannot be observed by role and label: stop; the story needs a correction
   and the owner's GO.
4. Commit (pushed with the next GO); propose `/delivery-method:spec-review <incr> --acceptance`.

## Outputs
- `spec/stories/*.md`, `spec/ui/copy.*.json`, `spec/product/glossary.md`, `framing.md`
  (assumptions, firm decisions, status), `spec/acceptance/` tests. Commits on `spec/<incr>`; the pull request is updated at each GO.

## Ends with
- Open questions or a GO awaited: `Outcome: question — <what the owner must decide>`.
- Otherwise: `Outcome: done — <what was reached>` (stories written, corrections applied,
  increment closed, or tests red against the empty app).
