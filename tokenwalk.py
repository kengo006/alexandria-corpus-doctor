# -*- coding: utf-8 -*-
"""tokenwalk.py — the single implementation of adjacent-token joining.

WHY THIS FILE EXISTS (and is not a comment in three other files)

"Pairwise rewriting walks tokens; it never uses ``re.sub``" was bought with a
silent, systematic bug. The lesson was then written as a comment into three
separate repair scripts -- and the fourth, the ladder runner that actually
executes them in sequence, never got it. It was still calling ``RE_SPACE.sub()``
a week later, which is the path six re-extracted files went through.

Three copies of a comment do not stop the fourth script, because **a comment is
not executed**. So the rule became a shared function instead: new pairwise
rewrites call this module, and the rule can no longer be forgotten.

THE BUG ITSELF (``re.sub`` consumes matches left to right)

    "the polit ical theory"

    A pattern matching (word, space, word) fires first on ("the", "polit"),
    decides not to join -- **but "polit" has already been consumed**. The pair
    that mattered, ("polit", "ical"), is never evaluated. Result: zero joins.

The symptom is diagnostic, and it is why this went unnoticed: single-letter
prefixes (``p eople``) still repair, because a single letter cannot serve as the
first element of a match and so is never eaten -- while mid-word splits
(``polit ical``, ``insti tution``) silently repair *nothing at all*.

And **re-running does not help**. The text is unchanged, so the next pass makes
the same mistake in the same place; a fixed-point loop terminates immediately on
``s == prev``. Silent, systematic, and non-convergent on retry: exactly the
class of defect that a regression test has to pin down, because no amount of
looking at the output will suggest that anything ran.

KNOWN BOUNDARY OF A SINGLE PASS (pinned by tests; not a bug to fix)

A three-part chain ``techno crat ic``: one pass joins (techno, crat), then
advances past the merged token, so (technocrat, ic) is not evaluated in that
pass, yielding ``technocrat ic``. The fix is to run to a fixed point --
``join_pairs_fixpoint()`` -- not to loosen the single pass. This is the ladder's
first iron rule (**run every repairer to its fixed point**) in miniature.

USAGE

    from tokenwalk import join_pairs_fixpoint
    new_text = join_pairs_fixpoint(text, accept)   # accept(a, b) -> bool
"""
import re

TOKEN = re.compile(r"[A-Za-z]+")


def join_pairs(text, accept, sep=" ", token=TOKEN):
    """Positionally evaluate every adjacent token pair and join the accepted ones.

    ``accept(a, b) -> bool`` decides whether ``a`` and ``b`` are one word that
    was split. A pair is considered only when the two tokens are separated by
    *exactly* ``sep`` (a single space by default); everything else is preserved
    byte for byte.

    The load-bearing line is ``i += 1`` in the ``else`` branch: when a pair is
    rejected, the walk advances by **one** token, so the rejected second token
    becomes the first element of the next pair. That is the property ``re.sub``
    cannot have, and the entire reason this module exists.

    Returns (new_text, joins) -- the count is for callers that need to report a
    denominator rather than a bare "done".
    """
    spans = [(m.start(), m.end(), m.group()) for m in token.finditer(text)]
    out, cursor, i, joins = [], 0, 0, 0
    while i < len(spans):
        s0, e0, w0 = spans[i]
        if i + 1 < len(spans):
            s1, e1, w1 = spans[i + 1]
            if text[e0:s1] == sep and accept(w0, w1):
                out.append(text[cursor:s0])
                out.append(w0 + w1)
                cursor = e1
                i += 2                      # both tokens consumed by the join
                joins += 1
                continue
        i += 1                              # <-- rejected: advance by ONE
    out.append(text[cursor:])
    return "".join(out), joins


def join_pairs_fixpoint(text, accept, sep=" ", token=TOKEN, max_passes=12):
    """Run :func:`join_pairs` until the text stops changing.

    Required for chains of three or more fragments (see the module docstring).
    ``max_passes`` is a runaway guard, not an expected limit; if it is ever hit,
    ``accept`` is oscillating and the caller has a bug worth finding.
    """
    total = 0
    for _ in range(max_passes):
        new, joins = join_pairs(text, accept, sep=sep, token=token)
        total += joins
        if new == text:
            return text, total
        text = new
    return text, total


# ---------------------------------------------------------------------------
# Counter-example. Kept executable on purpose.
# ---------------------------------------------------------------------------
def join_pairs_resub_BROKEN(text, accept, sep=" "):
    """DO NOT USE. The ``re.sub`` version, preserved so the failure is runnable.

    A rule with no executable counter-example teaches "don't do X" without
    showing what X does. Diff this against :func:`join_pairs` on
    ``"the polit ical theory"``: this returns the input unchanged, because the
    scan consumed ``polit`` while rejecting ``("the", "polit")``.
    """
    pattern = re.compile(r"([A-Za-z]+)" + re.escape(sep) + r"([A-Za-z]+)")

    def rep(m):
        a, b = m.group(1), m.group(2)
        return a + b if accept(a, b) else m.group(0)

    return pattern.sub(rep, text)


if __name__ == "__main__":
    demo = "the polit ical theory of insti tution al design"
    # "institution" must be acceptable for the chain to reach "institutional":
    # that is the point of the fixed point, not an oversight.
    vocab = {"political", "institution", "institutional"}
    accept = lambda a, b: (a + b).lower() in vocab

    one, n1 = join_pairs(demo, accept)
    fixed, n2 = join_pairs_fixpoint(demo, accept)
    broken = join_pairs_resub_BROKEN(demo, accept)

    print("input      :", demo)
    print("one pass   :", one, f"({n1} joins)  <- 'institution al' still split")
    print("fixed point:", fixed, f"({n2} joins)")
    print("re.sub     :", broken, "(0 joins - this is the bug)")
    assert "political" in fixed and "institutional" in fixed
    assert broken == demo, "the counter-example must reproduce the failure"
    print("\nself-check OK: the walk converges; re.sub returns the input unchanged.")
