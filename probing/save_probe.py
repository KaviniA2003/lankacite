"""Train the final probe on ALL clean-subset Llama citations and save with joblib.

Used by the 'Ask LankaCite' tab of the app for live hallucination warnings.
"""
import csv
import json
import os

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
HS = os.path.join(HERE, "hidden_states")
AUDIT = os.path.join(ROOT, "evaluation", "audit_results_per_citation.csv")
CJL = os.path.join(HS, "citations.jsonl")
OUT = os.path.join(HERE, "probe.joblib")
LAYER = 20

REAL = {"verified-correct", "verified-correct-external"}
FAKE = {"name-mismatch", "wrong-case", "not-found-anywhere"}

labels = {}
for r in csv.DictReader(open(AUDIT)):
    if r["model"] != "llama-3.2-3b":
        continue
    if not r["case_name"]:
        continue  # clean-subset: AI gave a name
    if r["verdict"] in REAL:
        labels[(r["q_id"], r["raw"])] = 1
    elif r["verdict"] in FAKE:
        labels[(r["q_id"], r["raw"])] = 0

X, y = [], []
seen = set()
with open(CJL) as f:
    for line in f:
        if not line.strip():
            continue
        d = json.loads(line)
        k = (d["q_id"], d["raw"])
        if k in seen or k not in labels:
            continue
        seen.add(k)
        p = os.path.join(HS, f"{d['q_id']}.npy")
        if not os.path.exists(p):
            continue
        arr = np.load(p)
        if d["idx"] >= arr.shape[0]:
            continue
        X.append(arr[d["idx"], LAYER])
        y.append(labels[k])
X = np.stack(X).astype(np.float32)
y = np.array(y)
print(f"N={len(y)} (real={int(y.sum())}, fake={int((1-y).sum())}), layer={LAYER}")

clf = LogisticRegression(max_iter=2000, C=0.1)
clf.fit(X, y)
joblib.dump({"clf": clf, "layer": LAYER}, OUT)
print(f"wrote {OUT}")
