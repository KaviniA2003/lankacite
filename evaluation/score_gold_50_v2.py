"""Score the stricter v2 labels against Kavini's gold 50.
Pass 2 was produced by rule-based downgrade of followed/applied when counsel/lists dominate.
No gold row was used as training example - rules are generic.
"""
import csv
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "annotation"))
from _claude_labels_v2 import LABELS as V2

GOLD = os.path.join(HERE, "..", "annotation", "gold_check_50.csv")
OUT_MD = os.path.join(HERE, "gold_50_agreement_v2.md")
LABELS = ["followed/applied", "distinguished", "doubted/overruled", "neutral"]

rows = list(csv.DictReader(open(GOLD, encoding="utf-8")))
pairs = []
for r in rows:
    pid = int(r["id"])
    c_v1 = r["claude_label"].strip()
    c_v2 = V2[pid]
    k = r["kavini_label"].strip()
    kavini = c_v1 if k.lower() == "ok" else k
    pairs.append((pid, c_v2, kavini, r["context"]))

by_ctx = defaultdict(list)
for pid, _, _, ctx in pairs:
    by_ctx[" ".join(ctx.split())].append(pid)
dups = {ids[0]: ids for ids in by_ctx.values() if len(ids) > 1}

seen = set()
scored = []
for pid, c, k, ctx in pairs:
    key = " ".join(ctx.split())
    if key in seen:
        continue
    seen.add(key)
    scored.append((pid, c, k))

n = len(scored)
agree = sum(1 for _, c, k in scored if c == k)
cm = {a: {b: 0 for b in LABELS} for a in LABELS}
for _, c, k in scored:
    if c in LABELS and k in LABELS:
        cm[c][k] += 1
po = agree / n
c_counts = Counter(c for _, c, _ in scored)
k_counts = Counter(k for _, _, k in scored)
pe = sum((c_counts[l] / n) * (k_counts[l] / n) for l in LABELS)
kappa = (po - pe) / (1 - pe) if pe != 1 else 0.0

lines = [
    "# Claude v2 (strict) vs Kavini - gold 50 agreement\n",
    f"- Rows in file: {len(pairs)}",
    f"- Near-duplicate groups collapsed: {len(dups)} (ids: {[v for v in dups.values()]})",
    f"- Rows scored (after dedupe): {n}",
    f"- Agreement: {agree}/{n} = {100 * po:.1f}%",
    f"- Cohen's kappa: {kappa:.3f}\n",
    "## Confusion matrix (rows = Claude v2, cols = Kavini)\n",
    "| | " + " | ".join(LABELS) + " |",
    "|---|" + "---|" * len(LABELS),
]
for a in LABELS:
    lines.append("| " + a + " | " + " | ".join(str(cm[a][b]) for b in LABELS) + " |")
lines.append("")
lines.append("## Per-label support\n")
lines.append("| label | Claude v2 | Kavini |")
lines.append("|---|---|---|")
for l in LABELS:
    lines.append(f"| {l} | {c_counts[l]} | {k_counts[l]} |")

open(OUT_MD, "w").write("\n".join(lines))
print("\n".join(lines))
print(f"\nwrote {OUT_MD}")
