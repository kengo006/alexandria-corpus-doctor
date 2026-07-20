# -*- coding: utf-8 -*-
"""repair_wordsplits.py — repair words split apart inside the text layer.

The disease: PDF kerning micro-adjustments and stylized initials make one word
arrive as two tokens. Two shapes:
  A  single-letter prefix : `p eople` / `t hese` / `D emocracy` (stylized
                            initials; chapter titles and running heads)
  B  mid-word split       : `polit ical` / `Fou cault` / `dif ference` (kerning)
Exact phrase grep fails (`political` never matches `polit ical`) and the
embedding of that span degrades too.

THE CRITERION IS MORPHOLOGICAL POSSIBILITY, NOT FREQUENCY RATIO:
  merge(a,b) holds iff  (1) `ab` is a common word in YOUR corpus (>= 30), and
                        (2) a or b is NOT itself a word -> the sequence "a b"
                            cannot be a legal two-word sequence
  `t hose` -> "t" is not a word -> merge (even though "hose" is a word).
  `a round` -> both are words -> LEAVE IT.
  Frequency-ratio criteria (freq[ab] > 3*freq[a]) necessarily fail on cases
  like `la rge` / `p eople` where the prefix is itself a common word — that is
  exactly why the standard approach cannot repair them.

Discipline: when unsure, do nothing (`a round` / `in to` stay). After applying,
re-run corpus_health.py AND read a few repaired pages with your own eyes —
metrics going green does not prove the text reads correctly.

Usage:
  python repair_wordsplits.py --corpus <txt-root> [--apply] [--file <substr>]
                              [--preview <dir>] [--backup <dir>]
  --file bypasses the file-level threshold (already-half-repaired files are
  otherwise a blind spot: 13 `demo cratic` sites once hid below the floor).
  --preview writes repaired copies elsewhere so you can read BEFORE applying.

CORPUS_ROOT env var is honored when --corpus is omitted.

Ported from the production tooling of the alexandria librarian role
(https://github.com/kengo006/alexandria). Battle log: LESSONS.md.
"""
import argparse
import os
import re
import shutil
from collections import Counter

# DO NOT scan adjacent pairs with re.sub. re.sub consumes matches left to
# right: in `Michel Fou cault` it first matches "Michel Fou" (no merge) and
# CONSUMES "Fou" — so "Fou cault", the pair that should be checked, never gets
# looked at. Symptom: single-letter-prefix cases repair fine (a single letter
# cannot be the second element, so the previous word cannot steal it) while
# mid-word splits repair at exactly zero. Correct approach: positional,
# token-by-token evaluation.
TOKEN = re.compile(r"[A-Za-z]+")

# "Is a word" = DOCUMENT FREQUENCY (DF), not total count. Split fragments
# (`polit` / `ical` / `Fou` / `cault`) occur dozens of times in each damaged
# file, so their total counts pass any threshold — but they live in only a few
# files, while real words spread across the corpus. DF separates the two.
# (This lesson was bought twice; see LESSONS.md #6.)
WORD_MIN_DF = 0.06      # appears in >= 6% of dictionary-source files
MERGE_MIN = 20
REAL_1LETTER = {"a", "i"}
CLEAN_MAX_SP = 2.0      # only files with splitpair < this feed the dictionary

# Hyphens come in many Unicode flavors: U+2011 NON-BREAKING HYPHEN looks
# identical to ASCII "-" but is a different codepoint (1,086 occurrences in one
# file taught us this). Enumerating literal strings WILL miss variants —
# normalize first, then classify.
HYPHENS = "‐‑‒–—­-"


def walk_txt(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith("_")]
        for fn in fns:
            if fn.lower().endswith(".txt") and not fn.startswith("_"):
                yield os.path.join(dp, fn)


def rd(p):
    return open(p, "rb").read().decode("utf-8", "replace").replace("\r\n", "\n")


def build_freq(root):
    """Learn the dictionary FROM HEALTHY FILES ONLY.
    First-run lesson: learning from the whole corpus lets fragments
    (`polit`/`ical`) accumulate into "words", and then criterion (2) —
    "both sides are words, leave it" — blocks exactly the merges that matter
    (27 `polit ical` sites in one file, all skipped). THE DEFECT WRITES ITSELF
    INTO THE DICTIONARY. Two passes: rough corpus-wide counts to estimate each
    file's splitpair, then rebuild counts from clean files only."""
    rough = Counter()
    allf = []
    for p in walk_txt(root):
        allf.append(p)
        rough.update(w.lower() for w in re.findall(r"[A-Za-z]+", rd(p)))

    def sp_of(s, fr):
        t = re.findall(r"[A-Za-z]+", s)
        if len(t) < 500:
            return 0.0
        n = sum(1 for a, b in zip(t, t[1:])
                if len(a + b) >= 5 and fr[(a + b).lower()] >= 30
                and fr[(a + b).lower()] > 3 * max(fr[a.lower()], fr[b.lower()]))
        return n / len(t) * 1000

    clean = Counter()
    df = Counter()               # document frequency: how many clean files carry the word
    n_src = 0
    for p in allf:
        s = rd(p)
        if len(re.findall(r"[一-鿿]", s)) > len(s) * 0.05:
            continue
        if sp_of(s, rough) < CLEAN_MAX_SP:
            ws = [w.lower() for w in re.findall(r"[A-Za-z]+", s)]
            clean.update(ws)
            df.update(set(ws))
            n_src += 1
    print(f"  dictionary sources: {n_src}/{len(allf)} files (clean only)")
    return clean, df, n_src, allf


def main():
    ap = argparse.ArgumentParser(description="Repair words split apart in the text layer")
    ap.add_argument("--corpus", default=os.environ.get("CORPUS_ROOT"))
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--file", default=None,
                    help="comma-separated substrings; only matching files, threshold bypassed")
    ap.add_argument("--preview", default=None,
                    help="write repaired copies to this dir instead of applying (READ THEM)")
    ap.add_argument("--backup", default=os.path.join("_backup", "repair_wordsplits"))
    args = ap.parse_args()
    if not args.corpus or not os.path.isdir(args.corpus):
        ap.error("--corpus <dir> is required (or set CORPUS_ROOT)")

    print("building corpus dictionary...", flush=True)
    freq, df, n_src, allf = build_freq(args.corpus)
    print(f"  {len(freq):,} word types\n", flush=True)
    if n_src < 20:
        print("WARNING: fewer than 20 clean dictionary-source files. The repair criterion")
        print("depends on a real corpus to learn from; on a tiny corpus, do not trust it.")

    def is_word(x):
        """DF criterion: real words spread across the corpus; split fragments
        live only in the few damaged files."""
        x = x.lower()
        if len(x) == 1:
            return x in REAL_1LETTER
        return df[x] / max(n_src, 1) >= WORD_MIN_DF

    # MEASUREMENT dictionary = whole corpus (comparable with corpus_health);
    # REPAIR criterion uses the clean dictionary above.
    gfreq = Counter()
    for p in allf:
        gfreq.update(w.lower() for w in re.findall(r"[A-Za-z]{2,}", rd(p)))

    def splitpair(s):
        t = re.findall(r"[A-Za-z]+", s)
        if len(t) < 500:
            return None
        n = sum(1 for a, b in zip(t, t[1:])
                if len((a + b)) >= 5 and gfreq[(a + b).lower()] >= 30
                and gfreq[(a + b).lower()] > 3 * max(gfreq[a.lower()], gfreq[b.lower()]))
        return n / len(t) * 1000

    targets = []
    for p in allf:
        rel = os.path.relpath(p, args.corpus)
        if args.file and not any(x.strip().lower() in rel.lower()
                                 for x in args.file.split(",") if x.strip()):
            continue
        s = rd(p)
        if len(re.findall(r"[一-鿿]", s)) > len(s) * 0.05:
            continue
        sp = splitpair(s)
        # --file bypasses the floor: files already repaired below 5 permille
        # are otherwise a permanent blind spot for their remaining sites.
        if sp is not None and (sp >= 5.0 or args.file):
            targets.append((sp, p, rel))
    targets.sort(reverse=True)
    print(f"targets: {len(targets)} files ({'APPLY' if args.apply else 'dry-run'})\n")

    grand = Counter()
    for sp0, p, rel in targets:
        s = rd(p)
        stat = Counter()
        examples = Counter()
        skipped = Counter()

        def collapse_runs(text):
            """Letter-spaced display words (`C H A P T E R`) must be collapsed
            as a WHOLE RUN, never pairwise: pairwise merging yields `CH AP TE R`,
            and `ch`/`ap` — accumulated corpus-wide from headings — would pass
            the dictionary test (the circular-contamination trap again)."""
            out, n = [], 0
            pos = 0
            toks = list(TOKEN.finditer(text))
            i = 0
            while i < len(toks):
                j = i
                while (j + 1 < len(toks) and len(toks[j].group(0)) == 1
                       and len(toks[j + 1].group(0)) == 1
                       and text[toks[j].end():toks[j + 1].start()] == " "):
                    j += 1
                if j - i + 1 >= 4:                       # >= 4 single letters = display word
                    run = "".join(t.group(0) for t in toks[i:j + 1])
                    if freq[run.lower()] >= MERGE_MIN:   # collapse only into a real word
                        out.append(text[pos:toks[i].start()])
                        out.append(run)
                        pos = toks[j].end()
                        n += 1
                        examples[f"<{' '.join(t.group(0) for t in toks[i:j+1])}> -> {run}"] += 1
                    i = j + 1
                else:
                    i += 1
            out.append(text[pos:])
            return "".join(out), n

        def classify_sep(sep):
            """Return (processable?, contains-hyphen?). Normalize all hyphen
            variants to '-' and all whitespace to ' ' BEFORE judging. Key field
            observation: much line-break splitting arrives as "newline PLUS one
            extra space" (`Sci\\n ence` / `philosophi-\\n cal`) — tools that
            expect exactly `word-\\nword` or `word\\nword` miss all of it."""
            norm = "".join("-" if c in HYPHENS else (" " if c in " \t\n\r" else c) for c in sep)
            norm = re.sub(r" +", " ", norm)
            if norm.strip("-") not in ("", " "):
                return False, False
            return (norm in ("", " ", "-", " -", "- ", " - ")), ("-" in norm)

        def repair_once(text):
            toks = list(TOKEN.finditer(text))
            merges = []            # (start, end, replacement)
            i = 0
            while i < len(toks) - 1:
                m1, m2 = toks[i], toks[i + 1]
                sep = text[m1.end():m2.start()]
                if len(sep) > 4:
                    i += 1; continue
                ok, has_hyphen = classify_sep(sep)
                if not ok:
                    i += 1; continue
                # Apostrophe guard: the s of `Foucault's own` must not merge forward.
                if m1.start() > 0 and text[m1.start() - 1] in "'’":
                    i += 1; continue
                a, b = m1.group(0), m2.group(0)
                j = (a + b).lower()
                aw, bw = is_word(a), is_word(b)
                # Third layer of contamination defense (bought with 13 missed
                # `demo cratic` sites): `cratic` fragments spread across 40+
                # damaged files, so even DF got polluted. When both sides pass
                # the word test, still merge if the joined form OVERWHELMS the
                # weaker fragment (>10x): democratic 21,537 vs cratic 147 = 146x.
                # Legal pairs (in to / a round / can not) have joined forms in
                # the same league as their parts and never trigger this.
                overwhelming = freq[j] > 10 * min(freq[a.lower()], freq[b.lower()])
                mergeable = (freq[j] >= MERGE_MIN and (not (aw and bw) or overwhelming)
                             and not (len(b) == 1 and aw)                     # Robert E / of T
                             and not (len(a) == 1 and a.isupper() and bw)     # B and / C is
                             and not (len(a) == 1 and len(b) == 1
                                      and (a.isupper() or b.isupper())))      # leftover C H
                if mergeable:
                    merges.append((m1.end(), m2.start(), ""))
                    stat["merged"] += 1
                    examples[f"{a}[{sep.replace(chr(10), '<NL>')}]{b} -> {j}"] += 1
                    i += 2
                    continue
                # Hyphen branch: both sides are words and `a-b` is corpus-attested
                # -> collapse to `a-b` (drop the line break, keep the hyphen).
                if has_hyphen and freq.get(f"{a}-{b}".lower(), 0) >= 3 and len(sep) > 1:
                    merges.append((m1.end(), m2.start(), "-"))
                    stat["hyph"] += 1
                    i += 2
                    continue
                if freq[j] >= MERGE_MIN:
                    skipped[f"{a}|{b}"] += 1
                i += 1
            for st, en, repl in reversed(merges):
                text = text[:st] + repl + text[en:]
            return text, len(merges)

        new, n_run = collapse_runs(s)       # collapse display words first, then pairs
        for _ in range(4):                  # iterate to fixpoint (merges expose new pairs)
            new, n = repair_once(new)
            if n == 0:
                break
        stat["runs"] = n_run
        sp1 = splitpair(new)
        grand["merged"] += stat["merged"]
        print(f"  {sp0:6.2f} -> {(sp1 if sp1 is not None else -1):6.2f} permille  "
              f"merged {stat['merged']:>5}  hyph {stat.get('hyph', 0):>4}  "
              f"display {stat.get('runs', 0):>3}  ambiguous {sum(skipped.values()):>5}  "
              f"{os.path.basename(rel)[:38]}")
        for k, v in examples.most_common(5):
            print(f"        {v:>4}x  {k}")
        if skipped:
            print(f"        [left alone] {'  '.join(f'{k}({v})' for k, v in skipped.most_common(4))}")
        if args.preview:
            os.makedirs(args.preview, exist_ok=True)
            open(os.path.join(args.preview, os.path.basename(rel)), "w",
                 encoding="utf-8", newline="").write(new)
        elif args.apply and stat["merged"]:
            b = os.path.join(args.backup, rel)
            os.makedirs(os.path.dirname(b), exist_ok=True)
            if not os.path.exists(b):
                shutil.copy2(p, b)
            open(p, "w", encoding="utf-8", newline="").write(new)

    print(f"\ntotal merges: {grand['merged']:,}")
    if args.apply:
        print(f"backups: {args.backup}")
    else:
        print("[dry-run] nothing written.")


if __name__ == "__main__":
    main()
