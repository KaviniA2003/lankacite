"""Method B: zero-shot treatment classification with local Llama-3.2-3B-Instruct.

For each gold row (68, Kavini-verified), prompt the model to choose one of four labels.
Score macro-F1, per-class F1, confusion matrix against Kavini.
"""
import csv
import json
import os
import re
import sys
from collections import Counter

import torch
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
GOLD = os.path.join(ROOT, "evaluation", "gold.csv")
OUT_MD = os.path.join(ROOT, "evaluation", "method_b_llama.md")

MODEL = "unsloth/Llama-3.2-3B-Instruct"
LABELS = ["followed/applied", "distinguished", "doubted/overruled", "neutral"]
L2I = {l: i for i, l in enumerate(LABELS)}

SYSTEM = (
    "You classify how a Sri Lankan court treats a case it cites. Choose exactly one of:\n"
    "  followed/applied   - the current judge accepts or applies the cited case as authority,\n"
    "                       EVEN inside a parenthetical list.\n"
    "  distinguished      - the current court distinguishes the cited case from the facts at hand.\n"
    "  doubted/overruled  - the current court overrules, doubts, or calls it per incuriam.\n"
    "  neutral            - cited by counsel, only described/reported, inside a stated question of law,\n"
    "                       or part of a list of mere examples.\n"
    "Reply with ONLY the label, nothing else."
)


def prompt(context, raw):
    return (f"Context (±~400 chars around the citation):\n{context}\n\n"
            f"Cited case raw text: {raw}\n\nLabel:")


def parse(text):
    t = text.strip().lower()
    for l in LABELS:
        if l in t:
            return l
    if "overrul" in t or "doubt" in t or "incuriam" in t:
        return "doubted/overruled"
    if "distinguish" in t:
        return "distinguished"
    if "follow" in t or "appl" in t:
        return "followed/applied"
    return "neutral"


def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float16).to(device).eval()
    print(f"1) Llama on {device}")

    rows = list(csv.DictReader(open(GOLD)))
    print(f"2) {len(rows)} gold rows")

    gold, pred = [], []
    for i, r in enumerate(rows, 1):
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt(r["context"], r["cited_raw"])}]
        ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt",
                                      return_dict=True)["input_ids"].to(device)
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=16, do_sample=False, temperature=None,
                                 top_p=None, pad_token_id=tok.eos_token_id)
        txt = tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)
        p = parse(txt)
        g = r["kavini_label"]
        gold.append(L2I[g]); pred.append(L2I[p])
        if i % 10 == 0:
            print(f"   {i}/{len(rows)}", flush=True)

    labels_idx = list(range(len(LABELS)))
    macro = f1_score(gold, pred, average="macro", labels=labels_idx, zero_division=0)
    per = f1_score(gold, pred, average=None, labels=labels_idx, zero_division=0)
    cm = confusion_matrix(gold, pred, labels=labels_idx)
    report = classification_report(gold, pred, target_names=LABELS, labels=labels_idx,
                                   zero_division=0, digits=3)
    print(report)

    counts = Counter(gold)
    md = [f"# Method B - Llama-3.2-3B zero-shot\n",
          f"- Test: {len(rows)} Kavini gold rows",
          f"- Device: {device}\n",
          f"- **Macro-F1: {macro:.3f}**\n",
          "## Per-class F1\n", "| label | F1 | support in test |", "|---|---|---|"]
    for i, l in enumerate(LABELS):
        md.append(f"| {l} | {per[i]:.3f} | {counts[i]} |")
    md.append("\n## Confusion matrix (rows=gold, cols=predicted)\n")
    md.append("| | " + " | ".join(LABELS) + " |")
    md.append("|---|" + "---|" * len(LABELS))
    for i, l in enumerate(LABELS):
        md.append("| " + l + " | " + " | ".join(str(int(cm[i, j])) for j in range(len(LABELS))) + " |")
    md.append("\n```\n" + report + "\n```")
    open(OUT_MD, "w").write("\n".join(md))
    print(f"3) wrote {OUT_MD}")


if __name__ == "__main__":
    main()
