# Changelog

Versioning note: this project starts at v0.1, matching the convention of its
sibling repos — early versions that work but have not yet survived outside
their home corpus.

## v0.2 — 2026-07-31

**Two new tools, seven new lessons, and one judgement that reframes the rest.**

- **New** `tokenwalk.py` — the single implementation of adjacent-token joining,
  with `join_pairs_resub_BROKEN` kept **executable** beside it. A rule with no
  runnable counter-example teaches "don't do X" without showing what X does;
  running the module prints the walk converging and `re.sub` returning the
  input unchanged.
- **New** `ligature_and_encoding.py` — ligature expansion, line-end
  dehyphenation, and font-encoding garble detection, **adapted from four
  upstream parsers with attribution** (docling MIT, Kreuzberg MIT, marker
  Apache-2.0, RAGFlow Apache-2.0; licenses verified against each project's
  LICENSE file). Two deviations are ours and are documented at the functions:
  the hyphen must be **attached** to the preceding word (upstream's guard reads
  word tokens, so a line ending in a spaced hyphen joins across and invents a
  word), and garble detection returns a **rate with its denominator** rather
  than a boolean. Thresholds were re-measured rather than carried over:
  upstream flags at 0.5 — 500 permille — while the worst file in this corpus
  sits at 2.458 permille, two hundred times below it. A boolean at the upstream
  threshold reports every one of them as clean.
- **LESSONS #13–#19** — repairing what nobody searches for (the P0/P1/P2
  criterion); eight domain gaps that are one disease; a repair whose wrong
  output is a real word; "new" as a judgement relative to a list; mechanism-side
  versus symptom-side scanning; the self-referential stopping condition; and a
  test runner that skips but reports passing.
- **README**: the governing criterion is stated up front — **findability, not
  correctness**.

## v0.1 — 2026-07-20

First public release. The toolkit as it emerged from a three-day remediation
campaign on a ~530-text scholarly corpus (final state: 519/530 files healthy
and searchable, 0 unrepaired defects, 11 files honestly registered as limited).

- `pdf_risk_probe.py` — six-type intake probe (each type validated against a
  real specimen during the campaign)
- `corpus_health.py` — six-gate corpus health check; every gate built from a
  damage type that had slipped past naive checks
- `dehyphenate.py`, `repair_wordsplits.py`, `unglue_words.py` — the three
  repair tools, one per damage direction (line-break hyphens / extra spaces /
  missing spaces), all corpus-lexicon-driven, dry-run by default
- `fix_pipeline.py` — measure-then-decide escalation ladder (cheap
  re-extraction first, re-OCR queue only on measured failure)
- `add_page_markers.py` — OCR-free page-anchor recovery via running heads +
  LIS, generalized here to a `--file`/`--heads` CLI (the upstream original was
  hard-wired to one book)
- `examples/` — deterministic synthetic demo corpus; two damaged files that
  each fire exactly their own health gate
- `LESSONS.md` — the twelve failures and three laws behind the design

Differences from the upstream production scripts: paths are CLI arguments
instead of constants, all documentation is in English, thresholds are
annotated with their calibration provenance, and one corpus-specific
skip-list became the generic `--exclude` option. Repair criteria are ported
unchanged.
