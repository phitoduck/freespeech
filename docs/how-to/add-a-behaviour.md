# Add a behaviour

A change here starts as a sentence in a feature file and ends as a screenshot in
these docs. This is the loop.

## 1. Write the sentence first

Open the right file in `features/` and write the scenario before any code
exists. The wording carries a decision — **is this an example, or a claim about
everything?**

=== "An example (`@docs`)"

    Concrete nouns. Becomes documentation.

    ```gherkin
    @docs
    Scenario: A muted page shows no play button
      Given a PDF containing the text "One two three."
      When I mute the page
      Then the play button is hidden
    ```

=== "A property (`@property`)"

    The word **any**. Runs against generated input, hundreds of cases per run.

    ```gherkin
    @property
    Scenario: Muting never changes the words on the page
      Given any page of words
      When it is muted
      Then the words are unchanged, in order
    ```

Most behaviours deserve both: an example a person can picture, and a property
that covers the space around it.

## 2. Let a test fail

Bind the scenario in `tests/bdd/` and run it. It must fail, and it must fail for
the *right reason* — a missing function, not a typo in a step name. A test that
was never red proves nothing.

For a `@property` scenario, the shape is fixed (and
[ADR 0005](../explanation/adr/0005-gherkin-quantifiers-split-examples-from-properties.md)
explains why): the `Given` step returns a **strategy**, the `When` step returns
an **operation**, and the `Then` step runs the property *inside itself*.

```python
from hypothesis import given as for_all

@given("any page of words", target_fixture="subject")
def _():
    return word_lists()                   # a strategy, not a value

@then("the words are unchanged, in order")
def _(subject, operation):
    @for_all(subject)                     # every example runs inside ONE step
    def property_holds(words):
        assert operation(words) == words

    property_holds()
```

!!! danger "Do not put `@for_all` on the `@scenario` function"
    pytest-bdd builds a scenario out of fixtures, and Hypothesis re-runs the body
    many times per fixture setup. Your `Given` steps would run once while a
    hundred examples chewed on the same state.

## 3. Make it pass

Write the smallest thing that satisfies the test. If the test looks wrong while
you are implementing, say so and fix the *test* deliberately — never quietly
adjust it until it goes green. That distinction is the whole value of the
separation.

## 4. Ask what the test is worth

Before you are done, answer one question about every test you added:

> What plausible bug does this catch that no other test catches?

If there is no answer, delete it. If you are unsure, break the implementation on
purpose and check that the test notices. Doing that once found the most useful
thing in this codebase's history: a guard in `allocate()` that no property could
reach, because the strategy had been bounded to avoid the very regime the guard
defended.

## 5. Let the docs catch up on their own

If the scenario is tagged `@docs`, take a screenshot in its step definition and
reference it from a page. Then:

```bash
make test-e2e     # regenerates the images
make docs         # rebuilds the site
```

The Reference section regenerates from the feature files, so the behaviour you
just wrote is already listed:

```bash
uv run python scripts/gen_behaviours.py
```

## The loop closes

When a property fails, Hypothesis hands you a minimal counterexample. Transcribe
it back into the feature file as a `@docs` scenario with human-meaningful values,
and it becomes a permanent regression test *and* a piece of documentation.

Properties discover scenarios; scenarios document them.
