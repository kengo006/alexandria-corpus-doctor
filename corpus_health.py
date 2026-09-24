# -*- coding: utf-8 -*-
"""corpus_health.py — six-gate health check for a plain-text corpus layer.

Your grep can lie: a text file can LOOK complete while being unsearchable —
words split by stray spaces, sentences glued into single tokens, accents
misread so French terms never match, pages unlocatable. Every gate below was
built from a damage type that slipped past naive checks (file size, encoding)
in a real ~530-text corpus. Each gate is designed to fire ONLY on true damage.

Gates:
  1. phrase density   — "of the / in the / to the ..." per 10k words. An English
                        file below 15% of the corpus median is phrase-dead
                        (characters scattered or layers interleaved).
  2. accent misreads  — systematic OCR substitution (Collège -> Collége).
                        >50% misread = French/Greek-transliteration terms
                        are unfindable by exact grep.
  3. hidden OCR layer — GlyphLessFont in the PDF = an invisible OCR layer.
                        Only DUAL layers are dangerous (the two layers
                        interleave and shred phrases); single = plain scan, fine.
  4. page anchors     — neither \\f form feeds (pdftotext-style) nor
                        `===== page N =====` markers = the file cannot be
                        cited by page; the evidence chain loses a link.
  5. splitpair rate   — adjacent token pairs that join into a common word
                        (`polit ical`); the direct measure of fragmentation.
  6. glue rate        — tokens >= 18 letters (`Researchisneededto`); the blind
                        spot of gate 5 — when a whole phrase is one token there
                        are no adjacent pairs left to join.

Thresholds are calibrated on one ~530-text Western-language humanities corpus.
Gate 1 adapts to your corpus (median-relative); gates 5-6 use absolute floors —
run once, read your distribution, then decide what to trust.

Usage:
  python corpus_health.py --corpus <txt-root> [--pdf <pdf-root>] [--no-pdf]
  (--pdf enables gate 3; requires PyMuPDF: uv run --with pymupdf ...)
Exit code 0 = every gate that ran found nothing; 1 = findings, or a gate you
asked for (--pdf without PyMuPDF) could not run.

CORPUS_ROOT env var is honored when --corpus is omitted.
Files and directories whose names start with "_" are ignored (workspace convention).

Ported from the production tooling of the alexandria librarian role
(https://github.com/kengo006/alexandria). Battle log: LESSONS.md.
"""
import argparse
import os
import re
import sys

PHRASES = ["of the", "in the", "to the", "is not", "there is"]
# Accent probes: common French words + Greek transliterations. Extend for your corpus.
ACCENT = [("Collège", "Collége"), ("Bibliothèque", "Bibliothéque"), ("être", "étre"),
          ("rêve", "réve"), ("après", "aprés"), ("tekhnē", "tekhné"), ("askēsis", "askésis")]
CJK = re.compile(r"[一-鿿]")
PAGEMARK = re.compile(r"={3,}\s*(?:page|omnibus\s*p\.?)\s*\d+", re.I)


def walk_txt(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith("_")]
        for fn in fns:
            if fn.lower().endswith(".txt") and not fn.startswith("_"):
                yield os.path.join(dp, fn)


def build_freq(root):
    """Corpus-wide word frequency (for gate 5)."""
    from collections import Counter
    f = Counter()
    for p in walk_txt(root):
        s = open(p, "rb").read().decode("utf-8", errors="replace")
        f.update(w.lower() for w in re.findall(r"[A-Za-z]{2,}", s))
    return f


def scan_txt(root, freq=None):
    rows = []
    for p in walk_txt(root):
        s = open(p, "rb").read().decode("utf-8", errors="replace")
        if len(s) < 20000:
            continue
        rel = os.path.relpath(p, root)
        toks = re.findall(r"[A-Za-z]+", s)
        # Gate 6, glue rate: gate 5's blind spot — a fully glued sentence has no
        # adjacent word pair to join, so its splitpair figure looks PERFECT.
        # 12 OCR-disaster files once sailed through three metrics this way.
        glue = (sum(1 for w in toks if len(w) >= 18) / len(toks) * 1000) if len(toks) >= 300 else None
        sp = None
        if freq is not None and len(toks) >= 1500:
            # v2 fix (bought with 56 false positives): joined word must be >= 5
            # letters. v1 did not exclude single-letter tokens, so letter-spaced
            # headings ("C H A P T E R") produced (C,H)->ch, (H,A)->ha ... and
            # those two-letter strings — accumulated from headings corpus-wide —
            # became "common words" in the dictionary: CIRCULAR CONTAMINATION.
            # The defect had written itself into the lexicon used to detect it.
            n = 0
            for a, b in zip(toks, toks[1:]):
                j = (a + b).lower()
                if len(j) < 5:
                    continue
                if freq[j] >= 30 and freq[j] > 3 * max(freq[a.lower()], freq[b.lower()]):
                    n += 1
            sp = n / len(toks) * 1000
        words = len(toks)
        cjk = len(CJK.findall(s)) / max(len(s), 1)
        good = sum(s.count(g) for g, _ in ACCENT)
        bad = sum(s.count(b) for _, b in ACCENT)
        rows.append({
            "f": rel, "chars": len(s), "words": words, "cjk": cjk, "sp": sp, "glue": glue,
            # Language call is RATIO-based. A keyword test once exempted a whole
            # damaged file because it contained one "Politikwissenschaft".
            "de": (sum(1 for w in toks if w.lower() in {"der", "die", "das", "und", "nicht", "von", "dem", "den", "ist"})
                   > sum(1 for w in toks if w.lower() in {"the", "of", "and", "to", "in", "that", "is", "was"})),
            "phrase": sum(s.count(x) for x in PHRASES) / max(words, 1) * 10000,
            "acc_good": good, "acc_bad": bad,
            "acc_ratio": (bad / (good + bad) * 100) if (good + bad) >= 5 else None,
            "page_ok": s.count("\f") > 0 or bool(PAGEMARK.search(s)),
        })
    return rows


def scan_pdf(pdf_root):
    """None when PyMuPDF is missing: the caller must report gate 3 as NOT RUN,
    never as OK (an empty scan and an impossible scan are different results)."""
    try:
        import pymupdf as fitz          # the module's current name
    except ImportError:
        try:
            import fitz                 # PyMuPDF before the rename
        except ImportError:
            return None
    out = []
    for dp, dns, fns in os.walk(pdf_root):
        dns[:] = [d for d in dns if not d.startswith("_")]
        for fn in fns:
            if not fn.lower().endswith(".pdf"):
                continue
            p = os.path.join(dp, fn)
            try:
                d = fitz.open(p)
                n = d.page_count
                idx = sorted({0, n // 2, n - 1, *range(0, n, max(1, n // 10))})[:12]
                fonts = set()
                for pno in idx:
                    if 0 <= pno < n:
                        for f in d[pno].get_fonts(full=True):
                            fonts.add(f[3])
                if not any("GlyphLess" in f for f in fonts):
                    d.close()
                    continue
                # Classify: sample three pages, count chars NOT in the OCR font.
                tot = ocr = 0
                for pno in sorted({n // 4, n // 2, (3 * n) // 4}):
                    for blk in d[pno].get_text("dict")["blocks"]:
                        if blk.get("type") != 0:
                            continue
                        for line in blk["lines"]:
                            for sp in line["spans"]:
                                tot += len(sp["text"])
                                if "GlyphLess" in sp["font"]:
                                    ocr += len(sp["text"])
                d.close()
                other = (tot - ocr) / max(tot, 1) * 100
                out.append({"f": os.path.relpath(p, pdf_root), "pages": n,
                            "other_pct": other, "dual": other > 15})
            except Exception as e:
                out.append({"f": os.path.relpath(p, pdf_root), "err": str(e)[:60]})
    return out


def main():
    ap = argparse.ArgumentParser(description="Six-gate corpus health check")
    ap.add_argument("--corpus", default=os.environ.get("CORPUS_ROOT"),
                    help="root of the .txt corpus layer (or set CORPUS_ROOT)")
    ap.add_argument("--pdf", default=None,
                    help="root of the source PDFs (enables gate 3)")
    ap.add_argument("--no-pdf", action="store_true", help="skip gate 3")
    args = ap.parse_args()
    if not args.corpus or not os.path.isdir(args.corpus):
        ap.error("--corpus <dir> is required (or set CORPUS_ROOT to an existing directory)")

    print("=" * 78)
    print("  corpus_health — six-gate text-layer check")
    print("=" * 78)
    freq = build_freq(args.corpus)
    rows = scan_txt(args.corpus, freq)
    print(f"  scanned {len(rows)} files (>= 20 KB) under {args.corpus}")
    if not rows:
        print("  nothing to check - is --corpus pointing at your .txt tree?")
        return 1
    en = [r for r in rows if r["cjk"] <= 0.05]
    med = sorted(r["phrase"] for r in en)[len(en) // 2] if en else 0
    fails = 0

    print(f"\nGate 1: phrase density ({len(en)} Latin-script files, median {med:.1f}/10k words)")
    dead = [r for r in en if r["phrase"] < med * 0.15]
    for r in sorted(dead, key=lambda x: x["phrase"]):
        print(f"   RED {r['phrase']:6.1f}/10k  {r['f']}")
    print(f"   {'OK: no phrase-dead files' if not dead else f'FAIL: {len(dead)} phrase-dead (may be non-English false positives - verify each by eye)'}")
    fails += len(dead)

    print("\nGate 2: accent misreads")
    accbad = [r for r in rows if r["acc_ratio"] is not None and r["acc_ratio"] > 50]
    for r in sorted(accbad, key=lambda x: -x["acc_bad"]):
        print(f"   RED misread {r['acc_ratio']:5.1f}% (good {r['acc_good']} / bad {r['acc_bad']})  {r['f']}")
    print(f"   {'OK: no systematic misreads' if not accbad else f'FAIL: {len(accbad)} files (French/transliterated terms unfindable by exact grep - search accent-insensitively)'}")
    fails += len(accbad)

    print("\nGate 4: page anchors")
    nopage = [r for r in rows if not r["page_ok"]]
    for r in sorted(nopage, key=lambda x: -x["chars"]):
        print(f"   RED {r['chars']:>9,} chars  {r['f']}")
    print(f"   {'OK: all files page-locatable' if not nopage else f'FAIL: {len(nopage)} files with no page markers at all'}")
    fails += len(nopage)

    print("\nGate 5: splitpair rate (joined word >= 5 letters; reference corpus: median 0.20 permille, P95 2.91)")
    spbad = [r for r in en if r["sp"] is not None and r["sp"] >= 5.0]
    for r in sorted(spbad, key=lambda x: -x["sp"])[:15]:
        print(f"   RED {r['sp']:6.2f} permille  {r['f']}")
    if len(spbad) > 15:
        print(f"   ... {len(spbad)} files total")
    print(f"   {'OK: no fragmentation above floor' if not spbad else f'FAIL: {len(spbad)} files >= 5 permille (words split apart - grep and embeddings both degraded; run repair_wordsplits.py, or fix_pipeline.py --pdf if you have the source PDFs)'}")
    fails += len(spbad)

    print("\nGate 6: glue rate (tokens >= 18 letters per 1k; healthy baseline median 0.20 permille)")
    gluebad = [r for r in rows if r["glue"] is not None and r["glue"] >= 3.0
               and not r["de"] and r["cjk"] <= 0.05]
    for r in sorted(gluebad, key=lambda x: -x["glue"])[:12]:
        print(f"   RED {r['glue']:6.2f} permille  {r['f']}")
    print(f"   {'OK: no glued files' if not gluebad else f'FAIL: {len(gluebad)} files >= 3 permille (sentences glued into single tokens - invisible to gate 5; run unglue_words.py)'}")
    fails += len(gluebad)

    skipped, pdfs = [], None
    if args.pdf and not args.no_pdf:
        print("\nGate 3: hidden OCR layers in PDFs")
        pdfs = scan_pdf(args.pdf)
        if pdfs is None:
            print("   NOT RUN: PyMuPDF is not installed (pip install pymupdf), so gate 3 checked nothing")
            skipped.append("gate 3")
    if pdfs is not None:
        # Cross-check: a dual-layer PDF is NOT a problem if its text layer was
        # already extracted properly. Without this, the gate keeps flagging
        # handled files forever - and a gate that cries wolf gets ignored.
        bytxt = {r["f"][:-4]: r for r in rows}
        dual = []
        for x in pdfs:
            if x.get("err"):
                print(f"   WARN could not open {x['f']}: {x['err']}")
                continue
            if not x["dual"]:
                continue
            t = bytxt.get(x["f"][:-4])
            if t and t["phrase"] >= med * 0.5:
                print(f"   ok  dual-layer but text layer extracted cleanly (phrase {t['phrase']:.0f}/10k)  {x['f']}")
            else:
                got = f"phrase {t['phrase']:.0f}/10k" if t else "no matching .txt"
                print(f"   RED dual-layer, unhandled (non-OCR font {x['other_pct']:.1f}% - {got})  {x['f']}")
                dual.append(x)
        single = [x for x in pdfs if not x.get("dual") and not x.get("err")]
        print(f"   {len(pdfs)} PDFs carry an OCR layer: {len(single)} single-layer scans (fine), {len(dual)} dual-layer to handle")
        print(f"   {'OK: no unhandled dual layers' if not dual else 'FAIL: re-extract excluding the OCR font, or re-OCR from images'}")
        fails += len(dual)

    print("\n" + "=" * 78)
    if skipped and fails == 0:
        # never print the words "ALL GREEN" here: a log check like `grep "ALL GREEN"` would pass on "not ALL GREEN"
        print(f"  result: INCOMPLETE - {', '.join(skipped)} did not run (no findings in the gates that did)")
    else:
        print(f"  result: {'ALL GREEN' if fails == 0 else f'{fails} finding(s) to handle'}"
              + (f" ({', '.join(skipped)} did not run)" if skipped else ""))
    print("=" * 78)
    return 1 if (fails or skipped) else 0


if __name__ == "__main__":
    sys.exit(main())
