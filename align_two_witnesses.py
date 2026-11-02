# -*- coding: utf-8 -*-
"""align_two_witnesses.py -- two independent witnesses of the same text: where they diverge are the candidates.

## The case: damage no single-text-layer detector can see
An essay's text layer, in a stretch the scan had pencil underlining, carried inserted junk characters:
    the self of the e reassuring stability
    to restore a an unbroken continuity
    of historians inverts 3 the relationshi ips
The sentence looks normal except for one extra token, and "a", "e", "3" are neither rare nor illegal. Every
glue, split and rare-non-word detector is silent. Its sibling is a dropped passage that happens to end on real
words on both sides ("he came to the conclusion" with three lines missing in between): no non-word is left as
a clue. A detector that uses a dictionary as its judge is blind, in principle, to damage that leaves valid text.

## The fix: not a cleverer judge, a second witness
The same essay was in the library twice: in its first-edition collection and in a later collected-works volume,
scanned and OCR'd independently. Both wrong in the same place, and wrong the same way, is very unlikely, so the
points of divergence are the candidates -- without knowing in advance what the damage looks like.

⚠ A divergence is not a defect. Three sources must be kept apart:
  1. A's OCR is wrong (fix A);
  2. B's OCR is wrong (nothing to do with A);
  3. 🔴 the two editions really differ (the later one was revised: "whited sepulchres" became "blanched tombs").
So this tool only lists divergences; every decision goes back to the page image. Never copy B's words into A
automatically: that rewrites A as B. It writes nothing.

Usage:
  python align_two_witnesses.py <A.txt> <B.txt> [--b-head "<first words of the piece>"] [--b-tail "<last words>"]
         [--heads "<regex of running-head lines>"] [--offset N] [--context 7]
  python align_two_witnesses.py --self-test
  A keeps its `===== page N =====` anchors (PDF pages; --offset N prints the printed page = PDF page + N).
  B may be a whole volume: --b-head / --b-tail cut the piece out (take them from A's first and last sentences,
  which both editions share). --heads strips whole lines that are only a running head (with or without a page
  number) on both sides; the count of stripped lines is always printed, since a silent exclusion once hid half a
  corpus. Running heads are the largest source of false divergences.
Exit codes: 0 = listed / 1 = the comparison is not trustworthy (B could not be cut; word counts too different) / 2 = input missing
"""
import difflib
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ANCHOR = re.compile(r"^=+\s*page\s+(\d+)\s*=+\s*$", re.M)
WORD = re.compile(r"[A-Za-z]+")
RATIO_OK = (0.85, 1.15)


def strip_heads(text: str, heads, tag: str) -> str:
    if not heads:
        return text
    rx = re.compile(r"^[ \t]*\d*[ \t]*(?:" + heads + r")[ \t]*\d*[ \t]*$", re.M | re.I)
    n = len(rx.findall(text))
    print(f"   ✂ {tag}: stripped {n} running-head line(s) (whole lines only; the same words in the body are untouched)")
    return rx.sub("", text)


def words_with_page(text, keep_pages=True):
    """[(lowercase word, PDF page it belongs to)]; anchors are removed before splitting."""
    out, pg, pos = [], None, 0
    for m in ANCHOR.finditer(text):
        out += [(w.group().lower(), pg) for w in WORD.finditer(text[pos:m.start()])]
        pg = int(m.group(1)) if keep_pages else None
        pos = m.end()
    out += [(w.group().lower(), pg) for w in WORD.finditer(text[pos:])]
    return out


def align(ta: str, tb: str, b_head=None, b_tail=None, heads=None, offset=None, ctx=7, show=True):
    if b_head or b_tail:
        i = tb.find(b_head) if b_head else 0
        j = tb.find(b_tail) if b_tail else len(tb)
        if i < 0 or j < 0 or j <= i:
            print(f"🔴 the piece cannot be cut out of B (head at {i}, tail at {j}): this is a failure, not 'no divergence'")
            return 1, []
        tb = tb[i:j + (len(b_tail) if b_tail else 0)]
    ta, tb = strip_heads(ta, heads, "A"), strip_heads(tb, heads, "B")
    A, B = words_with_page(ta), words_with_page(tb, keep_pages=False)
    wa, wb = [w for w, _ in A], [w for w, _ in B]
    ratio = len(wb) / max(len(wa), 1)
    print(f"■ A {len(wa):,} words   B {len(wb):,} words   ratio B/A = {ratio:.3f}")
    if not RATIO_OK[0] < ratio < RATIO_OK[1]:
        print("   🔴 word counts too different: probably the wrong range, not editions this different => not trustworthy")
        return 1, []
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    same = sum(o[2] - o[1] for o in sm.get_opcodes() if o[0] == "equal")
    print(f"   aligned: {same:,} words the same ({same / max(len(wa), 1):.1%}) · {len(ops)} divergence(s)\n")
    rows = []
    for k, (tag, i1, i2, j1, j2) in enumerate(ops, 1):
        pg = next((p for _, p in A[i1:i2] if p), None) or (A[i1 - 1][1] if i1 else None)
        left, right = " ".join(wa[max(0, i1 - ctx):i1]), " ".join(wa[i2:i2 + ctx])
        aa, bb = " ".join(wa[i1:i2]) or "(none)", " ".join(wb[j1:j2]) or "(none)"
        rows.append((tag, pg, aa, bb))
        if show:
            printed = f" (printed ~{pg + offset})" if pg is not None and offset is not None else ""
            print(f"-- #{k}  {tag}  PDF page {pg}{printed}")
            print(f"     A: …{left} [{aa}] {right}…")
            print(f"     B: …{left} [{bb}] {right}…")
    if show:
        print("\n🔴 a divergence is not a defect: A's OCR wrong / B's OCR wrong / the editions really differ.")
        print("⚠ decide on the page image; never copy B's words into A automatically.")
    return 0, rows


def _self_test() -> int:
    import io, contextlib
    body = ("An archive is patient and uneven work. It operates on a field of scattered and half-sorted papers, "
            "on records that have been copied, annotated and copied again by many hands. ") * 3   # invented text
    a = ("===== page 1 =====\nTHE ESSAY 139\n" + body.replace("operates on", "operates e on", 1) +
         "===== page 2 =====\nTHE ESSAY 140\n" + body.replace("whited", "whited") + "we must restore an unbroken continuity.\n")
    b = ("Preface of the volume. " + "COLLECTED WORKS 81\n" + body + "\nCOLLECTED WORKS 82\n" + body +
         "we must restore an unbroken continuity.\n" + "Index of names.")
    checks = []
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        code, rows = align(a, b, b_head="An archive is patient", b_tail="unbroken continuity", heads=r"THE ESSAY|COLLECTED WORKS", offset=138)
    out = buf.getvalue()
    checks.append(("an inserted real token ('e') is a divergence on its PDF page", code == 0 and any(r[2] == "e" and r[1] == 1 for r in rows)))
    checks.append(("running heads stripped and counted on both sides", "A: stripped 2" in out and "B: stripped 1" in out))
    checks.append(("printed page shown with --offset", "(printed ~139)" in out))
    with contextlib.redirect_stdout(io.StringIO()):
        code2, _ = align(a, b, b_head="not in B at all")
    checks.append(("a piece that cannot be cut out is a failure (1), not 'no divergence'", code2 == 1))
    with contextlib.redirect_stdout(io.StringIO()):
        code3, _ = align(a, b * 3)
    checks.append(("word counts too different => not trustworthy (1)", code3 == 1))
    bad = 0
    for name, ok in checks:
        bad += not ok
        print(("ok   " if ok else "FAIL ") + name)
    print(f"{len(checks) - bad} of {len(checks)} as expected")
    return 1 if bad else 0


def main() -> int:
    a = sys.argv[1:]
    if "--self-test" in a:
        return _self_test()

    def opt(k, d=None):
        return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d
    vals = {opt(k) for k in ("--b-head", "--b-tail", "--heads", "--offset", "--context")}
    files = [x for x in a if not x.startswith("--") and x not in vals]
    if len(files) != 2:
        print(__doc__)
        return 2
    pa, pb = Path(files[0]), Path(files[1])
    for p in (pa, pb):
        if not p.is_file():
            print(f"🔴 not found: {p} (that is 'not read', not 'nothing to report')")
            return 2
    off = opt("--offset")
    code, _ = align(pa.read_text(encoding="utf-8", errors="replace"), pb.read_text(encoding="utf-8", errors="replace"),
                    opt("--b-head"), opt("--b-tail"), opt("--heads"), int(off) if off else None, int(opt("--context", 7)))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
