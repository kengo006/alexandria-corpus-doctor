# Changelog

Versioning note: this project starts at v0.1, matching the convention of its
sibling repos — early versions that work but have not yet survived outside
their home corpus.

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
