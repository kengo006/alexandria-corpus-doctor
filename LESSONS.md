# LESSONS — the battle log

These tools were not designed; they were *survived into*. Across two
remediation campaigns on a corpus of a few hundred scholarly texts, every
naive version failed in an instructive way. The twenty failures below are
preserved in the tools as guards, tests and comments; this file is the
narrative index. Names of specific
books and files are omitted throughout — the shapes of the failures are what
generalize.

## The twenty

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
The possessive `'s` merging forward (`the author's own` → "sown"); name
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

**13. Repairing what nobody would ever search for.**
A character-substitution class was repaired across 1,122 sites before anyone
asked whether the word it produced was one a reader would ever search for. It
was a copula. The text layer is a **locating** layer — the authoritative text
is the PDF — so the question is not "is this damaged?" but **"does this stop a
content word from being found?"** *Fix:* three priorities, and the middle one
does the work. **P0** a content keyword is broken and the file carries no
correct form → repair. **P1** a content word that is not on your keyword list
→ two independent pieces of evidence before touching it. **P2** stop words,
page numbers, running heads, footnote markers, column gutters → **decided not
to fix, which is not the same as not yet fixed**. The tool was fine; the value
function was wrong.

**14. Eight domain gaps, one disease.**
Every scanning expression has a boundary condition, and every boundary
condition is a region the scan cannot see. Over one campaign the same error
surfaced eight times in eight different places: a **minimum length** on the
leading fragment; a **gap width** fixed at exactly one space; a **direction**
(only splits, never joins); a **case** anchor; a **hyphen-handling** choice
(tried keeping it, never tried dropping it); a **semantic misjudgement inside
a guard** (a year read as a fragment, so the detector went blind precisely
inside bibliographies); a **comparison scope** (corpus-wide dictionary, never
within a single file); and a **unit of measurement in the gate itself**
(corpus-wide document frequency, so a term specific to one book could never
serve as its own reference form). *Fix:* before writing or changing any scan,
**ask what it structurally cannot see and measure the answer** — write a
diagnostic that matches only the anchor with no context constraints and diff
the two. Put the number in the docstring, and say whether the remainder is
*decided not to fix* or *not yet fixed*.

**15. A repair whose wrong output is a real word.**
The safest-looking case is the dangerous one. A split fragment joined into a
perfectly ordinary English word and the gate accepted it on exactly that
ground — while the printed page carried a **surname with a dropped ligature**.
Applying the rule in bulk would have replaced a person's name with a word that
reads as completely normal, and **no downstream gate would ever light up
again**. Same class: two fragments that are each a real word in another
language; a fragment that is genuinely the tail of a legitimate phrase.
*Fix:* pair the pre-flight question of law #2 with its twin — **what does this
look like when it is wrong?** If the wrong output is a real word, the repair
never runs in bulk: deny list with dated evidence per entry, a `--show` mode
that prints surrounding context, and regression cases drawn from the false
positives you actually met.

**16. "New" is a judgement relative to a list.**
A defect type was named, ruled low-priority, never written down — and then
surfaced in four later variants, every one of them during the rounds where
convergence was being declared. If the list is incomplete, "N consecutive
rounds with nothing new" measures **the maintainer's memory**, not the corpus.
*Fix:* register a type the round you name it, **even when the ruling is "not
fixing this"** — those need the register most, because no tool will ever touch
them again and the list is the only place they live.

**17. Two kinds of scan find different things.**
Mechanism-side scanning asks *where is it broken*, and every gate encodes an
already-named failure mode — so it structurally cannot find one nobody has
thought of yet. Symptom-side scanning asks a different question: **is this
book's core term spelled the minority way?** It needs no mechanism, and on its
first run it found a class that twenty-eight rounds of mechanism-side scanning
had missed. It is not a replacement: it only sees terms a book discusses
often, and most of its candidates are legitimate orthography that varies by
book — a hyphenation the author chose, a period spelling, a translator's
convention. *Fix:* run both, and let a person read the candidates.

**18. The stopping condition is self-referential.**
Two conditions, not one: the mechanical indicator at zero **and** N
consecutive blind-sample rounds turning up nothing new. Only the first is
machine-checkable. But both are measured *inside* the detector — the
"nothing new" judgement compares against your own list of known types — so
whoever declares convergence is the person who has been looking, and their
detector and their attention are the same set. *Fix:* **the final confirming
round is ordered by whoever receives the report, not by whoever wrote it.**
Here a completion was announced twice and overturned twice, both times by an
instruction to run one more round, and both extra rounds found real defects.
And note what did *not* help: both reports had said "this is a heuristic, not
a proof". **A hedge protects the record, not the judgement.**

**19. A test runner that skips is not a test runner that passes.**
A regression case was skipped for a missing optional dependency, and the
runner still printed "all tests passed". *Fix:* **exit non-zero when anything
was skipped**, and inject a stub so environment gaps cannot silence a case.
Untested is not passed.

**20. Some glued words have a knowable cause — and then the repair stops guessing.**
`unglue_words.py` segments a fused token by dictionary probability, because the
space is normally just *gone* and nothing left in the file says where it stood.
One subclass is not like that. Some layout-aware extractors normalise every em
and en dash to an ASCII hyphen and, at an internal cell boundary, drop it and
weld the two sides together. Where the dash had spaces around it the loss is
cosmetic; where it did not (`assembly—it`), two words become one token and the
shorter one stops being findable. Measured on one 18-page article: 29 em dashes
and 58 en dashes present in a plain text-flow extraction, **zero of either** in
the layout-aware one, and 6 fused pairs as a result. *Why it matters:* the true
value is still in the PDF, so this subclass can be repaired **against the
source** instead of inferred from a dictionary — and dictionary segmentation is
precisely the method whose wrong answers come out as real words (lesson 15).
*Fix:* before segmenting, compare the fused span against a dash-preserving
extraction of the same page; where the source has a dash and the fused form
occurs exactly once, the repair is determined rather than guessed. ⚠ Only the
determined ones. The rest stay with the dictionary path and its deny list.

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
