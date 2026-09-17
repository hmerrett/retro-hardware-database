# Work from the manual first

`MANUAL.md` is what the register promises the person using it. It is the
specification and not a write-up of what was built, so it is where a change
starts: something that cannot be described there is something nobody can be told
about.

The order is manual, then tests, then code.

## The order

1. **Write the manual entry first.** Say what the software will do, in the
   section where somebody would look for it, in the present tense and as though
   it already worked. Write it for a reader who does not know the codebase — if
   the entry needs a paragraph of apology, or names a module, the design is
   saying something while it is still cheap to hear.
2. **Derive the tests from that entry.** Every promise it makes is a test, named
   for the promise so it reads as a line of spec (testing-standards). A promise
   with no test is a claim the suite cannot keep.
3. **Then write the code**, until those tests pass and the suite stays green.

The chain runs one way: the manual promises, the tests hold the promise, and
`docs/behaviour.md` is generated from the tests as the evidence that it is kept.
`behaviour.md` is therefore never where a promise starts, and is never edited by
hand.

## When the manual and the code disagree

That is a fault in one of them and not a difference to be left standing. Decide
which is wrong, in the open: either the code has drifted and is brought back, or
the manual describes something better than what was built and the entry is
rewritten deliberately, in its own commit, saying so. Quietly editing the manual
to match what the code happens to do is how a specification becomes a changelog.

## What this does not cover

Work with no user-visible face — a router extraction, a migration, a lockfile —
has no manual entry, and inventing one to satisfy the rule helps nobody. The
specification for that work is `docs/architecture.md` and the ADRs, and the order
holds in the same shape: write down the invariant or the decision first, put a
test on it where a test can reach it, then move the code.

## Why

The suite is generated into a document that reads as a specification, which makes
it tempting to treat the tests as the specification themselves. They are not: a
test says what the code does, and a code-shaped promise is one only its author
can check. Starting at the manual keeps the description in the language of
somebody who owns a collection rather than somebody who owns the repository, and
it catches the features that are hard to explain before they are expensive to
change.
