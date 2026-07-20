# -*- coding: utf-8 -*-
"""pdf_risk_probe.py — 30-second intake probe for PDF text-layer risk.

Run this BEFORE extracting a PDF into your corpus. A census of ~530 real PDFs
showed that text-layer damage is not a property of *what kind of book* a file
is — it is a property of *how the PDF's text layer was generated*. The same
typesetting software produced both the cleanest and the most fragmented files
in that census. A 30-second probe at intake beats a corpus-wide audit later.

Six verdicts:
  1. broken ToUnicode map   — extraction yields glyph IDs, not readable text
  2. per-character layout   — "D e m o c r a c y": word boundaries unrecoverable
  3. legacy OCR             — ClearScan / Paper Capture / ABBYY / hidden layer
  4. image-text reflow      — report-style layouts; reading order is geometric
  5. pure image             — no usable text layer at all
  6. healthy born-digital   — extract normally

Exit code 0 = healthy (verdict 6); 1 = at-risk (verdicts 1-5); 2 = usage.

Usage:
  uv run --with pymupdf python pdf_risk_probe.py "<path-to-pdf>"

Ported from the production tooling of the alexandria librarian role
(https://github.com/kengo006/alexandria). Battle log: LESSONS.md.
"""
import re
import sys
from collections import Counter

import fitz

# Function-word tables for a cheap language guess (affects only which
# fragmentation threshold is *reported* — not any repair decision).
EN = set("the of and to in that is was for as with it not on be by this are from at or an".split())
FR = set("le la les des une dans qui pour pas sur est plus par ce cette au aux du ne se".split())
DE = set("der die das und ist nicht von mit dem den des ein eine im für auf als".split())

OCR_FLAGS = ("clearscan", "paper capture", "abbyy", "finereader", "tesseract", "ocrmypdf")


def probe(path):
    doc = fitz.open(path)
    md = doc.metadata or {}
    prod = ((md.get("producer") or "") + " | " + (md.get("creator") or "")).strip(" |")
    n = doc.page_count
    idx = list(range(0, n, max(1, n // 20)))[:20]          # 20-point sample

    text = "".join(doc[i].get_text("text") for i in idx)
    imgpages = sum(1 for i in idx if doc[i].get_images())
    glyphless = any("GlyphLessFont" in str(f[3]) for i in idx[:5]
                    for f in doc.get_page_fonts(doc[i].number))
    doc.close()

    per_page = len(text) / max(len(idx), 1)
    ctrl = sum(1 for ch in text[:100000] if ord(ch) < 32 and ch not in "\n\r\t\f")
    ctrl_ratio = ctrl / max(min(len(text), 100000), 1) * 100

    toks = re.findall(r"[A-Za-zÀ-ÿ]+", text)
    low = [w.lower() for w in toks]
    c = Counter(low)
    lang = "en"
    if toks:
        en = sum(c[x] for x in EN)
        fr = sum(c[x] for x in FR)
        de = sum(c[x] for x in DE)
        lang = ("fr" if fr >= max(en, de) else "de" if de >= max(en, fr) else "en")
    single = (sum(1 for w in toks if len(w) == 1) / len(toks) * 100) if toks else 0.0

    findings = []
    # 5: pure image
    if per_page < 200:
        findings.append(("5: pure image (no usable text layer)",
                         "run image-side OCR (ocrmypdf / tesseract / RapidOCR); "
                         "page anchors must come from the OCR pass itself"))
    else:
        # 1: broken ToUnicode
        if ctrl_ratio > 0.5:
            findings.append(("1: broken ToUnicode map (extraction yields glyph IDs; "
                             "the page LOOKS fine but the text layer is unreadable)",
                             "do NOT extract directly — go image-side OCR, or find another "
                             "copy of the PDF; re-extracting this one can only yield garbage"))
        # 2: per-character layout
        if single > 30:
            findings.append(("2: per-character positioning ('D e m o c r a c y'; no word boundaries)",
                             "do NOT extract directly — word boundaries are unrecoverable from "
                             "this text layer; go image-side OCR"))
        # 3: legacy OCR
        if any(f in prod.lower() for f in OCR_FLAGS) or glyphless:
            findings.append(("3: legacy OCR product (ClearScan / Paper Capture / ABBYY / hidden layer)",
                             "extract, then ALWAYS run the fragmentation gate (corpus_health.py "
                             "gate 5); above threshold -> re-OCR. GlyphLessFont = hidden OCR "
                             "layer; only DUAL layers are dangerous (see corpus_health gate 3)"))
        # 4: image-text reflow — reported only when 1-3 are absent (scanned files
        # have images on every page anyway, so this would false-positive on them)
        if not findings and imgpages >= len(idx) * 0.7 and per_page > 800:
            findings.append(("4: image-text reflow (report-style layout; reading order is "
                             "geometric, not logical)",
                             "use a layout-model extractor (e.g. docling), then spot-check "
                             "2-3 pages for reading-order coherence"))

    # Post-extraction single-letter-rate thresholds by language. French runs a
    # high baseline because of l'/d' elisions. Calibrated on one ~530-text
    # Western-language humanities corpus — read your own distribution first.
    thr = {"en": "en: >5.5% investigate, >8% fail",
           "fr": "fr: >11% investigate, >13% fail (l'/d' elisions raise the baseline)",
           "de": "de: >6% investigate, >9% fail"}[lang]

    print(f"file    : {path}")
    print(f"pages   : {n} | sampled {len(idx)} | {per_page:,.0f} chars/page")
    print(f"producer: {prod[:90] or '(none)'}")
    print(f"language: {lang} | single-letter rate {single:.2f}% | control chars {ctrl_ratio:.2f}%")
    if not findings:
        print("\nverdict : 6: healthy born-digital -> extract normally")
        print(f"post-extraction gate: single-letter thresholds ({thr})")
        return 0
    print(f"\nverdict : {'; '.join(f[0] for f in findings)}")
    for name, act in findings:
        print(f"  - {name}\n    action: {act}")
    print(f"post-extraction gate: single-letter thresholds ({thr})")
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(probe(sys.argv[1]))
