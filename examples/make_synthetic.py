# -*- coding: utf-8 -*-
"""make_synthetic.py — regenerate the bundled synthetic demo corpus.

Three files, one lesson: a text layer can LOOK complete and still be
unsearchable. All text is an original synthetic passage written for this demo
(no copyrighted corpus material is ever bundled). Deterministic: seed is fixed,
so the shipped files are exactly reproducible with `python make_synthetic.py`.

  corpus/healthy.txt            the passage, clean, with page markers
  corpus/wordsplit-damaged.txt  same passage, ~2% of long words split apart
                                (`polit ical`, `p eople`) -> fires health gate 5
  corpus/glued-damaged.txt      same passage, short spans glued together
                                (`thelibraryisnot`) -> fires health gate 6

NOTE: the demo corpus is for DIAGNOSIS only. The repair tools learn their
dictionary from your own healthy files; on a three-file toy corpus that
dictionary is meaningless. Diagnose here, repair on a real corpus.
"""
import os
import random
import re

# Original passage (~450 words), written for this demo. Long content words
# recur >= 4 times so that, cycled, they clear the lexicon thresholds the
# health gates use; common-phrase density is natural English.
PASSAGE = """
The library is not a warehouse. A collection of texts becomes a library only
when the people who keep it can answer for what is inside it, and there is no
answer without evidence. Every claim about the collection rests on the text
layer, and the text layer is not the book: it is a copy of a copy, produced by
software that guesses at spacing, hyphens, and page boundaries. When the guess
is wrong, the political consequences are quiet. Nothing crashes. The search
simply returns nothing, and the person searching concludes that the knowledge
is not there.

This is the failure that matters in the library: not the missing file but the
unfindable one. A reader who asks for political theory and receives silence
will not suspect the text layer. There is no error message for a word that was
split in half by a kerning table, and there is no warning for a sentence that
was glued into a single token by a broken extractor. The evidence of damage
lives in the statistics of the collection itself, and only there.

Consider what the people in charge of a collection can measure. The density of
common phrases tells them whether the words of the text arrived intact. The
rate of adjacent fragments that join into a frequent word tells them whether
the political vocabulary of the collection was split apart. The rate of
overlong tokens tells them whether whole phrases were glued together. None of
this requires reading every page; all of it requires believing the numbers
only after the numbers have been checked against the page.

The knowledge in a library is not the sum of its files. It is the degree to
which the collection can be interrogated and answer honestly. A damaged text
layer answers dishonestly: it says nothing is there when the evidence is
sitting in the shelves. The political cost of that dishonesty falls on
whoever trusted the search, which is to say on the people least equipped to
suspect it. The remedy is not better trust but better measurement, and the
measurement must be designed so that it only fires when the damage is real.

So the library needs a doctor, not a decorator. The work of the doctor is to
probe what is inside the collection, to measure the text layer against the
evidence of the page, and to repair only what the statistics of the knowledge
itself can justify. Everything else is left alone, because in a library the
first duty of the people to the texts is the same as the first duty of the
doctor to the patient: do no harm to what is healthy.
""".strip() + "\n"

CYCLES = 10          # ~4,500 words / ~28 KB per file - above the health check floors
WORDS_PER_PAGE = 2   # page marker every N cycles -> plausible page density

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "corpus")


def build_clean():
    parts = []
    page = 1
    for c in range(CYCLES):
        if c % WORDS_PER_PAGE == 0:
            parts.append(f"\n===== page {page} =====\n")
            page += 1
        parts.append(PASSAGE)
    return "".join(parts)


def damage_wordsplit(text, rng):
    """Split ~7% of long words: mid-word (`polit ical`) or single-letter
    prefix (`p eople`) - the two shapes of the real disease. The rate is
    chosen so the file lands clearly above health gate 5's 5-permille floor
    (real damaged files in the source corpus ran 8-116 permille)."""
    toks = list(re.finditer(r"[A-Za-z]{6,}", text))
    out, pos, n = [], 0, 0
    for m in toks:
        w = m.group(0)
        if rng.random() < 0.07:
            cut = 1 if rng.random() < 0.3 else rng.randint(3, min(5, len(w) - 2))
            out.append(text[pos:m.start()])
            out.append(w[:cut] + " " + w[cut:])
            pos = m.end()
            n += 1
    out.append(text[pos:])
    return "".join(out), n


def damage_glue(text, rng):
    """Glue short spans into single tokens, enough to land clearly above
    health gate 6's 3-permille floor (real damaged files ran 3-30 permille)."""
    words = list(re.finditer(r"(?:[A-Za-z]+ ){2,3}[A-Za-z]+", text))
    out, pos, n = [], 0, 0
    for m in words:
        if rng.random() < 0.05 and len(m.group(0).replace(" ", "")) >= 18:
            out.append(text[pos:m.start()])
            out.append(m.group(0).replace(" ", ""))
            pos = m.end()
            n += 1
    out.append(text[pos:])
    return "".join(out), n


def main():
    os.makedirs(OUT, exist_ok=True)
    clean = build_clean()
    open(os.path.join(OUT, "healthy.txt"), "w", encoding="utf-8", newline="").write(clean)

    rng = random.Random(42)
    ws, n1 = damage_wordsplit(clean, rng)
    open(os.path.join(OUT, "wordsplit-damaged.txt"), "w", encoding="utf-8", newline="").write(ws)

    rng = random.Random(43)
    gl, n2 = damage_glue(clean, rng)
    open(os.path.join(OUT, "glued-damaged.txt"), "w", encoding="utf-8", newline="").write(gl)

    print(f"healthy.txt            {len(clean):,} chars")
    print(f"wordsplit-damaged.txt  {len(ws):,} chars | {n1} words split")
    print(f"glued-damaged.txt      {len(gl):,} chars | {n2} spans glued")


if __name__ == "__main__":
    main()
