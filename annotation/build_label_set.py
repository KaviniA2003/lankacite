"""
LankaCite - build 200 citation contexts for precedent-treatment labelling.

For every citation with a non-empty context the script guesses one of four labels
    followed/applied, distinguished, doubted/overruled, neutral
from cue words in the ~400 characters around the citation (the `context` column already
holds that window). Negatives are rare, so the script OVERSAMPLES them: it keeps every
doubted/overruled candidate and every distinguished candidate, then fills the rest with
followed / neutral, preferring SC FR citing cases. The result is written to

    annotation/label_set.csv

with columns suggested_label and kavini_label (blank). Kavini accepts or corrects the
suggested label in a spreadsheet.

Run: python3 annotation/build_label_set.py --db data/judgments.db --out annotation/label_set.csv
"""

import argparse
import csv
import os
import re
import sqlite3
from collections import Counter

CUES = {
    "doubted/overruled": [
        r"\boverrul(ed|ing|e)\b", r"\bdoubt(ed|ing)\b", r"\bdisapprov(ed|ing|e)\b",
        r"\bwrongly decided\b", r"\bper incuriam\b", r"\bno longer good law\b",
        r"\bdepart(ed|ing|ure) from\b", r"\bcannot (now )?stand\b", r"\bwith respect,? we (cannot|do not) (agree|follow)\b",
        r"\breconsider(ed|ing)?\b", r"\bnot good law\b",
    ],
    "distinguished": [
        r"\bdistinguish(ed|able|ing)?\b", r"\bdoes not apply\b", r"\binapplicable\b",
        r"\bfacts? (are|is) different\b", r"\bon different facts\b", r"\bconfined to its (own )?facts\b",
    ],
    "followed/applied": [
        r"\bfollow(ed|ing|s)?\b", r"\bappli(ed|es|ying)\b", r"\badopt(ed|ing|s)?\b",
        r"\bapprov(ed|ing|es|al)\b", r"\bagree(d|ing)? with\b", r"\bin accordance with\b",
        r"\bendors(ed|ing|es)\b", r"\breiterat(ed|ing|es)\b", r"\baffirm(ed|ing|s)?\b",
        r"\brel(y|ied|ying) on\b", r"\bcit(ed|ing) with approval\b",
    ],
}

COMPILED = {lbl: [re.compile(p, re.I) for p in pats] for lbl, pats in CUES.items()}

PRIORITY = ["doubted/overruled", "distinguished", "followed/applied", "neutral"]


def guess_label(context: str) -> str:
    for lbl in PRIORITY[:-1]:  # negatives first
        for rx in COMPILED[lbl]:
            if rx.search(context):
                return lbl
    return "neutral"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/judgments.db")
    ap.add_argument("--out", default="annotation/label_set.csv")
    ap.add_argument("--n", type=int, default=200)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT id, citing_case, kind, raw, case_name, report_key, case_no, target, context
        FROM citations
        WHERE context IS NOT NULL AND length(context) >= 80 AND kind != 'supra'
    """).fetchall()
    con.close()
    print(f"1) {len(rows)} citations with context")

    # dedupe by (citing_case, target or report_key or case_no or raw) keeping longest context
    best = {}
    for r in rows:
        key = (r["citing_case"], r["target"] or r["report_key"] or r["case_no"] or r["raw"])
        if key not in best or len(r["context"]) > len(best[key]["context"]):
            best[key] = r
    rows = list(best.values())
    print(f"2) {len(rows)} after dedupe")

    labelled = [(r, guess_label(r["context"])) for r in rows]
    by_label = {lbl: [x for x in labelled if x[1] == lbl] for lbl in PRIORITY}
    print("3) cue-word distribution: " + ", ".join(f"{k} {len(v)}" for k, v in by_label.items()))

    def sc_fr_first(xs):
        return sorted(xs, key=lambda x: (not x[0]["citing_case"].startswith("SC_FR_"), x[0]["citing_case"]))

    picked = []
    # all negatives (capped so one class can't eat everything)
    cap_neg = min(len(by_label["doubted/overruled"]), max(20, args.n // 4))
    cap_dist = min(len(by_label["distinguished"]), max(30, args.n // 3))
    picked += sc_fr_first(by_label["doubted/overruled"])[:cap_neg]
    picked += sc_fr_first(by_label["distinguished"])[:cap_dist]
    remaining = args.n - len(picked)
    # rest: half followed/applied, half neutral; SC FR first
    half = remaining // 2
    picked += sc_fr_first(by_label["followed/applied"])[:half]
    picked += sc_fr_first(by_label["neutral"])[:remaining - half]
    # top up from any bucket if short
    if len(picked) < args.n:
        pool = [x for x in labelled if x not in picked]
        picked += sc_fr_first(pool)[: args.n - len(picked)]
    picked = picked[: args.n]

    dist = Counter(lbl for _, lbl in picked)
    print(f"4) selected {len(picked)}: " + ", ".join(f"{k} {dist[k]}" for k in PRIORITY))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "citing_case", "cited_target", "cited_raw", "case_name",
                    "report_key", "case_no", "context", "suggested_label", "kavini_label", "notes"])
        for r, lbl in picked:
            w.writerow([r["id"], r["citing_case"], r["target"] or "", r["raw"] or "",
                        r["case_name"] or "", r["report_key"] or "", r["case_no"] or "",
                        (r["context"] or "").strip().replace("\n", " "),
                        lbl, "", ""])
    print(f"5) wrote {args.out}")


if __name__ == "__main__":
    main()
