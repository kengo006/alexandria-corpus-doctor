# alexandria-corpus-doctor

**Diagnose and repair the text layer of a PDF-derived corpus — because your grep can lie.**
Companion tooling for [alexandria](https://github.com/kengo006/alexandria), a role-based protocol for running a personal research library with AI agents.

A text file extracted from a PDF can look complete and still be unsearchable:
words split apart by kerning (`polit ical`), sentences glued into single tokens
(`Researchisneededto`), accents systematically misread (`Collège` → `Collége`),
pages that cannot be cited because no anchor survived extraction. Nothing
crashes. The search just returns nothing — and "no results" quietly becomes
"the source doesn't say that." For any workflow where an agent's *negative*
claims matter (citation checking, literature review, RAG), this is the failure
mode that hurts most, because nobody suspects the text layer.

This repo is the toolkit that came out of debugging exactly that, across a real
corpus of ~530 scholarly texts: an intake probe, a six-gate health check, and
statistical repair tools that fix the text using the corpus's own word
frequencies.

## How this differs from better parsers

The mainstream answer to bad extractions is a better parser (docling, MinerU,
olmOCR, marker). We tested that road and it did not reach: re-extracting our
damaged files with a modern layout-model parser produced nearly identical
output — because the damage (kerning micro-adjustments, per-character
positioning) lives **in the PDF text layer itself**, and a faithful parser
faithfully reproduces it. Re-OCR from images swaps one disease for another
(word gluing went up 20–80× on born-digital files).

What worked is corpus-statistical repair: **use the library's own word
frequencies to fix the library's own files.** The core criterion is
*morphological possibility*, not frequency ratio — `t hose` merges not because
"those" is common, but because "t" is not a word, so "t hose" cannot be a legal
two-word sequence. That is what lets it repair `la rge` and `p eople`, the
cases where the prefix is itself a common word and every ratio-based rule
fails. No models, no training, no API calls; plain Python, and the only
optional dependency is PyMuPDF, used only by `pdf_risk_probe.py`,
`fix_pipeline.py` and the `--pdf` gate of `corpus_health.py` (`pip install
pymupdf`, or prefix the command with `uv run --with pymupdf`). Nothing in the
Quickstart needs it.

## The tools

| tool | job |
|---|---|
| `pdf_risk_probe.py` | 30-second **intake probe**: classify a PDF into six risk types *before* extraction (broken ToUnicode, per-char layout, legacy OCR, reflow, pure image, healthy) |
| `corpus_health.py` | **six-gate health check** over the whole corpus: phrase density, accent misreads, hidden OCR layers, page anchors, splitpair rate, glue rate — each gate fires only on true damage |
| `dehyphenate.py` | join end-of-line hyphenations, only when the joined form is corpus-attested (no fabricated words) |
| `repair_wordsplits.py` | repair words split apart (`polit ical`, `p eople`) via the morphological-possibility criterion |
| `unglue_words.py` | split glued spans (`proponentsoftheextendedmind`) via DP segmentation over a clean-file dictionary |
| `fix_pipeline.py` | escalation ladder: cheap re-extraction + repair first, *measured*; only files that still fail get queued for re-OCR |
| `tokenwalk.py` | the **single implementation** of adjacent-token joining — and a runnable counter-example (`join_pairs_resub_BROKEN`) showing what `re.sub` does instead |
| `ligature_and_encoding.py` | ligature expansion, line-end dehyphenation, and font-encoding garble detection — **adapted from four upstream parsers** (docling, Kreuzberg, marker, RAGFlow) with attribution and re-measured thresholds — see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) |
| `add_page_markers.py` | recover printed page anchors from running heads swept into OCR text (LIS outlier removal, four gates, no fuzzy alignment) |

All repair tools are dry-run by default, back up before writing, and follow one
discipline: **when unsure, do nothing.** A false repair is worse than a missed
one, and a false page anchor is worse than no anchor.

**The criterion that governs all of them: findability, not correctness.** The
text layer *locates*; the PDF is the authority. So a defect matters when it
stops a content word from being found, and not otherwise — page numbers,
running heads, footnote markers and stop words are **decided not to fix**,
which is a different state from *not yet fixed*. See LESSONS #13; this is the
one judgement that changes what the whole ladder is for.

## Quickstart (2 minutes, synthetic corpus included)

```bash
git clone https://github.com/kengo006/alexandria-corpus-doctor
cd alexandria-corpus-doctor

# 1) diagnose the bundled demo corpus - two files are damaged, each fires its own gate
python corpus_health.py --corpus examples/corpus --no-pdf
#    -> gate 5 RED on wordsplit-damaged.txt (10.3 permille)
#    -> gate 6 RED on glued-damaged.txt    (6.4 permille)

# 2) watch the repairs (dry-run prints every proposed merge/split)
python repair_wordsplits.py --corpus examples/corpus
python unglue_words.py     --corpus examples/corpus

# 3) apply and re-check
python repair_wordsplits.py --corpus examples/corpus --apply
python unglue_words.py     --corpus examples/corpus --apply
python corpus_health.py    --corpus examples/corpus --no-pdf
```

The demo corpus is synthetic (an original passage with damage injected by
`examples/make_synthetic.py`, deterministic seed). Note that the repair tools
will *warn you* on it: a three-file dictionary is a toy. Diagnosis is valid
anywhere; the repair criterion earns its statistical footing on a real corpus.

Step 3 rewrites the two damaged demo files in place and leaves a `_backup/`
folder where you ran it. To run the Quickstart again, restore the damaged files
with `python examples/make_synthetic.py` (fixed seed, byte-identical output);
`_backup/` can be deleted.

## Your own corpus

The input is a folder tree of `.txt` files, one per source PDF (the same
text-layer convention alexandria uses; page boundaries as `\f` or
`===== page N =====`). Files and directories starting with `_` are ignored.

```bash
set CORPUS_ROOT=C:\path\to\your\text-layer    # or export, or pass --corpus

python corpus_health.py --pdf C:\path\to\your\pdfs     # full check incl. gate 3
python fix_pipeline.py  --pdf C:\path\to\your\pdfs     # ladder over flagged files
```

**Calibration discipline:** the absolute floors (splitpair ≥ 5‰, glue ≥ 3‰,
single-letter thresholds per language) were calibrated on one ~530-text
Western-language humanities corpus (reference distribution: splitpair median
0.20‰, P95 2.91‰). Run the health check once, *read your own distribution*,
and only then decide what to trust. Gate 1 (phrase density) is
median-relative and adapts to your corpus automatically.

## Scope, honestly

- **Latin-script corpora** (English/French/German function-word tables ship;
  the criteria generalize to other Latin-script languages, unverified). CJK
  files are detected and skipped, not processed.
- Dictionaries are **learned from your corpus at runtime** — nothing
  pre-trained ships in this repo, and files never leave your machine.
- The repair tools change files. They back up first, dry-run by default, and
  print every change — but on your corpus, **read a repaired page before you
  trust a green metric.** That rule is the single most expensive lesson in
  [LESSONS.md](LESSONS.md).

## The battle log

[LESSONS.md](LESSONS.md) documents the twenty mistakes that shaped these
tools — circular dictionary contamination (the defect writes itself into the
lexicon used to detect it), the `re.sub` adjacent-pair bug, why "must halve
the metric" is mathematically impossible for mid-band files, and the general
laws they add up to. If you build corpus tooling of your own, start there.

## Part of the alexandria family

- **[alexandria](https://github.com/kengo006/alexandria)** — the protocol: role
  charters, verification gates, and evidence discipline for running a personal
  research library with AI agents. This repo is its corpus-quality layer:
  alexandria's librarian role runs these checks at intake and before release.
- **[alexandria-semantic-recall](https://github.com/kengo006/alexandria-semantic-recall)** —
  the retrieval layer: local, cross-lingual semantic recall over the same text
  layer (recall-only by contract; quotes are always verified against the PDF).

## License

MIT

Release history, and the reasoning behind each change, is in
[CHANGELOG.md](CHANGELOG.md).
