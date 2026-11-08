# -*- coding: utf-8 -*-
"""extract_disagree.py -- two independent extraction paths over the same PDF: where they disagree is where the
defects are.

## What it is for
A full human read of the text layer catches one class nothing else does: damage where both halves are real words
("dearly" for "clearly", "modem" for "modern"); a non-word gate is blind to it by construction. A full read costs
a person per page. This finds most of what a full read finds, at the cost of a computer.

## The principle
Two extraction paths read the same glyphs; where they agree, they are very unlikely to be wrong in the same way.
The criterion is not "is this word in the dictionary" (the non-word gate's blind spot) but "do the two read the
same", so real-word damage shows up too. Path A is your text layer; path B is PyMuPDF reading the PDF directly
(or any second witness passed to analyze_pages(), e.g. an EPUB of the same edition aligned to pages).

## What it does not catch (printed with every report, so a quiet result is not read as clean)
1. what both paths get wrong the same way -- a misprint in the book (which should not be "fixed" anyway);
2. a scan with a single OCR layer: there is no second path (use a second OCR engine as path B);
3. errors of placement (right words, wrong paragraph or page);
4. a split both paths make at the same place ("conver -sational"); control characters (not words).

## The unit is the word sequence, not characters
The text layer's job is that a keyword can be found. Differences in spaces, punctuation and line breaks do not
change what anyone can find, so comparing them only adds noise. Both sides are reduced to [A-Za-z'] words and
aligned page by page with difflib.

## Known noise, removed first
- markdown furniture from layout parsers (headings, image comments, table pipes, link targets);
- running heads that land on different lines: compare within a page; neighbouring pages are used only to rule
  out "moved to the next page" as a missing passage;
- hyphenation differences ("demo"+"cracy" vs "democracy"): classified by corpus frequency, not skipped (below);
- apostrophes and accents: both sides get one normalisation (NFKD without marks, curly to straight apostrophe,
  a word-final apostrophe dropped).

## 🔴 Why "joined they are equal" is classified, not skipped
The first version skipped every case where the two sides were equal once joined, intending to skip hyphenation.
It skipped a whole layer of defects with it: a line whose spaces were all lost ("Theexamplesaboveillustrate"),
"howpeople", letter-spaced "S ynchronicity", a dash that glued two words ("systemslittle") -- all equal when
joined. Now: A glued (A is not a word, B's parts are), A split (A is fragments, B is a word), a correct join.
It also skipped pure insertions and deletions as "layout difference", hiding dropped lines and duplicated
passages: runs of >= K_RUN words get their own buckets, after ruling out "moved on the same page" and "moved to
a neighbouring page".

## The word-frequency proxy and its known biases
"Is this a word" = the number of files in your corpus containing it (built at run time from --corpus).
(a) the corpus's own damage votes: a glued form present in many damaged files looks common; so a join is judged
    by the ratio of its parts' frequency to its own (RATIO_JOIN), not by its frequency alone;
(b) new names and coinages have frequency 0: the B side's separator (a hyphenation or not) decides those;
(c) words normally written together but broken at a line end in the PDF ("blockchain") cause about a fifth of
    the "A glued" bucket's false positives.
The thresholds were calibrated on a corpus of about 740 files; on a much smaller corpus they shift, and the
report prints the corpus size so you can tell.

Measured upstream (63 articles whose full human read was on record): of the defects marked "fix", 83% found;
of those marked "check the image", 59%. Most misses were in the declared blind spots (a misprint in the book,
both paths wrong, a single OCR layer); about 1% were real misses.

Usage:
  python extract_disagree.py --text <text-layer.txt> --pdf <source.pdf> --corpus <text-layer folder> [--limit 40]
  python extract_disagree.py --self-test
Needs PyMuPDF for path B. The text layer carries `===== page N =====` anchors.
"""
import difflib
import html
import re
import sys
import unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ANCHOR = re.compile(r"={3,}\s*page\s+(\d+)\s*={3,}", re.I)
WORD = re.compile(r"[A-Za-z][A-Za-z']*")
FURNITURE = re.compile(r"<!--.*?-->|^#{1,6}\s|^\s*\|.*\|\s*$|\]\((?:https?://|www\.)[^)]*\)", re.M)
SHY = chr(0x00AD)
# Between two B-side words: a hyphenation = a hard hyphen followed by whitespace, or a soft hyphen (U+00AD) with or
# without whitespace (a soft hyphen is by definition a break point). A real compound mid-line ("self-presentation")
# has a hard hyphen and no space, so it is not taken for a hyphenation.
HYPH_BREAK = re.compile(f"^(?:[-{chr(0x2010)}{chr(0x2011)}]\\s+|{SHY}[\\s{SHY}]*)$")
APOS = str.maketrans({chr(0x2019): "'", chr(0x2018): "'", chr(0x02BC): "'", chr(0x2032): "'"})
MAX_SUB = 3          # replacements up to this many words a side are classified by frequency; longer = misaligned
RATIO = 8            # empirical
T_WORD = 20          # files containing it >= this: a common real word (empirical)
T_BAD = 2            # files containing it <= this: found almost only in damaged files (empirical)
K_RUN = 6            # insertions/deletions of >= K words are reported (a running head is usually < 6 words)
RATIO_JOIN = 4       # parts >= 4 x the joined form's frequency: the joined form is a glue (real compounds ~1x)
FUNC = {"the", "of", "and", "to", "a", "in", "is", "that", "for", "with", "as", "on", "by", "this", "be", "are",
        "it", "or", "from", "an", "at", "which", "not", "we", "their", "was", "were", "has", "have", "its", "can",
        "than", "these", "they", "such", "into", "more", "but", "also", "our", "between", "whether", "while"}


def norm(s: str) -> str:
    """One normalisation for both sides: HTML entities ("&lt;" must not become the word "lt"), NFKD without marks
    (ligatures expanded), curly apostrophes straightened."""
    s = unicodedata.normalize("NFKD", html.unescape(s))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).translate(APOS)


def words_seps(s: str):
    """Words with the separator after each (B side: tells a hyphenation from a space or a dash)."""
    t = norm(s)
    ms = list(WORD.finditer(t))
    out = []
    for i, m in enumerate(ms):
        w = m.group(0).rstrip("'")
        if w:
            out.append((w, t[m.end():ms[i + 1].start()] if i + 1 < len(ms) else ""))
    return out


def words(s: str):
    return [w for w, _ in words_seps(s)]


def build_df(corpus: Path):
    """{word: number of .txt files under corpus containing it}. The corpus is yours; nothing is shipped or cached."""
    df = {}
    files = list(corpus.rglob("*.txt"))
    for f in files:
        for w in {w.lower() for w in words(f.read_text(encoding="utf-8", errors="replace"))}:
            df[w] = df.get(w, 0) + 1
    return df, len(files)


def dict_ok(d) -> bool:
    """Self-check: a frequency table without these is the wrong table, and every word would be judged 'not a word'
    -- a classifier that puts everything in one bucket gives a tidy, wrong answer and no error."""
    return all(w in d for w in ("the", "and", "of"))


def pages_from_txt(t):
    ms = [(m.start(), m.end(), int(m.group(1))) for m in ANCHOR.finditer(t)]
    return {n: FURNITURE.sub(" ", t[e:(ms[i + 1][0] if i + 1 < len(ms) else len(t))]) for i, (s, e, n) in enumerate(ms)}


def pages_from_pdf(pdf):
    import pymupdf
    with pymupdf.open(pdf) as d:
        return {i + 1: d[i].get_text() for i in range(d.page_count)}


def _grams(seq, k=3):
    return {tuple(seq[i:i + k]) for i in range(len(seq) - k + 1)}


def _covered(run, pool, step: int = 16) -> float:
    """Coverage = the larger of (1) 16-character chunks of the joined words and (2) word trigrams. Trigrams alone
    miss when the two sides hyphenate at different points; chunks alone miss when blocks on a page are reordered.
    Each catches the other's failure."""
    pool_str, pool_g = pool
    s = "".join(run).lower()
    if len(s) < step:
        c1 = 1.0 if s and s in pool_str else 0.0
    else:
        chunks = [s[i:i + step] for i in range(0, len(s) - step + 1, step)]
        c1 = sum(c in pool_str for c in chunks) / len(chunks)
    g = _grams([w.lower() for w in run])
    return max(c1, len(g & pool_g) / len(g) if g else 0.0)


def _prose(run) -> bool:
    """Running text vs figure labels: >= 20% function words is running text."""
    return sum(w.lower() in FUNC for w in run) / max(len(run), 1) >= 0.2


def analyze_pages(A: dict, BS: dict, d) -> dict:
    """The classification itself. A = {page: [words]} (your text layer); BS = {page: [(word, separator)]} (the
    second witness). One implementation for every kind of second witness: two copies would drift."""
    B = {n: [w for w, _ in v] for n, v in BS.items()}
    common = sorted(set(A) & set(B))

    def df(seq):
        vs = [d.get(w.lower(), 0) for w in seq]
        return min(vs) if vs else 0

    def pool(side, pages):
        ws = [w.lower() for p in pages for w in side.get(p, [])]
        return "".join(ws), _grams(ws)

    out = {k: [] for k in ("both", "a_bad", "a_glue", "a_split", "join_amb", "a_missing", "a_missing_label",
                           "a_extra", "a_extra_cross")}
    cnt = {k: 0 for k in ("fixed", "join_ok", "moved_same_page", "missing_moved_neighbor", "tiny_runs", "misalign")}
    out["pages"], out["words_a"], out["words_b"] = len(common), sum(map(len, A.values())), sum(map(len, B.values()))
    seen = set()

    def emb_glue(n, xs, ys) -> bool:
        """In A's words: a rare long word equal to several consecutive B words (a glue hidden in a misaligned or moved block)."""
        found, ly = False, [w.lower() for w in ys]
        for t in xs:
            tl = t.lower()
            if len(tl) < 6 or d.get(tl, 0) > T_BAD or (n, tl) in seen:
                continue
            for i in range(len(ly)):
                if not tl.startswith(ly[i]):
                    continue
                acc, j = ly[i], i
                while len(acc) < len(tl) and j + 1 < min(i + 10, len(ly)):
                    j += 1
                    acc += ly[j]
                if acc == tl and j > i:
                    out["a_glue"].append((n, [t], ys[i:j + 1], d.get(tl, 0), df(ys[i:j + 1])))
                    seen.add((n, tl))
                    found = True
                    break
        return found

    def emb_split(n, xs, ys) -> bool:
        """A real word on the B side broken into consecutive rare fragments on the A side."""
        found, lx = False, [w.lower() for w in xs]
        for u in ys:
            ul = u.lower()
            if d.get(ul, 0) < 3 or (n, ul) in seen:
                continue
            for i in range(len(lx) - 1):
                if not ul.startswith(lx[i]) or lx[i] == ul:
                    continue
                acc, j = lx[i], i
                while len(acc) < len(ul) and j + 1 < min(i + 4, len(lx)):
                    j += 1
                    acc += lx[j]
                if acc == ul and j > i and df(xs[i:j + 1]) <= T_BAD:
                    out["a_split"].append((n, xs[i:j + 1], [u], df(xs[i:j + 1]), d.get(ul, 0)))
                    seen.add((n, ul))
                    found = True
                    break
        return found

    for n in common:
        wa, wb, sb = A[n], B[n], [s for _, s in BS[n]]
        sm = difflib.SequenceMatcher(None, [w.lower() for w in wa], [w.lower() for w in wb], autojunk=False)
        ins, dels = [], []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            x, y = wa[i1:i2], wb[j1:j2]
            if not x or not y:                                # pure insertion / deletion
                run, bucket = (y, ins) if not x else (x, dels)
                if len(run) >= K_RUN:
                    bucket.append(run)
                else:
                    cnt["tiny_runs"] += 1
                continue
            jx, jy = "".join(x).lower(), "".join(y).lower()
            da, db = df(x), df(y)
            if jx == jy:                                       # equal once joined: classify by what separates B's words
                if len(x) < len(y):                            # A has fewer words
                    inner = sb[j1:j2 - 1]
                    hyph = bool(inner) and all(HYPH_BREAK.match(s) for s in inner)
                    # "A is common so A is a real word" is fooled by the corpus's own damage (a glued form present in
                    # 65 damaged files). Compare the parts' frequency with the joined form's instead.
                    proper = any(w[:1].isupper() for w in y[1:])   # hyphen then a capital: a real hyphen in a name
                    if hyph and proper:
                        out["a_glue"].append((n, x, y, da, db))
                    elif hyph:                                 # B is a line-end hyphenation
                        if db <= T_BAD:
                            cnt["join_ok"] += 1               # fragments: A joined them correctly
                        elif da < T_WORD and db >= T_WORD:
                            out["a_glue"].append((n, x, y, da, db))   # two real words, rare compound: a real hyphen lost
                        elif db >= RATIO_JOIN * max(da, 1):
                            out["a_glue"].append((n, x, y, da, db))   # common joined form, far rarer than its parts: corpus-wide glue
                        else:
                            cnt["join_ok"] += 1               # "some-" + "thing" -> "something"
                    elif da < T_WORD or db >= RATIO_JOIN * da:
                        out["a_glue"].append((n, x, y, da, db))       # A lost a space, a dash or a mid-line hyphen
                    else:
                        out["join_amb"].append((n, x, y, da, db))     # "any one" / "anyone": cannot tell
                elif len(x) > len(y):                          # A has more words
                    if db >= max(RATIO * da, 3):
                        out["a_split"].append((n, x, y, da, db))      # A is fragments
                    elif da >= T_WORD and db <= T_BAD:
                        cnt["join_ok"] += 1                   # B glued, A is right
                    else:
                        out["join_amb"].append((n, x, y, da, db))
                continue
            if len(x) > MAX_SUB or len(y) > MAX_SUB:          # misaligned block: look inside it for glues and splits only
                found = emb_glue(n, x, y)
                found = emb_split(n, x, y) or found
                if not found:
                    cnt["misalign"] += 1
                continue
            if da >= max(db * RATIO, 1):
                cnt["fixed"] += 1
            elif db >= max(da * RATIO, 1):
                out["a_bad"].append((n, x, y, da, db))
            else:
                out["both"].append((n, x, y, da, db))
        same_a, same_b = pool(A, [n]), pool(B, [n])
        nb_a, nb_b = pool(A, [n - 2, n - 1, n + 1, n + 2]), pool(B, [n - 2, n - 1, n + 1, n + 2])
        # A moved block is not reported as a whole, but glues and splits inside it are still looked for.
        for r in ins:                                          # in B, not here in A
            if _covered(r, same_a) >= 0.8:
                cnt["moved_same_page"] += 1
                emb_split(n, wa, r)
            elif _covered(r, nb_a) >= 0.8:
                cnt["missing_moved_neighbor"] += 1
            else:
                out["a_missing" if _prose(r) else "a_missing_label"].append((n, [], r, 0, df(r)))
        for r in dels:                                         # in A, not here in B
            if _covered(r, same_b) >= 0.8:
                cnt["moved_same_page"] += 1
                emb_glue(n, r, wb)
            elif _covered(r, nb_b) >= 0.8:
                out["a_extra_cross"].append((n, r, [], df(r), 0))
            else:
                out["a_extra"].append((n, r, [], df(r), 0))
    # A running head or a download stamp appears once per page and is often dropped or moved by one path: the same
    # string (first 24 characters) on >= 3 pages is furniture, counted and not reported.
    cnt["furniture_runs"] = 0
    for b in ("a_missing", "a_missing_label", "a_extra"):
        key = lambda e: "".join(e[1] or e[2]).lower()[:24]
        pages_by_key = {}
        for e in out[b]:
            pages_by_key.setdefault(key(e), set()).add(e[0])
        keep = [e for e in out[b] if len(pages_by_key[key(e)]) < 3]
        cnt["furniture_runs"] += len(out[b]) - len(keep)
        out[b] = keep
    out.update(cnt)
    return out


LABELS = (("both", "🔴🔴 similar frequency, different words (a human must look: real-word damage lands here)"),
          ("a_bad", "🔴 A far rarer than B (the text layer is damaged)"),
          ("a_glue", "🔴 A glued (A is not a word; B's parts are)"),
          ("a_split", "🔴 A split (A is fragments; B is a word)"),
          ("a_missing", f"🔴 A missing, running text (>= {K_RUN} words in B absent from A and A's neighbouring pages)"),
          ("a_missing_label", "🟡 A missing, figure or table labels (< 20% function words)"),
          ("a_extra", f"🟡 A extra (>= {K_RUN} words absent from this and neighbouring PDF pages)"),
          ("a_extra_cross", "🟡 A extra but on a neighbouring PDF page (a duplicated passage at a page boundary?)"),
          ("join_amb", "🟡 equal once joined, cannot tell which side is right"))


def report(name, r, n_files, limit=60):
    print(f"== extraction disagreement: {name[:60]}")
    print(f"   A = text layer | B = PyMuPDF on the PDF | pages compared {r['pages']} | words A {r['words_a']:,} / B {r['words_b']:,}"
          f" | frequency table from {n_files} file(s)" + ("  ⚠ small corpus: the thresholds were calibrated on ~740" if n_files < 200 else ""))
    print(f"   ✅ not defects: A right or B damaged {r['fixed']} · correct joins {r['join_ok']} · moved on the page {r['moved_same_page']}"
          f" · in B, on A's neighbouring page {r['missing_moved_neighbor']} · runs under {K_RUN} words {r['tiny_runs']}"
          f" · furniture on >= 3 pages {r['furniture_runs']} (not reported)")
    print(f"   ⚠ misaligned blocks {r['misalign']} (over {MAX_SUB} words a side, nothing found inside): NOT LOOKED AT, not clean")
    for key, label in LABELS:
        rows = r[key]
        print(f"\n   {label}: {len(rows)}")
        for n, x, y, da, db in rows[:limit]:
            print(f"     p{n:>4}  A \"{' '.join(x)[:48]}\" df={da:<5} B \"{' '.join(y)[:48]}\" df={db}")
        if len(rows) > limit:
            print(f"     … {len(rows) - limit} more (truncated in display only; counts are complete)")
    print("\n⚠ a disagreement is not a verdict: a human decides which side is right. Blind by design: misprints in the book,"
          " errors both paths share, single-OCR scans, misplacement, splits both paths make alike.")


def _self_test() -> int:
    d = {"the": 700, "and": 700, "of": 700, "how": 600, "people": 500, "examples": 400, "above": 400, "illustrate": 300,
         "decision": 504, "making": 480, "decisionmaking": 65, "some": 600, "thing": 400, "something": 500,
         "democracy": 300, "synchronicity": 40, "systems": 300, "little": 400, "modern": 500, "clearly": 400, "s": 3}
    filler = "the public was gathered and the memory of the place was kept by the people of the town"
    A = {1: words("how" + "people " + filler), 2: words("S ynchronicity " + filler),
         3: words("democracy and something " + filler),
         4: words("decisionmaking " + filler), 5: words(filler)}
    BS = {1: words_seps("how people " + filler), 2: words_seps("Synchronicity " + filler),
          3: words_seps("demo-\ncracy and some-\nthing " + filler),
          4: words_seps("decision-\nmaking " + filler),
          5: words_seps(filler + " the people of the town were not told how the place had been taken from them")}
    r = analyze_pages(A, BS, d)
    glue = {" ".join(e[1]).lower() for e in r["a_glue"]}
    checks = [
        ("A glued: 'howpeople' (a space lost, not a hyphenation)", "howpeople" in glue),
        ("A split: 'S ynchronicity'", any(" ".join(e[1]) == "S ynchronicity" for e in r["a_split"])),
        ("correct joins: 'democracy', 'something'", r["join_ok"] >= 2),
        ("corpus-wide glue: 'decisionmaking' (parts 7x more common)", "decisionmaking" in glue),
        ("a dropped line in A is a missing run (running text)", len(r["a_missing"]) == 1),
        ("self-check: a table without common words is refused", not dict_ok({"df": 1, "bg": 2}) and dict_ok(d)),
    ]
    fur = {n: words("Downloaded by a university library on a date " + filler) for n in range(1, 5)}
    furb = {n: words_seps(filler) for n in range(1, 5)}
    r2 = analyze_pages(fur, furb, d)
    checks.append(("a download stamp on 4 pages is furniture, not 4 defects", r2["furniture_runs"] == 4 and not r2["a_extra"]))
    try:
        import pymupdf, tempfile, shutil, io, contextlib
        tmp = Path(tempfile.mkdtemp())
        (tmp / "corpus").mkdir()
        doc = pymupdf.open()
        for t in ("The examples above illustrate how people remember.", "Modern memory is clearly made, not kept."):
            pg = doc.new_page()
            pg.insert_text((72, 100), t, fontsize=11)
        doc.save(tmp / "w.pdf")
        (tmp / "corpus" / "w.txt").write_text("===== page 1 =====\nTheexamplesaboveillustrate how people remember.\n"
                                              "===== page 2 =====\nModem memory is dearly made, not kept.\n", encoding="utf-8")
        for i in range(3):
            (tmp / "corpus" / f"other{i}.txt").write_text("the and of examples above illustrate modern clearly memory", encoding="utf-8")
        dd, nf = build_df(tmp / "corpus")
        A2 = {n: words(t) for n, t in pages_from_txt((tmp / "corpus" / "w.txt").read_text(encoding="utf-8")).items()}
        B2 = {n: words_seps(t) for n, t in pages_from_pdf(tmp / "w.pdf").items()}
        r3 = analyze_pages(A2, B2, dd)
        checks.append(("end to end: a whole line's spaces lost is found", any("theexamplesaboveillustrate" == " ".join(e[1]).lower() for e in r3["a_glue"])))
        checks.append(("end to end: real-word damage 'modem'/'dearly' is reported", len(r3["a_bad"]) + len(r3["both"]) >= 2))
        shutil.rmtree(tmp, ignore_errors=True)
        skipped = 0
    except ImportError:
        skipped = 2
    bad = 0
    for name, ok in checks:
        bad += not ok
        print(("ok   " if ok else "FAIL ") + name)
    if skipped:
        print(f"skip  end to end, {skipped} checks (not installed: PyMuPDF)")
    print(f"{len(checks) - bad} of {len(checks)} as expected" + (f", {skipped} skipped" if skipped else ""))
    return 1 if bad else 0


def main() -> int:
    a = sys.argv[1:]
    if "--self-test" in a:
        return _self_test()

    def opt(k, dflt=None):
        return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else dflt
    text, pdf, corpus = opt("--text"), opt("--pdf"), opt("--corpus")
    if not (text and pdf and corpus):
        print(__doc__)
        return 2
    for p in (text, pdf):
        if not Path(p).is_file():
            print(f"🔴 not found: {p}")
            return 2
    d, n_files = build_df(Path(corpus))
    if not dict_ok(d):
        print("🔴 the frequency table lacks the most common words (wrong folder?): refusing to classify")
        return 2
    A = {n: words(t) for n, t in pages_from_txt(Path(text).read_text(encoding="utf-8", errors="replace")).items()}
    if not A:
        print("🔴 no `===== page N =====` anchors in the text layer: nothing to align")
        return 2
    BS = {n: words_seps(t) for n, t in pages_from_pdf(pdf).items()}
    report(Path(text).name, analyze_pages(A, BS, d), n_files, int(opt("--limit", 60)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
