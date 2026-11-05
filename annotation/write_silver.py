"""Write annotation/silver_labels.csv (400 contexts with Claude's labels) and
annotation/gold_check_50.csv (random 50 for Kavini to accept/correct)."""
import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _claude_labels import LABELS

HERE = os.path.dirname(__file__)
rows = list(csv.DictReader(open(os.path.join(HERE, "label_set.csv"))))

silver_path = os.path.join(HERE, "silver_labels.csv")
with open(silver_path, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "citing_case", "cited_target", "cited_raw", "case_name",
                "report_key", "case_no", "context", "claude_label", "labelled_by"])
    for r in rows:
        w.writerow([r["id"], r["citing_case"], r["cited_target"], r["cited_raw"],
                    r["case_name"], r["report_key"], r["case_no"],
                    r["context"], LABELS[int(r["id"])], "Claude (Anthropic)"])

random.seed(42)
sample = random.sample(rows, 50)
gold_path = os.path.join(HERE, "gold_check_50.csv")
with open(gold_path, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "cited_raw", "context", "claude_label", "kavini_label"])
    for r in sample:
        ctx = r["context"].strip().replace("\n", " ")
        raw = r["cited_raw"]
        i = ctx.find(raw[:30]) if raw else -1
        if i < 0:
            i = max(0, len(ctx) // 2 - 180)
        a = max(0, i - 180)
        b = min(len(ctx), i + len(raw) + 220)
        w.writerow([r["id"], raw, ctx[a:b], LABELS[int(r["id"])], ""])

print(f"wrote {silver_path} ({len(rows)} rows)")
print(f"wrote {gold_path} (50 rows)")
