---
name: acceptance-by-role
description: How to write the shared Playwright acceptance suite from the spec - tags per criterion, locators by role and label key, data only through the UI and the harness, a new client state per test, red against the empty app. Used by the product-analyst after the GO close and by spec reviewers.
---
## When to use
When tests of `spec/acceptance/` are written or reviewed, after the GO close of an increment.
Why: every implementation runs this suite unchanged; a test that stays green on a wrong
product hides the hole it claims to cover.
Scope: the spec repository only. An implementation never edits the suite.

## Doctrine
**Written from the spec.** Each test follows the Given/When/Then of the criteria it covers.
Title: a plain sentence, then `@<id>` and one tag `@<id>-ac<n>` per criterion covered:
`share a list with a friend @s004 @s004-ac1`. A test may cover several criteria; each
criterion has at least one test; no tag points to a missing criterion.

**Locators by role and label.** `getByRole`, `getByLabel`, `getByText`, with accessible names
from `copy('<key>')`:

```ts
await page.getByRole('button', { name: copy('share.open') }).click();
await expect(page.getByRole('alert')).toHaveText(copy('share.unknown_person'));
```

No CSS selector, test id, XPath, sleep or hand-built URL. A criterion that cannot be observed
by role and label means the UI contract of the story is incomplete: fix the story, not the
test.

**Data through the UI and the harness only.** The harness of
`spec/acceptance/harness-contract.md` offers `reset`, `users` (a named person), `login-as`
(a session for that person) and, when the story depends on time, `tick`. Everything else is
created by the test through the interface, as a user would.

**A new client state per test.** Start with `reset`, then a fresh browser context per
person. Nothing carries over from another test or from the order of tests. A precondition
the test relies on is asserted first, so the test fails loudly when it is missing.

**Every Then asserts.** Each Then has at least one `expect` on what a person sees. A negative
assertion ("no error shown") comes with a positive observable, otherwise an empty page passes.

**Time and several people.** Time moves only through `tick`. Two people are two browser
contexts; a real-time outcome is asserted in the other context with the story's bound as the
`expect` timeout.

**Red against the empty app.** `spec/acceptance/fixtures/empty-app/` serves the harness and
nothing else. The whole suite fails there, each test on a locator or an assertion of its
story, never on the harness. A test that passes there proves nothing.

## Defaults and levers
- One file per story, named after it; helpers only in the suite's support code.
- The default `expect` timeout of the suite applies, except where a story sets a bound.
- Tests of a story run with `{grep} = @<id>`; the full suite runs at night, never per story.

## Anti-patterns
- Asserting URLs, CSS classes, DOM structure or counts with no meaning to a person.
- Seeding data through a route, a script or a database.
- A test that depends on another test's data or on execution order.
- A `catch` or a conditional that lets a test pass when the action did nothing.
- Editing a story's behaviour to fit a test.

## Checks
- `deliveryctl spec lint` passes: a test per criterion, no orphan tag.
- The suite run against the empty app is 100 % red, each failure on the story's own step.
- Every `copy('<key>')` key exists in each `spec/ui/copy.<locale>.json`.
- Every Then of every criterion covered has its `expect`.
