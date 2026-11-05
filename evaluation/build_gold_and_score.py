"""Combine gold_check_50 + gold_extra_20 into evaluation/gold.csv.

- "OK" in kavini_label means Kavini agreed with the claude_label present at labelling time.
- Collapse near-duplicate contexts (same whitespace-normalised text) keeping one row.
- Report final label counts and Claude-vs-Kavini agreement on the extra 20.
"""
import csv
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
G50 = os.path.join(HERE, "..", "annotation", "gold_check_50.csv")
G20 = os.path.join(HERE, "..", "annotation", "gold_extra_20.csv")
OUT = os.path.join(HERE, "gold.csv")
LABELS = ["followed/applied", "distinguished", "doubted/overruled", "neutral"]


def norm(s):
    return " ".join(s.split()).lower()


def resolve(k, c):
    k = (k or "").strip()
    if k.lower() == "ok":
        return c
    return k


# gold 50 - keep every row's resolved label
rows50 = list(csv.DictReader(open(G50)))
for r in rows50:
    r["kavini_label_resolved"] = resolve(r["kavini_label"], r["claude_label"])

rows20 = list(csv.DictReader(open(G20)))
for r in rows20:
    r["kavini_label_resolved"] = resolve(r["kavini_label"], r["claude_label"])

# Claude-vs-Kavini on the extra 20
agree_extra = sum(1 for r in rows20
                  if r["claude_label"] == r["kavini_label_resolved"])
n_extra = len(rows20)
cm_extra = {a: {b: 0 for b in LABELS} for a in LABELS}
for r in rows20:
    c = r["claude_label"]; k = r["kavini_label_resolved"]
    if c in LABELS and k in LABELS:
        cm_extra[c][k] += 1

# merge with dedupe on normalised context
all_rows = rows50 + rows20
seen = set()
merged = []
for r in all_rows:
    key = norm(r["context"])
    if key in seen:
        continue
    seen.add(key)
    merged.append({
        "id": r["id"],
        "cited_raw": r["cited_raw"],
        "context": r["context"],
        "kavini_label": r["kavini_label_resolved"],
    })

counts = Counter(r["kavini_label"] for r in merged)

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["id", "cited_raw", "context", "kavini_label"])
    w.writeheader()
    for r in merged:
        w.writerow(r)

print(f"1) gold rows: 50 + 20 = 70 raw; merged (dedup contexts) = {len(merged)}")
print(f"2) label counts in gold: " + ", ".join(f"{l} {counts[l]}" for l in LABELS))
print(f"3) Claude-vs-Kavini on extra 20: {agree_extra}/{n_extra} = {100*agree_extra/n_extra:.1f}%")
print("4) extra-20 confusion (rows=Claude, cols=Kavini)")
print("   " + " ".join(f"{l[:10]:>10s}" for l in LABELS))
for a in LABELS:
    print(f"   {a[:10]:>10s} " + " ".join(f"{cm_extra[a][b]:>10d}" for b in LABELS))

with open(os.path.join(HERE, "gold_build_summary.md"), "w") as f:
    f.write("# Gold set build summary\n\n")
    f.write(f"- Rows: 50 + 20 = 70 raw, {len(merged)} after context-dedupe\n")
    f.write(f"- Label counts: " + ", ".join(f"{l} {counts[l]}" for l in LABELS) + "\n")
    f.write(f"- Claude-vs-Kavini on the extra 20: {agree_extra}/{n_extra} = {100*agree_extra/n_extra:.1f}%\n\n")
    f.write("## Extra-20 confusion matrix (rows=Claude, cols=Kavini)\n\n")
    f.write("| | " + " | ".join(LABELS) + " |\n|---|" + "---|" * len(LABELS) + "\n")
    for a in LABELS:
        f.write("| " + a + " | " + " | ".join(str(cm_extra[a][b]) for b in LABELS) + " |\n")
