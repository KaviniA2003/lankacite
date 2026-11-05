# Hallucination probe - Llama-3.2-3B hidden states (with controls)

Labels from automatic audit (rebuilt after name-check fix).
- real = verified-correct or exists-name-unverified (41)
- fake = name-mismatch or verified-wrong-details (77)
- citations with ambiguous verdict dropped
- CV: GroupKFold by q_id so no question appears in both train and test

## Results

| probe | input | N | AUROC |
|---|---|---|---|
| main | last-token hidden state, layer 20 | 118 | **1.000** |
| baseline - surface features only | has_report_key, has_case_no, has_case_name, raw_length | 118 | 0.670 |
| shuffled-label control | hidden state, layer 20, labels permuted | 118 | 0.529 |
| report-key citations only | hidden state, layer 20 | 94 | 0.993 |
| case-number citations only | hidden state, layer 20 | 24 | nan |

## Per-layer AUROC (main probe)

| layer | AUROC |
|---|---|
| 0 | 0.992 |
| 1 | 0.995 |
| 2 | 0.993 |
| 3 | 0.992 |
| 4 | 0.987 |
| 5 | 0.995 |
| 6 | 0.993 |
| 7 | 0.993 |
| 8 | 0.993 |
| 9 | 0.992 |
| 10 | 0.993 |
| 11 | 0.994 |
| 12 | 0.996 |
| 13 | 0.996 |
| 14 | 0.996 |
| 15 | 0.991 |
| 16 | 0.996 |
| 17 | 0.996 |
| 18 | 0.992 |
| 19 | 0.992 |
| 20 | 1.000 |
| 21 | 0.996 |
| 22 | 0.991 |
| 23 | 0.993 |
| 24 | 0.989 |
| 25 | 0.988 |
| 26 | 0.987 |
| 27 | 0.987 |
| 28 | 0.987 |