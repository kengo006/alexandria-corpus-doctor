# -*- coding: utf-8 -*-
"""ligature_and_encoding.py -- ligature expansion, line-end dehyphenation, and
font-encoding garble detection for an extracted text layer.

WHY THIS IS A SEPARATE FILE FROM THE REPAIR LADDER

Everything else in this repository was derived from measuring one corpus. This
file is different: it is **adapted from four upstream open-source parsers**,
which had already solved these three problems well. Porting was cheaper and
safer than re-deriving them, and keeping the provenance visible is the point --
if you want the canonical version of any of these, go upstream.

ATTRIBUTION (verified 2026-07-31 against each project's LICENSE file)

  * Ligature map and the space-absorbing pattern
      docling -- docling/models/stages/page_assemble/page_assemble_model.py
      (_LIGATURE_MAP, _LIGATURE_RE).  MIT License.
      https://github.com/docling-project/docling
    The same space-absorbing behaviour is implemented in Kreuzberg
      (expand_ligatures_with_sp).  MIT License.
      https://github.com/Goldziher/kreuzberg

  * Line-end dehyphenation with the alphanumeric guard
      docling -- PageAssembleModel.sanitize_text (same file, MIT), whose test
      is "the token before the hyphen and the token after the break are both
      alphanumeric".  The layered treatment (in-span, line-to-line,
      cross-page continuation) follows marker.  Apache License 2.0.
      https://github.com/datalab-to/marker

  * Font-encoding garble detection
      RAGFlow -- deepdoc/parser/pdf_parser.py (_is_garbled_char /
      _is_garbled_text).  Apache License 2.0.
      https://github.com/infiniflow/ragflow

Apache-2.0 requires that changes be stated: **what we changed is recorded in
the "DEVIATIONS" note under each function**, and the thresholds were
re-measured on a humanities corpus rather than carried over (see THRESHOLDS).

THRESHOLDS ARE NOT PORTABLE

Every threshold in an upstream parser was tuned against that project's own
corpus -- largely business documents, reports, and technical PDFs. Scholarly
humanities texts differ in ways that matter here: dense footnotes, several
languages per volume, classical transliteration, and older typesetting
conventions. **Re-measure before you trust any number below on your own
material**; the ``--calibrate`` mode exists for exactly that.

Measured here (Western-language humanities corpus, 552 text-layer files, after
the repair ladder had been run to its fixed point):

    files with any garble    3  (0.5%)
    files with CID artefacts 0
    worst file               2.458 permille

**Upstream's flag is 0.5 -- that is 500 permille.** The worst file in this
corpus sits two hundred times below it, so a boolean at the upstream threshold
would report all three as clean. This is the whole reason ``garble_rate``
returns a rate and a denominator instead of a boolean: at this scale the
question is not "is the page unreadable" but "did a class of characters
silently vanish".
"""
import re
import sys
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Ligature expansion  (from docling, MIT; same behaviour as Kreuzberg, MIT)
# ---------------------------------------------------------------------------
LIGATURE_MAP = {
    "ﬀ": "ff",   # LATIN SMALL LIGATURE FF
    "ﬁ": "fi",   # LATIN SMALL LIGATURE FI
    "ﬂ": "fl",   # LATIN SMALL LIGATURE FL
    "ﬃ": "ffi",  # LATIN SMALL LIGATURE FFI
    "ﬄ": "ffl",  # LATIN SMALL LIGATURE FFL
    "ﬅ": "st",   # LATIN SMALL LIGATURE LONG S T
    "ﬆ": "st",   # LATIN SMALL LIGATURE ST
    "Ĳ": "IJ",   # LATIN CAPITAL LIGATURE IJ
    "ĳ": "ij",   # LATIN SMALL LIGATURE IJ
    "": "",     # private-use glyph emitted by some fonts; discard
}

# The trailing group absorbs a spurious space that PDF extractors insert
# between a ligature glyph and the rest of the word: "fi eld" -> "field".
_LIGATURE_RE = re.compile(r"([ﬀ-ﬆ]|Ĳ|ĳ|)( (?=\w))?")


def expand_ligatures(text):
    """Replace ligature glyphs with their ASCII equivalents, absorbing the
    spurious space some extractors leave behind.

    DEVIATIONS from upstream: none in behaviour. The map and pattern are
    reproduced as-is because they are already exhaustive for the Alphabetic
    Presentation Forms block, and narrowing them would only create a gap.
    """
    return _LIGATURE_RE.sub(lambda m: LIGATURE_MAP[m.group(1)], text)


# ---------------------------------------------------------------------------
# 2. Line-end dehyphenation  (guard from docling MIT; layering after marker Apache-2.0)
# ---------------------------------------------------------------------------
_PAGE_BREAK = re.compile(r"\n?\f\n?")


def dehyphenate_lines(text, join_across_pages=True):
    """Join words broken by a hyphen at end of line.

    The guard is upstream's and is the load-bearing part: join **only** when
    the token before the hyphen and the token after the break are both
    alphanumeric. That is what rejects enumerations and lines ending in a
    double dash.

    ⚠ It is **not** sufficient on its own, and finding that out is the reason
    this function has a third condition. Upstream's guard inspects *word
    tokens*, not the hyphen's attachment, so a line ending ``... em -`` joins
    to the next line's first word: both neighbouring tokens are alphanumeric,
    and the result is a word that was never in the source. This is common in
    scholarly typesetting, where a spaced hyphen ends a line inside a
    parenthetical.

    DEVIATIONS from upstream:
      * **The hyphen must be attached to the preceding word** (no whitespace
        before it). Ours; added after the case above showed up in the first
        self-test of this port.
      * ``join_across_pages`` is ours. Upstream treats a page boundary as a
        continuation candidate; in a page-marked scholarly text layer, the
        material immediately after a page break is very often a running head
        or a footnote block, so joining across it produces a word that never
        existed. Default stays True to match upstream, but set it False for
        corpora whose page boundaries carry apparatus.
      * We never *remove* a line break without also having removed a hyphen.
        A repairer that drops the hyphen but keeps the newline manufactures a
        split word that no later detector can distinguish from real damage.
    """
    out = []
    for block in _PAGE_BREAK.split(text) if not join_across_pages else [text]:
        lines = block.split("\n")
        for i in range(len(lines) - 1):
            prev, nxt = lines[i], lines[i + 1]
            if not prev.endswith("-"):
                continue
            # ours: the hyphen must be attached to the word, not floating
            if len(prev) < 2 or prev[-2].isspace():
                continue
            pw = re.findall(r"\b\w+\b", prev)
            nw = re.findall(r"\b\w+\b", nxt)
            if pw and nw and pw[-1].isalnum() and nw[0].isalnum():
                lines[i] = prev[:-1]
                lines[i + 1] = "\x00JOIN\x00" + nxt
        joined = "\n".join(lines).replace("\n\x00JOIN\x00", "").replace("\x00JOIN\x00", "")
        out.append(joined)
    return "\f".join(out) if not join_across_pages else out[0]


# ---------------------------------------------------------------------------
# 3. Font-encoding garble detection  (from RAGFlow, Apache-2.0)
# ---------------------------------------------------------------------------
_CID_PATTERN = re.compile(r"\(cid:\d+\)")


def is_garbled_char(ch):
    """True when a character indicates the extractor could not map a glyph
    to a real codepoint: private-use areas, the replacement character,
    C0/C1 controls, and unassigned or surrogate categories.

    DEVIATIONS from upstream: none. Reproduced because the range list is the
    whole value of the function and trimming it would create blind spots.
    """
    if not ch:
        return False
    cp = ord(ch)
    if 0xE000 <= cp <= 0xF8FF:          # Private Use Area
        return True
    if 0xF0000 <= cp <= 0xFFFFF:        # Supplementary PUA-A
        return True
    if 0x100000 <= cp <= 0x10FFFF:      # Supplementary PUA-B
        return True
    if cp == 0xFFFD:                    # REPLACEMENT CHARACTER
        return True
    if cp < 0x20 and ch not in ("\t", "\n", "\r", "\f"):   # C0 controls
        return True
    if 0x80 <= cp <= 0x9F:              # C1 controls
        return True
    return unicodedata.category(ch) in ("Cn", "Cs")


def garble_rate(text):
    """Return (rate, garbled, total_non_space, cid_hit).

    DEVIATIONS from upstream: upstream returns a boolean against a 0.5
    threshold suited to deciding "is this page unusable". We return the **rate
    and its denominator** instead, because in a scholarly text layer the
    interesting cases sit three orders of magnitude below that: a book whose
    accented characters were all mapped into the control range is perfectly
    readable in English and still has every author's name unsearchable. A
    boolean at 0.5 reports such a file as clean.
    """
    if not text or not text.strip():
        return 0.0, 0, 0, False
    cid = bool(_CID_PATTERN.search(text))
    garbled = total = 0
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        if is_garbled_char(ch):
            garbled += 1
    return (garbled / total if total else 0.0), garbled, total, cid


# Measured on a Western-language humanities corpus; see --calibrate.
# Deliberately far below upstream's 0.5: at this scale the failure is not
# "the page is unreadable" but "a class of characters silently vanished".
GARBLE_FLAG_PERMILLE = 0.1


def scan_corpus(root, flag_permille=GARBLE_FLAG_PERMILLE):
    """Report files whose garble rate exceeds the flag, plus any CID hits."""
    rows = []
    for p in sorted(Path(root).rglob("*.txt")):
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rate, g, tot, cid = garble_rate(t)
        if cid or rate * 1000 >= flag_permille:
            rows.append((p, rate * 1000, g, tot, cid))
    return rows


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[0])
        print("\nusage: python ligature_and_encoding.py <corpus-dir> [--calibrate]")
        sys.exit(0)
    root = sys.argv[1]
    calibrate = "--calibrate" in sys.argv
    rows = scan_corpus(root, flag_permille=0.0 if calibrate else GARBLE_FLAG_PERMILLE)
    if calibrate:
        total = len(rows)                      # flag 0.0 -> every readable file
        nz = sorted(r[1] for r in rows if r[1] > 0)
        cid = sum(1 for r in rows if r[4])
        print(f"files scanned            : {total}")
        print(f"files with any garble    : {len(nz)}  ({len(nz) / total * 100:.1f}%)" if total else "")
        print(f"files with CID artefacts : {cid}")
        if nz:
            m = nz[len(nz) // 2]
            p90 = nz[min(int(len(nz) * 0.9), len(nz) - 1)]
            print(f"  over the non-zero files: median {m:.3f} permille | p90 {p90:.3f} | max {nz[-1]:.3f}")
        print("  -> set GARBLE_FLAG_PERMILLE from YOUR distribution. A median of zero")
        print("     means the flag should sit just above zero, not at upstream's 0.5.")
    else:
        print(f"flagged {len(rows)} file(s) at >= {GARBLE_FLAG_PERMILLE} permille")
        for p, permille, g, tot, cid in rows[:40]:
            tag = " CID" if cid else ""
            print(f"  {permille:8.3f}pm  {g:6d}/{tot:<9d}{tag}  {p.name}")
