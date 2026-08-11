# -*- coding: utf-8 -*-
"""unglue_words.py — split words glued together in the text layer.

The disease: extraction loses spaces and whole spans arrive as one token
(`proponentsoftheextendedmindthesis` / `Bothexperimentsarepreregisteredbetween`).
The mirror image of repair_wordsplits.py (that one repairs EXTRA spaces, this
one repairs MISSING spaces). Exact phrase grep fails completely, and the
embedding of the span degrades.

Method: dynamic-programming segmentation (Norvig-style unigram), dictionary
learned FROM HEALTHY FILES ONLY (same lesson as repair_wordsplits — the defect
writes itself into the dictionary). For every token >= --min-len that is not
itself a word, find a segmentation where EVERY piece is a reliable word;
best sum of log-probabilities wins; every piece must be >= 3 letters (no a/i/s
confetti). If no fully legal segmentation exists, DO NOTHING — that is what
keeps legitimate long words like `psychopharmaceuticals` safe.

Discipline: after splitting, verify (1) long-token count fell, (2) word count
rose by a plausible amount, (3) READ a few repaired spans. When unsure, do nothing.

Known subclass this method should NOT be the first answer for (LESSONS #20):
some layout-aware extractors normalise em/en dashes to ASCII hyphens and then
drop them at a cell boundary, welding `assembly-it` into `assemblyit`. There the
true value is still in the PDF, so a diff against a dash-preserving extraction
of the same page settles it exactly -- determined, not inferred. Reach for the
dictionary only for the fused spans that source comparison cannot decide.

Usage:
  python unglue_words.py --corpus <txt-root> [--apply] [--preview <dir>]
                         [--exclude <prefix,prefix,...>] [--backup <dir>]
  --exclude skips subtrees by relative-path prefix (e.g. web-clipping folders
  whose UI artifacts look like glued words but are not prose).

CORPUS_ROOT env var is honored when --corpus is omitted.

Ported from the production tooling of the alexandria librarian role
(https://github.com/kengo006/alexandria). Battle log: LESSONS.md.
"""
import argparse
import math
import os
import re
import shutil
from collections import Counter

MIN_LEN = 15            # only tokens this long are candidates (short = too ambiguous)
GLUE_THR = 3.0          # file-level floor: long tokens per 1k
MIN_PIECE = 3           # every piece >= 3 letters
WORD_MIN_DF = 0.06


def walk_txt(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith("_")]
        for fn in fns:
            if fn.lower().endswith(".txt") and not fn.startswith("_"):
                yield os.path.join(dp, fn)


def rd(p):
    return open(p, "rb").read().decode("utf-8", "replace").replace("\r\n", "\n")


def main():
    ap = argparse.ArgumentParser(description="Split glued words via DP segmentation")
    ap.add_argument("--corpus", default=os.environ.get("CORPUS_ROOT"))
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--preview", default=None, help="write repaired copies here instead")
    ap.add_argument("--exclude", default=None,
                    help="comma-separated relative-path prefixes to skip")
    ap.add_argument("--backup", default=os.path.join("_backup", "unglue_words"))
    args = ap.parse_args()
    if not args.corpus or not os.path.isdir(args.corpus):
        ap.error("--corpus <dir> is required (or set CORPUS_ROOT)")
    excludes = [x.strip() for x in (args.exclude or "").split(",") if x.strip()]

    print("building clean dictionary (healthy files only)...", flush=True)
    files = list(walk_txt(args.corpus))

    def glue_rate(s):
        t = re.findall(r"[A-Za-z]+", s)
        if len(t) < 300:
            return None
        return sum(1 for w in t if len(w) >= 18) / len(t) * 1000

    freq, df, n_src = Counter(), Counter(), 0
    for p in files:
        s = rd(p)
        if len(re.findall(r"[一-鿿]", s)) > len(s) * 0.05:
            continue
        g = glue_rate(s)
        if g is not None and g < 1.5:                 # healthy files feed the dictionary
            ws = [w.lower() for w in re.findall(r"[A-Za-z]+", s)]
            freq.update(ws); df.update(set(ws)); n_src += 1
    print(f"  sources {n_src} files | {len(freq):,} word types\n", flush=True)
    if n_src < 20:
        print("WARNING: fewer than 20 clean dictionary-source files - do not trust")
        print("segmentation learned from a tiny corpus.")

    total = sum(freq.values())

    def dfr(x):
        return df[x.lower()] / max(n_src, 1)

    def is_glued_pair(x):
        """Is this piece itself two very common function words glued together
        (`ofthe` = of+the)? Then it is an artifact, not a word. BUT legitimate
        compounds must be exempted first: `understand` (under+stand) and
        `classroom` (class+room) also decompose into two very common pieces —
        the first version lacked this exemption, declared them artifacts, and
        the DP then split real words apart (`Can under stand completely`).
        Criterion: a form that is itself common enough IS a real word."""
        if dfr(x) >= 0.35:
            return False
        for k in range(2, len(x) - 1):
            if dfr(x[:k]) >= 0.55 and dfr(x[k:]) >= 0.55:
                return True
        return False

    def is_word(x):
        """Usable as a segmentation piece = high DF (spread corpus-wide) + long
        enough + not itself a glue artifact. Raw counts alone will not do:
        `ofthe` / `oft` / `tion` / `san` all have high totals."""
        x = x.lower()
        if len(x) < MIN_PIECE or dfr(x) < WORD_MIN_DF:
            return False
        return not is_glued_pair(x)

    def already_word(x):
        """The token itself is a legal word (however rare) -> never split.
        `environmentalism` / `paradigmatically` / `psychopharmaceuticals`
        survive on this rule."""
        x = x.lower()
        return freq[x] >= 5 or df[x] >= 3

    # Scoring uses LOG PROBABILITIES (negative): more pieces = lower score, so
    # fewer/longer pieces win naturally. The first version used log(freq)
    # (positive) — "the more you cut, the higher the score" — and produced
    # `What Make san Institu tion`-grade over-segmentation.
    logp = {w: math.log(freq[w] / total) for w in freq}
    # Extra penalty per piece. 3.0 was still too low (`Canunderstandcompletely`
    # got cut into `Can under stand completely`, splitting a real word) ->
    # 8.0 makes fewer-and-longer win decisively.
    PIECE_PENALTY = 8.0

    def segment(tok):
        """DP segmentation; returns list of pieces or None."""
        low = tok.lower()
        n = len(low)
        best = [None] * (n + 1)
        best[0] = (0.0, [])
        for i in range(1, n + 1):
            for j in range(max(0, i - 22), i):
                if best[j] is None:
                    continue
                piece = low[j:i]
                if not is_word(piece):
                    continue
                score = best[j][0] + logp.get(piece, -30.0) - PIECE_PENALTY
                if best[i] is None or score > best[i][0]:
                    best[i] = (score, best[j][1] + [(j, i)])
        if best[n] is None or len(best[n][1]) < 2:
            return None
        return [tok[a:b] for a, b in best[n][1]]

    targets = []
    for p in files:
        s = rd(p)
        if len(re.findall(r"[一-鿿]", s)) > len(s) * 0.05:
            continue
        g = glue_rate(s)
        if g is not None and g >= GLUE_THR:
            targets.append((g, p, os.path.relpath(p, args.corpus)))
    targets.sort(reverse=True)
    mode = "PREVIEW" if args.preview else ("APPLY" if args.apply else "dry-run")
    print(f"targets: {len(targets)} files ({mode})\n")

    for g0, p, rel in targets:
        s = rd(p)
        # German exemption: compounds are legitimately long. Ratio-based call.
        t_all = [w.lower() for w in re.findall(r"[A-Za-z]+", s)]
        de = sum(1 for w in t_all if w in {"der", "die", "das", "und", "nicht", "von", "dem", "den", "ist"})
        en = sum(1 for w in t_all if w in {"the", "of", "and", "to", "in", "that", "is", "was"})
        if de > en:
            print(f"  {g0:6.2f} permille  [German file - exempt] {os.path.basename(rel)[:48]}")
            continue
        # Guards: tiny files (risk > benefit) and base64/code-dense files.
        n_words = len(re.findall(r"[A-Za-z]+", s))
        # Real base64 must contain digits or +/ ; PURE-LETTER long runs are
        # exactly the glued words we are here to repair (the first version
        # lacked this distinction and skipped a genuinely glued target).
        b64 = len(re.findall(r"(?=[A-Za-z0-9+/]{40,})(?=[^ ]*[0-9+/])[A-Za-z0-9+/]{40,}={0,2}", s))
        if n_words < 2000:
            print(f"  {g0:6.2f} permille  [file too small: {n_words} words - skip] {os.path.basename(rel)[:44]}")
            continue
        if any(rel.replace("\\", "/").startswith(x) for x in excludes):
            print(f"  {g0:6.2f} permille  [excluded prefix - skip] {os.path.basename(rel)[:44]}")
            continue
        if b64 >= 20:
            print(f"  {g0:6.2f} permille  [base64/code-dense: {b64} runs - skip] {os.path.basename(rel)[:40]}")
            continue
        done, kept = [], []

        def rep(m):
            tok = m.group(0)
            if len(tok) < MIN_LEN or already_word(tok):
                return tok
            seg = segment(tok)
            if seg is None:
                kept.append(tok)
                return tok
            done.append((tok, " ".join(seg)))
            return " ".join(seg)

        new = re.sub(r"[A-Za-z]+", rep, s)
        g1 = glue_rate(new)
        nt0 = len(re.findall(r"[A-Za-z]+", s))
        nt1 = len(re.findall(r"[A-Za-z]+", new))
        print(f"  {g0:6.2f} -> {(g1 if g1 is not None else -1):5.2f} permille  "
              f"split {len(done):>4}  kept {len(kept):>4}  words {nt0:,} -> {nt1:,}  "
              f"{os.path.basename(rel)[:40]}")
        for a, b in done[:4]:
            print(f"        {a[:44]} -> {b[:56]}")
        if kept[:3]:
            print(f"        [left alone] {'  '.join(k[:26] for k in kept[:3])}")
        if args.preview:
            os.makedirs(args.preview, exist_ok=True)
            open(os.path.join(args.preview, os.path.basename(rel)), "w",
                 encoding="utf-8", newline="").write(new)
        elif args.apply and done:
            b = os.path.join(args.backup, rel)
            os.makedirs(os.path.dirname(b), exist_ok=True)
            if not os.path.exists(b):
                shutil.copy2(p, b)
            open(p, "w", encoding="utf-8", newline="").write(new)
    if args.apply:
        print(f"\nbackups: {args.backup}")


if __name__ == "__main__":
    main()
