"""Hallucination probe on Llama hidden states with 4 controls.

Labels come from the automatic audit (rebuilt after the name-check tightening):
    real = verified-correct or exists-name-unverified
    fake = name-mismatch or verified-wrong-details
    skip = not-in-corpus or undecidable

Four AUROCs:
  (main)       logistic regression on each layer's last-token hidden state,
                GroupKFold by q_id (same question's citations never in both folds)
  (baseline)   logistic regression on 4 surface features: has_report_key, has_case_no,
                has_case_name, raw_length (bucketed) - if this reaches ~ main the probe
                is only detecting citation format, not model-internal truth
  (shuffled)   main probe with labels shuffled - should be ~0.5
  (report-only) main probe restricted to citations whose format is a report key only
  (case-no-only) main probe restricted to case-number citations only

All numbers go into evaluation/probe.md.
"""
import csv
import json
import os
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
HS = os.path.join(HERE, "hidden_states")
AUDIT = os.path.join(ROOT, "evaluation", "audit_results_per_citation.csv")
CJL = os.path.join(HS, "citations.jsonl")
OUT = os.path.join(ROOT, "evaluation")

REAL = {"verified-correct", "verified-correct-external"}
FAKE = {"name-mismatch", "wrong-case", "not-found-anywhere"}
REQUIRE_NAME = True   # only cleanly-labelled citations (AI gave a name)

labels = {}  # (q_id, raw) -> 1 / 0
format_hint = {}
with open(AUDIT) as f:
    for r in csv.DictReader(f):
        if r["model"] != "llama-3.2-3b":
            continue
        if REQUIRE_NAME and not r.get("case_name"):
            continue
        v = r["verdict"]
        if v in REAL:
            labels[(r["q_id"], r["raw"])] = 1
        elif v in FAKE:
            labels[(r["q_id"], r["raw"])] = 0
        format_hint[(r["q_id"], r["raw"])] = (
            bool(r["report_key"]), bool(r["case_no"]), bool(r["case_name"]))

X, y, groups, fmts = [], [], [], []
seen = set()
with open(CJL) as f:
    for line in f:
        if not line.strip():
            continue
        d = json.loads(line)
        key = (d["q_id"], d["raw"])
        if key in seen or key not in labels:
            continue
        seen.add(key)
        p = os.path.join(HS, f"{d['q_id']}.npy")
        if not os.path.exists(p):
            continue
        arr = np.load(p)
        if d["idx"] >= arr.shape[0]:
            continue
        X.append(arr[d["idx"]])
        y.append(labels[key])
        groups.append(f"{d['q_id']}||{d['raw']}")  # group by (q_id, raw)
        fmts.append(format_hint.get(key, (False, False, False)))

X = np.stack(X)
y = np.array(y)
groups = np.array(groups)
fmts = np.array(fmts, dtype=int)    # (N, 3): has_rk, has_cn, has_name
raw_lens = np.array([len(k[1]) for k in seen])  # len of raw string
print(f"1) N={len(y)}  real={int(y.sum())}  fake={int((1-y).sum())}  groups(q_ids)={len(set(groups))}")


def cv_auroc(Xmat, Y, G, n_splits=5, C=0.1):
    # G may be a 2D array of (q_id, raw) tuples; GroupKFold needs 1D labels.
    if hasattr(G, "ndim") and G.ndim == 2:
        G = np.array([f"{a}||{b}" for a, b in G])
    if n_splits > len(set(G)):
        n_splits = len(set(G))
    gkf = GroupKFold(n_splits=n_splits)
    aurocs = []
    for tr, te in gkf.split(Xmat, Y, groups=G):
        if len(set(Y[te])) < 2:
            continue
        clf = LogisticRegression(max_iter=1000, C=C)
        clf.fit(Xmat[tr], Y[tr])
        aurocs.append(roc_auc_score(Y[te], clf.predict_proba(Xmat[te])[:, 1]))
    return float(np.mean(aurocs)) if aurocs else float("nan")


def surface_features():
    # bucket length into 4 bins
    buckets = np.digitize(raw_lens, [15, 25, 40])
    onehot = np.zeros((len(raw_lens), 4))
    onehot[np.arange(len(raw_lens)), buckets] = 1
    return np.hstack([fmts, onehot]).astype(float)


# ---- main: per-layer GroupKFold -----------------------------------------
n_layers = X.shape[1]
main_by_layer = [cv_auroc(X[:, L, :], y, groups) for L in range(n_layers)]
best_layer = int(np.nanargmax(main_by_layer))
main_best = main_by_layer[best_layer]
print(f"2) main (GroupKFold): best layer {best_layer}  AUROC {main_best:.3f}")

# ---- baseline: surface features (same GroupKFold) -----------------------
sf = surface_features()
base_auroc = cv_auroc(sf, y, groups)
print(f"3) baseline (surface features only): AUROC {base_auroc:.3f}")

# ---- shuffled-label control --------------------------------------------
rng = np.random.default_rng(42)
y_shuf = y.copy()
rng.shuffle(y_shuf)
shuf_auroc = cv_auroc(X[:, best_layer, :], y_shuf, groups)
print(f"4) shuffled-label control (best layer): AUROC {shuf_auroc:.3f}")

# ---- format-restricted subsets -----------------------------------------
report_mask = (fmts[:, 0] == 1) & (fmts[:, 1] == 0)
cn_mask = (fmts[:, 1] == 1) & (fmts[:, 0] == 0)


def restricted(mask):
    if mask.sum() < 20:
        return float("nan"), int(mask.sum())
    yy = y[mask]
    if len(set(yy)) < 2 or min(Counter(yy).values()) < 5:
        return float("nan"), int(mask.sum())
    try:
        au = cv_auroc(X[mask][:, best_layer, :], yy, groups[mask])
    except ValueError:
        au = float("nan")
    return au, int(mask.sum())


rep_au, rep_n = restricted(report_mask)
cn_au, cn_n = restricted(cn_mask)
print(f"5) report-only probe (N={rep_n}): AUROC {rep_au:.3f}")
print(f"6) case-no-only probe (N={cn_n}): AUROC {cn_au:.3f}")

# ---- write report ------------------------------------------------------
md = ["# Hallucination probe - Llama-3.2-3B hidden states (with controls)\n",
      f"Labels from automatic audit (rebuilt after name-check fix).",
      f"- real = verified-correct or exists-name-unverified ({int(y.sum())})",
      f"- fake = name-mismatch or verified-wrong-details ({int((1-y).sum())})",
      f"- citations with ambiguous verdict dropped",
      f"- CV: GroupKFold by q_id so no question appears in both train and test\n",
      "## Results\n",
      "| probe | input | N | AUROC |",
      "|---|---|---|---|",
      f"| main | last-token hidden state, layer {best_layer} | {len(y)} | **{main_best:.3f}** |",
      f"| baseline - surface features only | has_report_key, has_case_no, has_case_name, raw_length | {len(y)} | {base_auroc:.3f} |",
      f"| shuffled-label control | hidden state, layer {best_layer}, labels permuted | {len(y)} | {shuf_auroc:.3f} |",
      f"| report-key citations only | hidden state, layer {best_layer} | {rep_n} | {rep_au:.3f} |",
      f"| case-number citations only | hidden state, layer {best_layer} | {cn_n} | {cn_au:.3f} |",
      "",
      "## Per-layer AUROC (main probe)\n",
      "| layer | AUROC |", "|---|---|"]
for i, a in enumerate(main_by_layer):
    md.append(f"| {i} | {a:.3f} |")
open(os.path.join(OUT, "probe.md"), "w").write("\n".join(md))

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(range(n_layers), main_by_layer, marker="o", label="main")
ax.axhline(base_auroc, linestyle="--", color="orange", label=f"surface baseline {base_auroc:.2f}")
ax.axhline(shuf_auroc, linestyle=":", color="grey", label=f"shuffled {shuf_auroc:.2f}")
ax.axhline(0.5, linestyle="--", color="black", alpha=0.3)
ax.set_xlabel("layer"); ax.set_ylabel("AUROC (GroupKFold by q_id)")
ax.set_title(f"Probe vs controls (N={len(y)})")
ax.legend(fontsize=8); ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "probe_auroc_by_layer.png"), dpi=140)
with open(os.path.join(OUT, "probe_auroc_by_layer.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["layer", "auroc"])
    for i, a in enumerate(main_by_layer):
        w.writerow([i, f"{a:.4f}"])
print("7) wrote evaluation/probe.md + .png + .csv")
