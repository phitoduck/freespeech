# 5. Gherkin carries the quantifier; properties run inside steps

- Status: accepted
- Date: 2026-08-15

## Context

We want behaviour-driven specs *and* property-based tests. The obvious way to
combine them — putting Hypothesis's `@given` on a pytest-bdd `@scenario` — is
broken: pytest-bdd builds a scenario out of pytest fixtures, and Hypothesis
re-runs the test body many times per fixture setup. Function-scoped fixtures run
once for the whole test, so `Given` steps would set up state once and a hundred
generated examples would chew on the same mutated object.

The two also collide on the name `given`, which is trivial but confusing.

## Decision

**A property test is a Scenario Outline whose Examples table is generated at
runtime and minimised on failure.** That framing settles both questions.

1. The quantifier lives in the Gherkin, in the word **"any"**:
   - `Given a PDF containing "One two three."` → an example, tagged `@docs`
   - `Given any page of words and any audio duration` → a property, tagged `@property`

2. The property runs **inside a step**, never around the scenario:
   - a `Given` step returns a *strategy* via `target_fixture`
   - a `When` step returns the *operation* via `target_fixture`
   - a `Then` step defines an inner `@for_all(strategy)` function and calls it

   All examples then execute within one step invocation, so pytest's fixture
   lifecycle is never violated.

3. Hypothesis's decorator is imported as `for_all`, which reads as what it is and
   ends the name collision.

## Consequences

- Non-programmers can read the universal claims. *"Any page's timeline covers its
  audio exactly once"* is a sentence a stakeholder can agree or object to, and it
  is also the test.
- The property body must build fresh state per example and never mutate anything
  it closes over from a fixture. This is a real discipline the pattern demands;
  it is why the domain objects are frozen dataclasses.
- Example scenarios and property scenarios live in the same feature file and share
  domain helpers, but not step text — the phrasing differs because the claims
  differ.
- Counterexamples flow back the other way: when a property fails, its shrunk
  sequence is transcribed into a new `@docs` scenario with human-meaningful
  values. Properties discover scenarios; scenarios document them.
- The same split holds in TypeScript, where Hegel plays Hypothesis's part —
  deliberately, since Hegel is built on Hypothesis and shrinks identically.
