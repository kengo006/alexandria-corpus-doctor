# -*- coding: utf-8 -*-
"""fix_pipeline.py — escalation ladder: cheap re-extraction first, re-OCR only if it fails.

PRIMARY METRIC = splitpair rate (adjacent token pairs that join into a
high-frequency word, per 1k tokens): a direct measure of fragmentation,
immune to the things that fool single-letter-rate (abbreviations,
bibliographies, interview markers like "M.F.").

TRUST MEASUREMENT, NOT PREDICTION: for every flagged file, first try the cheap
path (PyMuPDF re-extraction + lexicon-driven repair pass, minutes); if the
measured result clears the bar, take it; if not, queue the file for image-side
re-OCR — with a tool of your choice. (In our runs, RapidOCR worked well on
scanned mid-size books; born-digital files consistently got WORSE from re-OCR
— glue rate up 20-80x — and 180+ page books hit negative cost-benefit. Probe
first with pdf_risk_probe.py; born-digital files should skip re-OCR entirely.)

Acceptance = below the absolute floor AND improved AND word count preserved
(>= 85%) AND "the" count preserved (>= 90%). Do NOT add a "must halve" rule:
for files in the 8-12 permille band that demands reaching coincidence baseline
(~3.4), which is mathematically impossible — we watched it wrongly send an
8.2 -> 5.3 improvement to re-OCR before removing it.

Usage:
  uv run --with pymupdf python fix_pipeline.py --corpus <txt-root> --pdf <pdf-root>
      [--apply] [--limit N] [--queue <out.json>] [--backup <dir>]

The corpus and PDF trees must mirror each other: <corpus>/x/y.txt <-> <pdf>/x/y.pdf.
CORPUS_ROOT env var is honored when --corpus is omitted.
Needs PyMuPDF (the uv command above installs it on the fly); without it the run
stops with exit code 2 before touching anything.

Ported from the production tooling of the alexandria librarian role
(https://github.com/kengo006/alexandria). Battle log: LESSONS.md.
"""
import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter


def _fitz():
    """Import PyMuPDF only when it is needed, so that `--help` works without it
    and a missing install stops the run before the slow lexicon build."""
    try:
        import pymupdf as fitz          # the module's current name
    except ImportError:
        try:
            import fitz                 # PyMuPDF before the rename
        except ImportError:
            sys.stderr.write("fix_pipeline.py needs PyMuPDF to re-extract PDFs. Install it with\n"
                             "    pip install pymupdf\n"
                             "or run it without installing:\n"
                             "    uv run --with pymupdf python fix_pipeline.py --corpus <txt-root> --pdf <pdf-root>\n"
                             "(Text-only repair of split words needs no PDFs: repair_wordsplits.py.)\n")
            sys.exit(2)
    return fitz


THR = 5.0        # absolute floor, calibrated on one ~530-text corpus
                 # (median 0.20 permille, P95 2.91) - read your own distribution first

RE_HYPH = re.compile(r"([A-Za-z]{2,})-\n([a-z]{2,})")
RE_SOFT = re.compile(r"([A-Za-z]{2,})\n([a-z]{2,})")
RE_SPACE = re.compile(r"\b([A-Za-z]{2,})[ ]([a-z]{2,})\b")
RE_RUN = re.compile(r"[ \t]{2,}")


def walk_txt(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith("_")]
        for fn in fns:
            if fn.lower().endswith(".txt") and not fn.startswith("_"):
                yield os.path.join(dp, fn)


def rd(p):
    return open(p, "rb").read().decode("utf-8", "replace").replace("\r\n", "\n")


def splitpair(s, freq):
    """v2 (bought with 56 false positives): joined word must be >= 5 letters,
    else letter-spaced headings ("C H A P T E R") trigger via ch/ha/ap pairs
    that heading accumulation had promoted to "common words" in the lexicon."""
    toks = re.findall(r"[A-Za-z]+", s)
    if len(toks) < 1500:
        return None, len(toks)
    n = 0
    for a, b in zip(toks, toks[1:]):
        j = (a + b).lower()
        if len(j) >= 5 and freq[j] >= 30 and freq[j] > 3 * max(freq[a.lower()], freq[b.lower()]):
            n += 1
    return n / len(toks) * 1000, len(toks)


def pipeline(s, freq):
    """Lexicon-driven repair pass over a fresh extraction: line-end hyphens,
    soft line breaks, double spaces, in-line splits. Conservative thresholds -
    every substitution must be corpus-attested."""
    hyphfreq = Counter(w.lower() for w in re.findall(r"\b[A-Za-z]{2,}-[A-Za-z]{2,}\b", s))

    def rep_hyph(m):
        a, b = m.group(1), m.group(2)
        pm, ph = freq[(a + b).lower()], hyphfreq[f"{a.lower()}-{b}"]
        if pm >= 50 and pm > ph * 3:
            return a + b
        if ph >= 3 and ph * 3 > pm:
            return a + "-" + b
        return m.group(0)

    def rep_soft(m):
        a, b = m.group(1), m.group(2)
        j = (a + b).lower()
        return a + b if (freq[j] >= 30 and freq[j] > freq[b] * 8) else m.group(0)

    def rep_space(m):
        a, b = m.group(1), m.group(2)
        j = (a + b).lower()
        return a + b if (freq[j] >= 50 and freq[j] > freq[b] * 20
                         and freq[j] > freq[a.lower()] * 3) else m.group(0)

    prev = None
    for _ in range(4):
        if s == prev:
            break
        prev = s
        s = RE_HYPH.sub(rep_hyph, s)
        s = RE_SOFT.sub(rep_soft, s)
        s = RE_RUN.sub(" ", s)
        s = RE_SPACE.sub(rep_space, s)
    return s


def main():
    ap = argparse.ArgumentParser(description="Escalation ladder for fragmented files")
    ap.add_argument("--corpus", default=os.environ.get("CORPUS_ROOT"))
    ap.add_argument("--pdf", required=True, help="root of the source PDFs (mirror tree)")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--limit", type=int, default=0, help="process at most N files")
    ap.add_argument("--queue", default="_reocr_queue.json",
                    help="where to write the re-OCR queue (with --apply)")
    ap.add_argument("--backup", default=os.path.join("_backup", "fix_pipeline"))
    args = ap.parse_args()
    if not args.corpus or not os.path.isdir(args.corpus):
        ap.error("--corpus <dir> is required (or set CORPUS_ROOT)")
    fitz = _fitz()          # checked here: before the slow lexicon build, not mid-run

    print("building corpus lexicon...", flush=True)
    freq = Counter()
    allfiles = list(walk_txt(args.corpus))
    for p in allfiles:
        freq.update(w.lower() for w in re.findall(r"[A-Za-z]{2,}", rd(p)))
    print(f"  {len(allfiles)} files | {len(freq):,} word types", flush=True)

    # queue: every file at or above the floor
    targets = []
    for p in allfiles:
        sp, w = splitpair(rd(p), freq)
        if sp is not None and sp >= THR:
            targets.append((sp, p, w))
    targets.sort(reverse=True)
    if args.limit:
        targets = targets[:args.limit]
    print(f"queue (splitpair >= {THR} permille): {len(targets)} files "
          f"({'APPLY' if args.apply else 'dry-run'})\n", flush=True)

    done, queue, nopdf = [], [], []
    for k, (sp0, p, w0) in enumerate(targets):
        rel = os.path.relpath(p, args.corpus)
        cjk = bool(re.search(r"[一-鿿]", rd(p)[:3000]))
        pdf = os.path.join(args.pdf, rel[:-4] + ".pdf")
        if cjk or not os.path.exists(pdf):
            (queue if os.path.exists(pdf) else nopdf).append(
                dict(rel=rel, sp=round(sp0, 2), why=("CJK file" if cjk else "no PDF")))
            print(f"[{k+1:>2}] {sp0:6.2f}  {'CJK -> re-OCR with CJK model' if cjk else 'WARN no PDF':<28} "
                  f"{os.path.basename(rel)[:44]}", flush=True)
            continue
        old = rd(p)
        othe = len(re.findall(r"(?i)\bthe\b", old))
        doc = fitz.open(pdf)
        fresh = "".join(f"\n===== page {i+1} =====\n{doc[i].get_text('text')}"
                        for i in range(doc.page_count))
        doc.close()
        fixed = pipeline(fresh.replace("\r\n", "\n"), freq)
        sp1, w1 = splitpair(fixed, freq)
        nthe = len(re.findall(r"(?i)\bthe\b", fixed))
        ok = (sp1 is not None and sp1 < THR and sp1 < sp0
              and w1 >= w0 * 0.85 and nthe >= othe * 0.9)
        print(f"[{k+1:>2}] {sp0:6.2f} -> {(sp1 if sp1 is not None else 99):6.2f}  "
              f"words {w0:>7,} -> {w1:>7,}  {'PASS: re-extracted' if ok else '-> re-OCR':<18} "
              f"{os.path.basename(rel)[:40]}", flush=True)
        if ok:
            done.append(dict(rel=rel, sp0=round(sp0, 2), sp1=round(sp1, 2)))
            if args.apply:
                b = os.path.join(args.backup, rel)
                os.makedirs(os.path.dirname(b), exist_ok=True)
                if not os.path.exists(b):
                    shutil.copy2(p, b)
                open(p, "w", encoding="utf-8", newline="").write(fixed)
        else:
            queue.append(dict(rel=rel, sp=round(sp0, 2),
                              why=f"still {sp1 if sp1 is not None else '?'} after re-extraction"))

    print("\n===== result =====")
    print(f"  solved by re-extraction: {len(done)}   -> re-OCR: {len(queue)}   no PDF: {len(nopdf)}")
    if args.apply:
        json.dump(dict(reocr=queue, nopdf=nopdf, done=done),
                  open(args.queue, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  queue written to {args.queue} | backups in {args.backup}")


if __name__ == "__main__":
    main()
