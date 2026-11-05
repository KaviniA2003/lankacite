"""Score Claude's silver labels against Kavini's gold 50.

Treat kavini_label == "OK" as agreement with claude_label (same label).
Collapse near-duplicate rows (identical context between pairs) when scoring.
Report: n, agreement, Cohen's kappa, confusion matrix.
"""
import csv
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, "..", "annotation", "gold_check_50.csv")
OUT_MD = os.path.join(HERE, "gold_50_agreement.md")

LABELS = ["followed/applied", "distinguished", "doubted/overruled", "neutral"]

rows = list(csv.DictReader(open(GOLD, encoding="utf-8")))
pairs = []  # (claude, kavini) after normalising "OK"
for r in rows:
    k = r["kavini_label"].strip()
    c = r["claude_label"].strip()
    kavini = c if k.lower() == "ok" else k
    pairs.append((r["id"], c, kavini, r["context"]))

# near-duplicates: same context text (strip spaces) OR known-identical rows
by_ctx = defaultdict(list)
for pid, c, k, ctx in pairs:
    by_ctx[" ".join(ctx.split())].append(pid)
dups = {ids[0]: ids for ids in by_ctx.values() if len(ids) > 1}

keep_ids, seen = [], set()
for pid, _, _, ctx in pairs:
    key = " ".join(ctx.split())
    if key in seen:
        continue
    seen.add(key)
    keep_ids.append(pid)

scored = [(pid, c, k) for (pid, c, k, _) in pairs if pid in keep_ids]
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

lines = []
lines.append("# Claude vs Kavini - gold 50 agreement\n")
lines.append(f"- Rows in file: {len(pairs)}")
lines.append(f"- Near-duplicate groups collapsed: {len(dups)} (ids: {[v for v in dups.values()]})")
lines.append(f"- Rows scored (after dedupe): {n}")
lines.append(f"- Agreement: {agree}/{n} = {100 * po:.1f}%")
lines.append(f"- Cohen's kappa: {kappa:.3f}\n")
lines.append("## Confusion matrix (rows = Claude, cols = Kavini)\n")
lines.append("| | " + " | ".join(LABELS) + " |")
lines.append("|---|" + "---|" * len(LABELS))
for a in LABELS:
    lines.append("| " + a + " | " + " | ".join(str(cm[a][b]) for b in LABELS) + " |")
lines.append("")
lines.append("## Per-label support\n")
lines.append("| label | Claude | Kavini |")
lines.append("|---|---|---|")
for l in LABELS:
    lines.append(f"| {l} | {c_counts[l]} | {k_counts[l]} |")

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\n".join(lines))
print(f"\nwrote {OUT_MD}")
