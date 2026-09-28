---
name: spec-writing
description: How to write technology-neutral spec stories - behaviour in the present tense, numbered business rules, flows, Given/When/Then criteria, UI contract, outcomes - and when a story is ready. Used by the product-analyst and by spec reviewers.
---
## When to use
When a story, the brief, the glossary or the UI copy is written or reviewed in `spec/`.
Why: several implementations, on any stack, are built and judged from the same text.
Scope: `spec/product/`, `spec/stories/`, `spec/ui/`; the tests follow the skill
`delivery-method:acceptance-by-role`.

## Doctrine
**Neutrality test.** Could two teams on unrelated stacks build this from the text alone, and
would one acceptance suite judge both? A sentence that fits one stack only is a solution.

| Instead of (solution) | Write (behaviour) |
|---|---|
| row-level security on lists | a person never sees a list nobody shared with them |
| push over a socket | a change made in one browser shows in the other within 2 seconds, without reloading |
| a job every morning at 9 | a reminder shows when the due time of the task is reached |
| error 404 on an unknown list | the person sees `list.not_found` and no task of that list |

**Story file** `spec/stories/<id>-<slug>.md`: frontmatter `id`, `title` (a short title, 3 to 8
plain words on what the user gets), `status` (`draft` | `ready`); sections in this order:
- `## Business rules`: `BR-1`, `BR-2`… one observable rule each.
- `## Main flow`: numbered steps; every visible text is a key in backticks (`share.open`).
- `## Extensions`: `2a.` one alternative or failure each, with what the person sees.
- `## Acceptance criteria`: `AC<n> @main|@ext-<xy> — Given … When … Then …`; keywords in
  English, the rest in the project language; at least one criterion per extension.
- `## UI contract`: key, accessible role, where it appears.
- `## Outcomes`: non-functional results with a number or an absolute ("within 2 seconds",
  "never"), each proven by a criterion.
- `## Out of scope`, `## Open questions`.

**Present tense, no history.** A story describes what the product does, not who decided it or
when. The link between firm decisions and stories lives in the `## Story map` of `framing.md`.

**No detail that varies.** No current counts, sample values or today's list of items: state
the rule that produces them.

**Keys and copy.** Every key of the UI contract exists in each `spec/ui/copy.<locale>.json` of
the locales of `spec/spec.toml`. A domain word that looks technical goes to the glossary.

**One story, one user goal.** Dependencies are functional: B needs A when a person must do A
before B makes sense. A story is named `<id> : <title>` wherever it is cited, never by its id.

**Ready.** A story is `ready` when a team on any stack can build it without a product
question: `## Open questions` empty, its assumptions accepted by the owner, `deliveryctl spec
lint` clean or exempted, no open blocking finding. Only the GO close sets `ready`.

## Defaults and levers
- `deliveryctl spec lint` is tolerant in `draft`, strict in `ready`. A finding is lifted by a
  line `lint-exempt: <rule> — <reason>` in the story, except the schema of a `ready` story.
- The neutrality lexicon extends through `[neutrality]` in `spec/spec.toml`.
- A story targets 150 lines; beyond, it covers two goals: split it.
- Before the first delivery, keys and criteria change freely. `deliveryctl spec release`
  computes the version: a removed or changed criterion is major, an added one minor.

## Anti-patterns
- Files, classes, endpoints, tables, protocols, frameworks or status codes in a story.
- "Fast", "secure", "intuitive" without an observable threshold.
- A criterion that states an internal state instead of what a person sees.
- One story per screen instead of one per user goal.
- A product point settled by the writer: it is an open question and the story stays `draft`.

## Checks
- `deliveryctl spec lint` passes for the stories written.
- Each extension has a criterion; each outcome is proven by a criterion.
- Each key used in a flow is in the UI contract and in every copy file.
- Nothing in the story would change if the implementation language changed.
