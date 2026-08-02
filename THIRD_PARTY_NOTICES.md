# Third-party notices

`alexandria-corpus-doctor` is released under the MIT License (see `LICENSE`).

One file in this repository, **`ligature_and_encoding.py`**, is **adapted from
four upstream open-source projects**. Nothing else here derives from third-party
code. This file records the provenance, the licences, and — as Apache-2.0 §4(b)
requires — that the adapted portions carry changes.

Licences were verified on **2026-07-31** by reading each project's `LICENSE`
file directly. Licences change; re-verify before relying on this page.

---

## docling — MIT License

- Project: https://github.com/docling-project/docling
- Source consulted: `docling/models/stages/page_assemble/page_assemble_model.py`
- Adapted: `_LIGATURE_MAP` and the ligature-plus-spurious-space pattern
  (`_LIGATURE_RE`); the alphanumeric guard in `sanitize_text` that decides when
  an end-of-line hyphen may be joined.
- Changes: the hyphen must additionally be **attached** to the preceding word
  (upstream inspects word tokens, so a line ending in a spaced hyphen joins
  across and produces a word absent from the source); joining across page
  boundaries is made optional.

## Kreuzberg — MIT License

- Project: https://github.com/Goldziher/kreuzberg
- Source consulted: `expand_ligatures_with_sp`
- Relationship: implements the same space-absorbing ligature behaviour adopted
  above. Recorded because the behaviour was cross-checked against both
  projects, not because a second copy was taken.

## marker — Apache License 2.0

- Project: https://github.com/datalab-to/marker
- Adapted: the layered treatment of dehyphenation (within a text span, between
  lines, and across a page boundary as a continuation candidate).
- Changes: the cross-page layer is **off by default** for page-marked scholarly
  text, where the material immediately after a page break is frequently a
  running head or footnote apparatus rather than a word continuation.

## RAGFlow — Apache License 2.0

- Project: https://github.com/infiniflow/ragflow
- Source consulted: `deepdoc/parser/pdf_parser.py` (`_is_garbled_char`,
  `_is_garbled_text`)
- Adapted: the codepoint ranges that identify characters an extractor could not
  map (private-use areas, the replacement character, C0/C1 controls,
  unassigned and surrogate categories), and the CID-placeholder pattern.
- Changes: the text-level function returns a **rate together with its
  denominator** instead of a boolean against a 0.5 threshold. Upstream's
  question is "is this page unusable"; ours is "did a class of characters
  silently vanish". Measured on a Western-language humanities corpus of 552
  text-layer files, the worst file scored 2.458 permille — two hundred times
  below the upstream flag, so a boolean at that threshold reports every
  affected file as clean.

---

## On the Apache-2.0 obligations

For the two Apache-2.0 sources, this file together with the `ATTRIBUTION` and
per-function `DEVIATIONS` notes inside `ligature_and_encoding.py` is intended
to satisfy §4: attribution is retained, and modified portions carry prominent
notices stating that they were changed and how. No upstream `NOTICE` file
content is reproduced here because none was present in the consulted sources at
the verification date.

If you are redistributing this repository and need stronger assurance for your
own compliance review, take the upstream licences directly from the project
URLs above — they are authoritative; this page is a convenience.
