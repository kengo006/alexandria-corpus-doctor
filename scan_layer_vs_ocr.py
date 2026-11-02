# -*- coding: utf-8 -*-
r"""scan_layer_vs_ocr.py -- for a scan that ships its own OCR layer: is that layer worse than a fresh,
independent OCR of the page images? Five pages decide the extraction route.

Why: a scan with its own OCR layer gives every text extractor (pymupdf, pdftotext, a layout-aware parser) the
same text to read, so their agreement says nothing about that layer -- a tie is guaranteed, and there is no
control group. To judge the layer you need a witness that reads the image itself: tesseract on 300-dpi renders.
The case behind it: an Internet Archive scan whose first page read by hand showed a whole family of misreadings
(`li` read as `h`, `rn` as `m`: "pohticians", "modem"); three extractors had tied on it. Re-OCR of the whole work
won 208 pages, tied 98, lost 3, and non-words fell from 2,886 to 1,877.

How it measures: English letter-words of length >= 3; line-end hyphenations joined first; a fragment that forms a
real word with its neighbour is NOT counted (a split word, which repair_wordsplits.py rejoins -- not a misreading);
words the spell checker does not know count as non-words. Proper names count too, and both arms pay that alike,
so what matters is the difference between the arms, not either number.

Decision: switch to re-OCR when the fresh OCR's non-word rate is lower by >= 1.0 percentage point AND >= 15%
relatively. Calibration (five pages each):
  - the scan above: layer 3.41% vs re-OCR 2.07% (-1.34 points, -39%) => switch (positive control)
  - a scan whose layer is known to be good: 1.45% vs 1.61% => keep (negative control)
  - 🔴 a first version did not discount split-word halves and told the good scan to switch (3.49% vs 1.66%):
    the archive's layer splits line-end hyphenations into two non-words, which a repair ladder rejoins.
Two calibration points only: when three scans in a row come out "keep", the threshold deserves a second look.

Usage:
  uv run --with pymupdf --with pyspellchecker python scan_layer_vs_ocr.py <file.pdf> [--pages 40,120,200]
         [--lang eng] [--tesseract PATH] [--tessdata DIR] [--show]
  ... python scan_layer_vs_ocr.py --self-test
Without --pages: the pages at 15/30/50/70/90% of the file (away from the cover and the index).
Read-only: renders and OCR output live in a temporary folder.
Needs: PyMuPDF, pyspellchecker, and the tesseract binary (on PATH, or --tesseract / $TESSERACT).
Exit codes: 0 = decided / 2 = too few words to decide / 3 = cannot run (no tesseract, OCR failed)
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TH_ABS, TH_REL = 1.0, 0.15
MIN_WORDS = 200


def make_stats():
    from spellchecker import SpellChecker
    sp = SpellChecker()

    def stats(s, show=None):
        s = re.sub(r"-\s*\n\s*", "", s)
        raw = re.findall(r"[A-Za-z]+", s)
        known = lambda w: not sp.unknown([w.lower()])
        drop = set()
        for i in range(len(raw) - 1):     # halves of a split word: the repair ladder's job, not a misreading
            if (not known(raw[i]) or not known(raw[i + 1])) and known(raw[i] + raw[i + 1]):
                drop.update((i, i + 1))
        toks = [w for i, w in enumerate(raw) if i not in drop and len(w) >= 3]
        unk = sp.unknown([w.lower() for w in toks])
        bad = [w for w in toks if w.lower() in unk]
        if show is not None:
            show.extend(bad)
        return len(toks), len(bad)
    return stats


def decide(layer, ocr):
    """layer, ocr = (words, non-words). Returns (verdict, layer %, ocr %): 'switch' / 'keep' / 'too few'."""
    if layer[0] < MIN_WORDS or ocr[0] < MIN_WORDS:
        return "too few", None, None
    rl, ro = layer[1] / layer[0] * 100, ocr[1] / ocr[0] * 100
    switch = (rl - ro) >= TH_ABS and (rl - ro) / max(rl, 1e-9) >= TH_REL
    return ("switch" if switch else "keep"), rl, ro


def find_tesseract(arg):
    for c in (arg, os.environ.get("TESSERACT"), shutil.which("tesseract"),
              r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        if c and Path(c).exists():
            return c
    return None


def compare(pdf, pages=None, lang="eng", tess=None, tessdata=None, show=False):
    import pymupdf
    stats = make_stats()
    tess = find_tesseract(tess)
    if not tess:
        print("⛔ tesseract not found (PATH, --tesseract or $TESSERACT): not checked is not passed")
        return 3, None
    doc = pymupdf.open(pdf)
    n = doc.page_count
    pages = pages or sorted({max(1, min(n, round(n * f))) for f in (0.15, 0.30, 0.50, 0.70, 0.90)})
    tot, shown = {"layer": [0, 0], "ocr": [0, 0]}, {"layer": [], "ocr": []}
    with tempfile.TemporaryDirectory() as td:
        for pg in pages:
            png = Path(td) / f"p{pg}.png"
            doc[pg - 1].get_pixmap(dpi=300).save(str(png))
            cmd = [tess, str(png), str(Path(td) / f"p{pg}"), "-l", lang] + (["--tessdata-dir", tessdata] if tessdata else [])
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"⛔ tesseract failed on PDF page {pg}: {r.stderr[-300:]}")
                return 3, None
            arms = {"layer": doc[pg - 1].get_text(), "ocr": (Path(td) / f"p{pg}.txt").read_text(encoding="utf-8")}
            row = []
            for k, s in arms.items():
                w, b = stats(s, shown[k] if show else None)
                tot[k][0] += w
                tot[k][1] += b
                row.append(f"{k} {b}/{w}")
            print(f"  PDF {pg}: " + "  ".join(row))
    doc.close()
    if show:
        for k, v in shown.items():
            print(f"  {k} non-words: {' '.join(v)}")
    verdict, rl, ro = decide(tot["layer"], tot["ocr"])
    if verdict == "too few":
        print(f"⚠ too few words (layer {tot['layer'][0]} / re-OCR {tot['ocr'][0]}): pick other pages; no verdict")
        return 2, verdict
    print(f"existing layer {rl:.2f}%   re-OCR {ro:.2f}%   difference {rl - ro:+.2f} points (relative {-(rl - ro) / max(rl, 1e-9):+.1%})")
    print("=> " + ("SWITCH: extract this work by OCR of the page images" if verdict == "switch"
                   else "KEEP: the existing layer is not worse") +
          f" (threshold: lower by >= {TH_ABS} point and >= {TH_REL:.0%}; pages {','.join(map(str, pages))}; lang {lang})")
    return 0, verdict


def _self_test():
    import io, contextlib
    checks = [
        ("positive control 3.41% vs 2.07% => switch", decide((1000, 34), (1000, 21))[0] == "switch"),
        ("negative control 1.45% vs 1.61% => keep", decide((1000, 15), (1000, 16))[0] == "keep"),
        ("lower by 1 point but only 10% relative => keep", decide((1000, 100), (1000, 90))[0] == "keep"),
        ("too few words => no verdict", decide((150, 9), (900, 3))[0] == "too few"),
    ]
    try:
        stats = make_stats()
        w, b = stats("The represen-\ntation of the politicians was atten tion to the modern world.")
        checks.append(("split-word halves are not counted as misreadings", b == 0))
        w, b = stats("The pohticians and the modem world.")
        checks.append(("li->h and rn->m are non-words", b == 1))     # 'modem' is a real word: the known blind spot
    except ImportError:
        print("skip  stats (pyspellchecker not installed)")
    try:
        import pymupdf
        tess = find_tesseract(None)
        if not tess:
            raise ImportError("tesseract")
        good = ("The politicians of the modern state claimed that public life would follow the will of the people. "
                "Critics replied that the public was itself produced by the institutions that claimed to represent it. ") * 6
        bad = good.replace("li", "h").replace("rn", "m")
        tmp = Path(tempfile.mkdtemp())
        src = pymupdf.open()
        p = src.new_page(width=420, height=600)
        p.insert_textbox(pymupdf.Rect(40, 40, 380, 560), good, fontsize=11)
        pix = p.get_pixmap(dpi=200)
        scan = pymupdf.open()
        for _ in range(2):                    # two pages: one page is below the 200-word floor
            q = scan.new_page(width=420, height=600)
            q.insert_image(q.rect, pixmap=pix)
            q.insert_textbox(pymupdf.Rect(40, 40, 380, 560), bad, fontsize=11, render_mode=3)   # invisible, wrong OCR layer
        scan.save(tmp / "scan.pdf")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code, verdict = compare(tmp / "scan.pdf", pages=[1, 2], tess=tess)
        checks.append(("scan with a bad OCR layer => switch (end to end, tesseract)", code == 0 and verdict == "switch"))
        shutil.rmtree(tmp, ignore_errors=True)
    except ImportError as e:
        print(f"skip  end to end ({e} not available)")
    bad_n = 0
    for name, ok in checks:
        bad_n += not ok
        print(("ok   " if ok else "FAIL ") + name)
    print(f"{len(checks) - bad_n} of {len(checks)} as expected")
    return 1 if bad_n else 0


def main():
    if sys.argv[1:] == ["--self-test"]:
        return _self_test()
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", help="PDF pages, comma-separated (1-based)")
    ap.add_argument("--lang", default="eng")
    ap.add_argument("--tesseract")
    ap.add_argument("--tessdata")
    ap.add_argument("--show", action="store_true", help="list both arms' non-words (read them: OCR errors or names?)")
    a = ap.parse_args()
    pages = [int(x) for x in a.pages.split(",")] if a.pages else None
    code, _ = compare(a.pdf, pages, a.lang, a.tesseract, a.tessdata, a.show)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
