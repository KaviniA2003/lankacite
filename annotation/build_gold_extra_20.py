"""Pick 20 NEW citation contexts most likely to be doubted/overruled or distinguished,
excluding any ids already in annotation/label_set.csv (silver + gold).

Cue words (must appear in a ±220-char window around the citation):
  overrule, per incuriam, not follow / did not follow, doubted, cannot agree,
  distinguishable, distinguished from, wrongly decided, disapproved.

Write annotation/gold_extra_20.csv with the same columns as gold_check_50.csv.
"""
import csv
import os
import re
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "..", "data", "judgments.db")
EXISTING = os.path.join(HERE, "label_set.csv")
OUT = os.path.join(HERE, "gold_extra_20.csv")

existing_ids = {int(r["id"]) for r in csv.DictReader(open(EXISTING, encoding="utf-8"))}

NEGATIVE = re.compile(
    r"(overrul(?:e|ed|ing)|per\s+incuriam|did\s+not\s+follow|cannot\s+be\s+followed|"
    r"disapprov(?:e|ed|ing)|wrongly\s+decided|"
    r"not\s+good\s+law|cannot\s+be\s+treated\s+as\s+good\s+law|"
    r"with\s+respect,?\s+we\s+(?:cannot|do\s+not)\s+(?:agree|follow)|"
    r"we\s+(?:would\s+)?(?:accordingly\s+)?overrule|I\s+(?:would\s+)?overrule)", re.I)
# "doubt" is tricky: "no doubt", "never doubted", "unable to doubt" are AFFIRMING.
# Only count "doubt" if preceded by explicit negative-treatment phrasing.
DOUBT_NEG = re.compile(
    r"(doubted\s+the\s+correctness|doubted\s+by|has\s+been\s+doubted|"
    r"we\s+doubt|I\s+doubt|now\s+doubted|is\s+doubted)", re.I)
FALSE_POS = re.compile(
    r"(unable\s+to\s+doubt|no\s+doubt|never\s+(?:been\s+)?doubted|without\s+doubt|"
    r"beyond\s+doubt|not\s+in\s+doubt)", re.I)
DISTINGUISH = re.compile(
    r"(can\s+(?:easily\s+)?be\s+(?:clearly\s+)?distinguished|is\s+distinguishable|"
    r"must\s+be\s+distinguished|should\s+have\s+distinguished|distinguish(?:es|ed)\s+the\s+case|"
    r"distinguished\s+the\s+facts|does\s+not\s+apply|inapplicable)", re.I)

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT id, citing_case, kind, raw AS cited_raw, case_name, report_key, case_no, "
    "target AS cited_target, context FROM citations "
    "WHERE context IS NOT NULL AND length(context) >= 120 AND kind != 'supra'"
).fetchall()
con.close()


def window(context, raw, r=220):
    i = context.find(raw[:40]) if raw else -1
    if i < 0:
        i = max(0, len(context) // 2 - r)
    return context[max(0, i - r): i + len(raw) + r]


def pick(regex, limit, extra_doubt=False):
    out = []
    seen = set()
    for row in rows:
        pid = row["id"]
        if pid in existing_ids or pid in seen:
            continue
        w = window(row["context"], row["cited_raw"] or "")
        if FALSE_POS.search(w):
            continue
        hit = regex.search(w) or (extra_doubt and DOUBT_NEG.search(w))
        if hit:
            out.append((row, w))
            seen.add(pid)
            if len(out) >= limit:
                break
    return out


neg = pick(NEGATIVE, 10, extra_doubt=True)
dist = pick(DISTINGUISH, 10)
# ensure no overlap between the two picks
dist = [(r, w) for (r, w) in dist if r["id"] not in {x[0]["id"] for x in neg}][:10]
if len(neg) + len(dist) < 20:
    pool_ids = {x[0]["id"] for x in neg} | {x[0]["id"] for x in dist}
    for row in rows:
        if row["id"] in existing_ids or row["id"] in pool_ids:
            continue
        w = window(row["context"], row["cited_raw"] or "")
        if NEGATIVE.search(w) or DISTINGUISH.search(w):
            (neg if NEGATIVE.search(w) else dist).append((row, w))
            if len(neg) + len(dist) >= 20:
                break

picked = (neg + dist)[:20]
print(f"1) {len(neg)} negative-cue + {len(dist)} distinguish-cue = {len(picked)} rows")

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "cited_raw", "context", "claude_label", "kavini_label"])
    for row, win in picked:
        suggested = "doubted/overruled" if NEGATIVE.search(win) else "distinguished"
        w.writerow([row["id"], row["cited_raw"] or "", win.strip(),
                    suggested, ""])
print(f"2) wrote {OUT}")
