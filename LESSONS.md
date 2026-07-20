# LESSONS — the battle log

These tools were not designed; they were *survived into*. Over a three-day
remediation campaign on a ~530-text corpus, every naive version failed in an
instructive way. The twelve failures below are preserved in the tools as
guards and comments; this file is the narrative index. Names of specific
books and files are omitted throughout — the shapes of the failures are what
generalize.

## The twelve

**1. Single-letter rate as the primary damage metric.**
It flagged interview transcripts and bibliographies (initials like "M.F." and
"Q" are *supposed* to be there) and missed two-fragment splits (`politi cal`
has no single letters). *Fix:* measure fragmentation directly — the splitpair
rate: adjacent token pairs whose concatenation is a frequent word.

**2. Splitpair v1: circular dictionary contamination.**
v1 did not exclude single-letter tokens. Letter-spaced headings
(`C H A P T E R`) generated pairs (C,H)→"ch", (H,A)→"ha" — and those
two-letter strings, accumulated from headings corpus-wide, became "common
words" in the very lexicon the metric consulted. Every book with display
headings lit up. **Cost: 56 false positives, and healthy files were sent to
re-OCR and came back worse.** *Fix:* joined form must be ≥ 5 letters.
The general law: **the defect writes itself into the dictionary** — any
lexicon learned from a damaged corpus contains the damage.

**3. Acceptance gates with hidden absolute-number bugs.**
Three at once: a CJK check that passed on *existence* (one stray character
exempted a file), a "metric must drop 50%" rule (for a file at 8‰ that
demands reaching ~3.4‰ — the coincidence baseline — which is mathematically
impossible), and comparing absolute "the" counts across texts of different
lengths. **Cost: two damaged files were accepted and written.** *Fix:*
ratios, not existence; "below the floor" instead of "halved"; densities,
not counts.

**4. The blind spot of the fragmentation metric.**
Twelve OCR-disaster files sailed through three metrics with beautiful
numbers — because when a whole sentence is glued into one token
(`Researchisneededto`), there are **no adjacent pairs left to join**. The
splitpair rate of maximally damaged text is *zero*. They were caught only
when a human read the actual text. *Fix:* a dedicated glue gate (overlong
token rate), and a standing rule: **acceptance includes reading the file.**

**5. Keyword-based language detection.**
One German loanword exempted an entire damaged file from English checks.
*Fix:* ratio of function words (German must *outnumber* English), never
keyword existence.

**6. Learning the dictionary from the whole corpus.**
Split fragments (`polit`, `ical`, `cratic`) occur dozens of times per damaged
file, so raw frequency promoted them to "words," and the criterion "both
sides are words → leave it" then blocked exactly the repairs that mattered.
Switching to document frequency (DF) helped — real words spread across the
corpus, fragments cluster in damaged files — but one fragment appeared in 40+
files and polluted even DF. *Fix, three layers deep:* learn only from healthy
files → judge wordhood by DF → and when both sides still pass, merge anyway if
the joined form **overwhelms** the weaker fragment (>10× its frequency).
Legitimate pairs (`in to`, `a round`) never trigger the overwhelming clause
because their joined forms are in the same league as their parts.

**7. Scanning adjacent pairs with `re.sub`.**
`re.sub` consumes matches left to right: in `Michel Fou cault` it matches
"Michel Fou" first (no merge) and *consumes* "Fou" — so "Fou cault", the pair
that should be checked, is never examined. Diagnostic signature: single-letter
prefixes repaired fine, mid-word splits repaired at exactly zero. *Fix:*
positional token-by-token evaluation, never consuming substitution.

**8. Enumerating separator strings.**
The damage in one batch was "newline plus one extra space" — one character
away from the two patterns the existing tools expected, so both silently
fixed nothing. Another file used U+2011 (non-breaking hyphen), visually
identical to ASCII `-`, 1,086 times. *Fix:* normalize all hyphen and
whitespace variants first, *then* classify.

**9. Three near-misses caught in dry-run.**
The possessive `'s` merging forward (`Foucault's own` → "sown"); name
initials merging (`Robert E` → "roberte"); and a DP segmenter scoring with
*positive* log-frequencies — the more pieces you cut, the higher the score,
so it shredded real words. *Fix:* apostrophe guard, initial guards, log
*probabilities* (negative) plus a per-piece penalty. The meta-lesson:
**dry-run with printed examples is where these die cheaply.**

**10. The second pass overwrote the first pass's backups.**
Iterative repair rounds, same backup path: round 2 copied *round 1's output*
over the pristine originals. An earlier snapshot saved us. *Fix:* backup
copies only if the backup does not already exist (first-write wins).

**11. Overfitting the acceptance probe to one symptom.**
A gate tuned to one orphan fragment from an earlier bad extraction rejected a
*good* new extraction that happened not to contain it. *Fix:* judge candidate
extractions by same-position comparison and human reading, not by symptom
checklists from previous failures.

**12. Not stopping when marginal cost went negative.**
Re-OCR on 180+ page born-digital books ran for hours and made every file
worse (glue rate up 20–80×). The queue kept going because nobody had priced
the ladder. *Fix:* probe files *before* queueing (born-digital → never
re-OCR), and make the pipeline measure-then-decide per file rather than
batch-and-hope.

## The three laws they add up to

1. **Metrics rank, eyes admit.** Every metric has a failure mode it cannot
   see, and repair tends to chase the disease from one metric into another
   (fragmentation → glue). Use numbers to order the queue; use reading to
   accept the result.
2. **Gates must themselves be gated.** Before trusting a new detector, pull
   the first twenty things it fires on and ask: *what would make a healthy
   file trigger this?* (That question would have prevented #2, #5, and #11.)
3. **A tool's silence is not evidence about the world.** Zero hits means
   *this detector* found nothing — the pattern may be one character off (#8),
   consumed by the scanner (#7), or invisible to the metric by construction
   (#4). And the lexicon you check against may itself be contaminated (#2, #6).

## Findings that surprised us

- **Better parsers do not fix this.** Re-extraction with a modern
  layout-model parser reproduced the damaged text almost verbatim — the
  damage is in the PDF text layer, and faithful parsers faithfully copy it.
- **Re-OCR is a trade, not an upgrade.** It genuinely rescued old scans, and
  it reliably *worsened* born-digital files. Direction matters more than
  tooling.
- **Page anchors without OCR.** When an OCR pass swept running heads into the
  text flow, printed page numbers were already sitting in the text. Exact
  string scan + longest-increasing-subsequence outlier removal recovered 195
  anchors with position/page correlation 0.99996 — in seconds, where a
  fuzzy per-page alignment attempt had failed by cascade.
- **Sample sizes are unforgiving.** Claiming "95% accuracy" with 95%
  confidence requires 59/59 correct in a spot-check; 52/52 only supports
  94.4%. One step short is one step short.
