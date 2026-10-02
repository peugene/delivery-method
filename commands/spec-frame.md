---
description: Ouvre ou reprend le cadrage d'un incrément avec l'analyste produit, jusqu'au GO de cadrage
argument-hint: "<incr> [--discover] [--market <domaine>]"
---
Target: $ARGUMENTS

## Contract
- Regime: spec (discuss). Nothing is decided in silence: you recommend, the decision owner
  decides.
- Frame one increment with the owner, up to the GO frame, in `refinement/<incr>/framing.md`.
- Why: stories written before the scope and the firm decisions are settled get rewritten.
- Scope: the `product-analyst` session; skill `delivery-method:framing-discussion`. No story,
  no test, no technique is written here.

## Preconditions
Fail closed: on the first failure, say why and stop.
1. `delivery.toml` has `repo_role` `spec` or `single`. Otherwise: "the spec phase runs in a
   spec or single repository".
2. This session runs the `product-analyst` agent. Otherwise print
   `claude --agent delivery-method:product-analyst` and stop.
3. `<incr>` is a short kebab-case name (`01-core`). Otherwise ask for one.
4. If `framing.md` has status `framed` or `closed`: say so and stop. Framing reopens only on the
   owner's explicit message; then set `status: discussing` and say what reopens.

## Steps
1. Absent `framing.md`: create it from `.delivery/templates/spec/framing.md` (missing: the
   sections of step 5, then `## Next`) with `id: <incr>`, `status: discussing`, `scope: []`.
   Present: read its `## Next` first, then the files it names.
2. Read the existing before you speak: `spec/product/brief.md` first (every framing starts from
   it), then the rest of `spec/product/`, `spec/stories/`, earlier
   `refinement/*/framing.md` (their deferred points and exclusions), and what the owner brought
   (notes, brief, `spec-question.md`).
3. With `--discover`, settle first the problem, the actors, the scope and the observable
   success. With `--market <domain>`, look at comparable products for feature ideas only.
   The brief is empty when it has no content of its own: only headings, `<!-- -->` comments
   and `<…>` placeholders. When the owner brings vision decisions (closing word vision, in this
   session or pasted), or with `--discover` while the brief is empty, write or update
   `spec/product/brief.md` from `.delivery/templates/spec/brief.md`, in the project language,
   product words only; the increment covers one block of `## Blocks`, named in its
   `## Purpose`. A firm decision that contradicts the brief updates it in the same framing; the
   recap and the GO frame name each change of the brief.
4. Open: your opinion, the structuring point, the option you discard and why; then numbered
   questions, each with lettered options, their consequence and your recommendation.
5. At the owner's rhythm, after each answer, write `framing.md`:
   - `## Purpose`: the problem and the observable success, in two or three sentences;
   - `## Firm decisions`: `D<n> : <short title> — <decision> — "<owner's words>" (<date>)`,
     one line each;
   - `## Scope`, `## Exclusions`: what the increment delivers, what it does not;
   - `## To investigate`: technical questions for the technical lead, as the observable
     result they condition;
   - `## Assumptions`: what you assumed without asking, to submit at the GO;
   - `## Deferred`: each point with what would bring it back;
   - `## Story map`: each story as `<id> : <short title>` (3 to 8 plain words, what the user
     gets), its user goal, its functional dependencies and the firm decisions it covers, each
     named `<id> : <short title>` too.
   Then recap: decided, assumed, deferred, open.
6. When no observable behaviour of the scope is left open, submit the GO frame: purpose, firm
   decisions, scope, exclusions, assumptions to accept, story map.
7. On the owner's explicit GO frame: accepted assumptions become firm decisions, the others
   return as questions; set `status: framed` and `scope: [<story ids>]`; commit `framing.md`
   and, when it changed, `spec/product/brief.md`, with trailers `Campaign: <incr>` and
   `Agent: product-analyst`. When the project works by merge requests,
   the approval of the one carrying this commit is the GO; pushing it is the owner's gesture.
   In a cloud session the session's own `claude/` branch is pushed for the pull request.

## Outputs
- `refinement/<incr>/framing.md`, 80 lines targeted, in the project language; section names
  and keys in English.
- `spec/product/brief.md` when it is written or updated, 40 lines targeted, same languages.
- Commits of these two files only, never pushed.

## Ends with
- Waiting for the owner: the recap and the numbered questions, then
  `Outcome: question — <n> questions for the decision owner`.
- After the GO frame: `Outcome: done — <incr> framed; next: /delivery-method:spec-write <incr>`.
