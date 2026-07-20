# -*- coding: utf-8 -*-
"""add_page_markers.py — recover printed page anchors from running heads (OCR-free).

Use case: the source PDF is pure image (no text layer), your existing .txt came
from an earlier OCR pass and reads fine — but it has no page anchors, so the
file cannot be cited by page.

Method (v3; the v2 OCR-alignment approach is retired): if the OCR pass swept
the page headers into the text flow, the printed page numbers are ALREADY in
your text, sitting next to the running heads. So:
  1. scan for <number><running-head> and <running-head><number> patterns
  2. drop the table-of-contents region (first run of 6 ascending hits, span <= 12)
  3. keep the LONGEST INCREASING SUBSEQUENCE — exact string matching plus LIS
     outlier removal, no fuzzy alignment, no cascade risk
     (v2 aligned per-page OCR fingerprints with a sliding search window; one
     early mismatch cascaded and 350 pages matched only 78 - retired)
  4. write `===== page N =====` markers only if ALL four gates pass:
       page numbers strictly increasing | character positions increasing |
       position-vs-page correlation > 0.999 | max gap <= 6 pages

BETTER NO ANCHOR THAN A FALSE ANCHOR: chapter-opening pages carry no running
head by typographic convention — they are simply not marked. On our validation
book this recovered 195 printed pages (67% coverage, max gap 4, correlation
0.99996) in seconds.

Usage:
  python add_page_markers.py --file <path.txt> --heads <heads.txt> [--apply]
                             [--backup <dir>]
  <heads.txt> = one running head per line (the chapter titles as printed in
  the page headers - copy them from the book's table of contents).

Ported from the production tooling of the alexandria librarian role
(https://github.com/kengo006/alexandria). Battle log: LESSONS.md.
"""
import argparse
import bisect
import os
import re
import shutil
import statistics


def extract(s, heads):
    raw = []
    for h in heads:
        hp = re.escape(h)
        for m in re.finditer(rf"\b(\d{{1,3}})\s+{hp}", s):
            raw.append((m.start(), int(m.group(1))))
        for m in re.finditer(rf"{hp}\s+(\d{{1,3}})\b", s):
            raw.append((m.start(), int(m.group(1))))
    raw.sort()
    # Drop the front table-of-contents region: body starts at the first run of
    # 6 consecutive ascending hits whose span is <= 12 pages.
    start = 0
    for i in range(len(raw) - 5):
        seg = [r[1] for r in raw[i:i + 6]]
        if all(a < b for a, b in zip(seg, seg[1:])) and seg[-1] - seg[0] <= 12:
            start = i
            break
    body = raw[start:]
    if not body:
        return raw, body, []
    # Longest increasing subsequence: drops ToC stragglers and misreads.
    vals = [r[1] for r in body]
    tails, idx, prev = [], [], [-1] * len(vals)
    for i, v in enumerate(vals):
        j = bisect.bisect_left(tails, v)
        if j == len(tails):
            tails.append(v); idx.append(i)
        else:
            tails[j] = v; idx[j] = i
        prev[i] = idx[j - 1] if j else -1
    seq, k = [], idx[len(tails) - 1]
    while k != -1:
        seq.append(k); k = prev[k]
    seq.reverse()
    return raw, body, [body[i] for i in seq]


def main():
    ap = argparse.ArgumentParser(description="Recover printed page anchors from running heads")
    ap.add_argument("--file", required=True, help="the .txt file to anchor")
    ap.add_argument("--heads", required=True,
                    help="text file with one running head per line")
    ap.add_argument("--apply", action="store_true", help="write markers (default: dry-run)")
    ap.add_argument("--backup", default=os.path.join("_backup", "add_page_markers"))
    args = ap.parse_args()

    heads = [ln.strip() for ln in open(args.heads, encoding="utf-8") if ln.strip()]
    if not heads:
        ap.error(f"no running heads found in {args.heads}")

    raw_txt = open(args.file, "rb").read().decode("utf-8", "replace")
    s = raw_txt.replace("\r\n", "\n").replace("\r", "\n")
    raw, body, kept = extract(s, heads)
    if len(kept) < 8:
        print(f"only {len(kept)} anchor candidates survived - the OCR pass probably did not")
        print("sweep the page headers into the text flow. This method does not apply; stop.")
        return 1
    pages = [r[1] for r in kept]

    mono_p = all(a < c for a, c in zip(pages, pages[1:]))
    mono_c = all(a[0] < c[0] for a, c in zip(kept, kept[1:]))
    xs = [r[0] for r in kept]
    mx, mp = statistics.mean(xs), statistics.mean(pages)
    num = sum((x - mx) * (q - mp) for x, q in zip(xs, pages))
    den = (sum((x - mx) ** 2 for x in xs) * sum((q - mp) ** 2 for q in pages)) ** .5
    corr = num / den if den else 0.0
    gaps = [c - a for a, c in zip(pages, pages[1:])] or [0]

    print(f"### {os.path.basename(args.file)}")
    print(f"  raw hits {len(raw)} -> ToC dropped {len(raw)-len(body)} -> LIS kept {len(kept)}")
    print(f"  pages {min(pages)}-{max(pages)} | coverage {len(kept)}/{max(pages)-min(pages)+1}"
          f" = {len(kept)/(max(pages)-min(pages)+1)*100:.1f}%")
    print(f"  gate 1 pages strictly increasing    : {'PASS' if mono_p else 'FAIL'}")
    print(f"  gate 2 char positions increasing    : {'PASS' if mono_c else 'FAIL'}")
    print(f"  gate 3 position/page correlation    : {corr:.5f} {'PASS' if corr > 0.999 else 'FAIL'}")
    print(f"  gate 4 max gap                      : {max(gaps)} pages {'PASS' if max(gaps) <= 6 else 'FAIL'}")

    if not args.apply:
        print("\n[dry-run] nothing written. Add --apply to write markers.")
        return 0
    if not (mono_p and mono_c and corr > 0.999 and max(gaps) <= 6):
        print("\nFAIL: gates not passed -> refusing to write. Better no anchor than a false one.")
        return 1

    os.makedirs(args.backup, exist_ok=True)
    shutil.copy2(args.file, os.path.join(args.backup, os.path.basename(args.file)))
    # kept[] positions index the NORMALIZED string, so insert into that and
    # write back with uniform \n (mixing them against original CRLF offsets
    # would shift every anchor).
    out = s
    for pos, folio in sorted(kept, key=lambda x: -x[0]):
        out = out[:pos] + f"\n===== page {folio} =====\n" + out[pos:]
    open(args.file, "w", encoding="utf-8", newline="").write(out)
    print(f"\n  wrote {len(kept)} page anchors (backup in {args.backup})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
