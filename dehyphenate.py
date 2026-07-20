# -*- coding: utf-8 -*-
"""dehyphenate.py — join end-of-line hyphenated words, against the corpus lexicon.

The disease: `deliber-\\n ation` in the text layer means exact grep for
"deliberation" fails. The danger of naive joining: in two-column extractions
"the next line" may belong to the OTHER column, and blind joining fabricates
words that never existed (we saw "sociowork" and "dyseconomic" invented this
way before this gate existed). So a join requires BOTH signals:

  1. the line really ends with a hyphen (explicit signal, not positional guess)
  2. the joined form is genuinely frequent in YOUR corpus
     (cross-column garbage fails this gate)

Anything below both bars is left untouched. Three verdicts per site:
  JOIN  joined form frequent and dominant      -> deliberation
  HYPH  hyphenated form frequent and dominant  -> decision-making (keep hyphen,
                                                  still merge the line break)
  SKIP  neither is convincing                  -> leave as-is

Usage:
  python dehyphenate.py --corpus <txt-root>            # dry-run (report only)
  python dehyphenate.py --corpus <txt-root> --apply    # write (backup first)

CORPUS_ROOT env var is honored when --corpus is omitted.
Backups go to --backup (default: ./_backup/dehyphenate/).

Ported from the production tooling of the alexandria librarian role
(https://github.com/kengo006/alexandria). Battle log: LESSONS.md.
"""
import argparse
import os
import re
import shutil
from collections import Counter

SPLIT = re.compile(r"([A-Za-z]{2,})-\r?\n([a-z]{2,})")


def walk_txt(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith("_")]
        for fn in fns:
            if fn.lower().endswith(".txt") and not fn.startswith("_"):
                yield os.path.join(dp, fn)


def build_dict(root):
    plain, hyph = Counter(), Counter()
    for p in walk_txt(root):
        s = open(p, "rb").read().decode("utf-8", errors="replace")
        for line in s.split("\n"):
            for w in re.findall(r"\b[A-Za-z]{3,}\b", line):
                plain[w.lower()] += 1
            for w in re.findall(r"\b[A-Za-z]{2,}-[A-Za-z]{2,}\b", line):
                hyph[w.lower()] += 1
    return plain, hyph


def decide(a, b, plain, hyph):
    pm = plain.get((a + b).lower(), 0)
    ph = hyph.get((a + "-" + b).lower(), 0)
    if pm >= 3 and pm > ph * 2:
        return "JOIN"
    if ph >= 2 and ph > pm:
        return "HYPH"
    return "SKIP"


def main():
    ap = argparse.ArgumentParser(description="Join end-of-line hyphenated words")
    ap.add_argument("--corpus", default=os.environ.get("CORPUS_ROOT"))
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--backup", default=os.path.join("_backup", "dehyphenate"),
                    help="backup directory used with --apply")
    args = ap.parse_args()
    if not args.corpus or not os.path.isdir(args.corpus):
        ap.error("--corpus <dir> is required (or set CORPUS_ROOT)")

    print("building corpus lexicon...", flush=True)
    plain, hyph = build_dict(args.corpus)
    print(f"  {len(plain):,} plain word types | {len(hyph):,} in-line hyphenated types\n")

    tot = Counter()
    changed = []
    for p in walk_txt(args.corpus):
        raw = open(p, "rb").read().decode("utf-8", errors="replace")
        n = {"JOIN": 0, "HYPH": 0, "SKIP": 0}

        def rep(m):
            a, b = m.group(1), m.group(2)
            d = decide(a, b, plain, hyph)
            n[d] += 1
            if d == "JOIN":
                return a + b
            if d == "HYPH":
                return a + "-" + b
            return m.group(0)

        new = SPLIT.sub(rep, raw)
        for k, v in n.items():
            tot[k] += v
        if n["JOIN"] + n["HYPH"]:
            changed.append((os.path.relpath(p, args.corpus), n, p, new))

    print(f"corpus-wide line-end hyphen sites: {sum(tot.values()):,}")
    print(f"  JOIN        {tot['JOIN']:>7,} ({tot['JOIN']/max(sum(tot.values()),1)*100:.1f}%)")
    print(f"  HYPH kept   {tot['HYPH']:>7,} ({tot['HYPH']/max(sum(tot.values()),1)*100:.1f}%)")
    print(f"  SKIP        {tot['SKIP']:>7,} ({tot['SKIP']/max(sum(tot.values()),1)*100:.1f}%)")
    print(f"  files that would change: {len(changed)}\n")

    print("largest 8:")
    for rel, n, _, _ in sorted(changed, key=lambda x: -(x[1]["JOIN"] + x[1]["HYPH"]))[:8]:
        print(f"  join {n['JOIN']:>5}  hyph {n['HYPH']:>4}  skip {n['SKIP']:>4}  {rel}")

    if not args.apply:
        print("\n[dry-run] nothing written. Add --apply to write (with automatic backup).")
        return
    os.makedirs(args.backup, exist_ok=True)
    for rel, n, p, new in changed:
        b = os.path.join(args.backup, rel)
        os.makedirs(os.path.dirname(b), exist_ok=True)
        if not os.path.exists(b):
            shutil.copy2(p, b)
        open(p, "w", encoding="utf-8", newline="").write(new)
    print(f"\n[applied] {len(changed)} files modified - originals in {args.backup}")


if __name__ == "__main__":
    main()
