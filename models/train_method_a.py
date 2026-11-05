"""Method A: fine-tune DistilBERT-base-uncased on annotation/silver_labels.csv (400 contexts,
Claude pass-3 labels), evaluate on evaluation/gold.csv (68 Kavini-verified contexts).

Report macro-F1, per-class F1, confusion matrix. Save model + results to evaluation/.
Trade-off: DistilBERT is lighter than Legal-BERT or DeBERTa-v3-base; note as limitation.
"""
import csv
import json
import os
import sys
from collections import Counter

import numpy as np
import torch
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SILVER = os.path.join(ROOT, "annotation", "silver_labels.csv")
GOLD = os.path.join(ROOT, "evaluation", "gold.csv")
OUT = os.path.join(ROOT, "evaluation")

MODEL = "distilbert-base-uncased"
LABELS = ["followed/applied", "distinguished", "doubted/overruled", "neutral"]
L2I = {l: i for i, l in enumerate(LABELS)}
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
EPOCHS = 6
BATCH = 16
LR = 3e-5
MAX_LEN = 384


def load_csv(path, label_col):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    return [(r["context"], L2I[r[label_col]]) for r in rows if r[label_col] in L2I]


class DS(Dataset):
    def __init__(self, data, tok):
        self.data = data
        self.tok = tok

    def __len__(self):
        return len(self.data)

    def __getitem__(self, i):
        t, y = self.data[i]
        enc = self.tok(t, truncation=True, max_length=MAX_LEN, padding="max_length", return_tensors="pt")
        return {"input_ids": enc["input_ids"][0], "attention_mask": enc["attention_mask"][0],
                "labels": torch.tensor(y, dtype=torch.long)}


def main():
    train = load_csv(SILVER, "claude_label")
    test = load_csv(GOLD, "kavini_label")
    print(f"1) train {len(train)}  |  test {len(test)}  |  device {DEVICE}")
    print(f"   train dist: {Counter(l for _, l in train)}")
    print(f"   test dist:  {Counter(l for _, l in test)}")

    counts = Counter(l for _, l in train)
    total = sum(counts.values())
    weights = torch.tensor([total / (len(LABELS) * counts[i]) for i in range(len(LABELS))],
                           dtype=torch.float32).to(DEVICE)
    print(f"2) class weights: {[round(float(w), 2) for w in weights]}")

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL, num_labels=len(LABELS)).to(DEVICE)
    train_dl = DataLoader(DS(train, tok), batch_size=BATCH, shuffle=True)
    test_dl = DataLoader(DS(test, tok), batch_size=BATCH)
    opt = torch.optim.AdamW(model.parameters(), lr=LR)
    lossfn = torch.nn.CrossEntropyLoss(weight=weights)

    for ep in range(EPOCHS):
        model.train()
        totloss = 0.0
        for b in train_dl:
            b = {k: v.to(DEVICE) for k, v in b.items()}
            opt.zero_grad()
            logits = model(input_ids=b["input_ids"], attention_mask=b["attention_mask"]).logits
            loss = lossfn(logits, b["labels"])
            loss.backward()
            opt.step()
            totloss += loss.item()
        print(f"   epoch {ep+1}/{EPOCHS}  loss {totloss/len(train_dl):.3f}")

    model.eval()
    preds, gold = [], []
    with torch.no_grad():
        for b in test_dl:
            b_in = {k: v.to(DEVICE) for k, v in b.items() if k != "labels"}
            logits = model(**b_in).logits.cpu().numpy()
            preds.extend(logits.argmax(axis=1).tolist())
            gold.extend(b["labels"].tolist())

    macro = f1_score(gold, preds, average="macro", labels=list(range(len(LABELS))), zero_division=0)
    per = f1_score(gold, preds, average=None, labels=list(range(len(LABELS))), zero_division=0)
    cm = confusion_matrix(gold, preds, labels=list(range(len(LABELS))))
    report = classification_report(gold, preds, target_names=LABELS, labels=list(range(len(LABELS))),
                                   zero_division=0, digits=3)
    print(report)

    md = [f"# Method A - DistilBERT fine-tuned on silver labels\n",
          f"- Train: {len(train)} silver rows (Claude pass-3)",
          f"- Test: {len(test)} Kavini gold rows (50 + 20, deduped)",
          f"- Device: {DEVICE}  |  epochs: {EPOCHS}  |  batch: {BATCH}  |  lr: {LR}\n",
          f"- **Macro-F1: {macro:.3f}**\n",
          "## Per-class F1\n", "| label | F1 | support in test |", "|---|---|---|"]
    test_counts = Counter(gold)
    for i, l in enumerate(LABELS):
        md.append(f"| {l} | {per[i]:.3f} | {test_counts[i]} |")
    md.append("\n## Confusion matrix (rows=gold, cols=predicted)\n")
    md.append("| | " + " | ".join(LABELS) + " |")
    md.append("|---|" + "---|" * len(LABELS))
    for i, l in enumerate(LABELS):
        md.append("| " + l + " | " + " | ".join(str(int(cm[i, j])) for j in range(len(LABELS))) + " |")
    md.append("\n```\n" + report + "\n```")
    open(os.path.join(OUT, "method_a_distilbert.md"), "w").write("\n".join(md))
    with open(os.path.join(OUT, "method_a_predictions.json"), "w") as f:
        json.dump({"gold": gold, "pred": preds, "labels": LABELS}, f)
    print(f"4) wrote evaluation/method_a_distilbert.md")


if __name__ == "__main__":
    main()
