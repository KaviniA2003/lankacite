# Claude v2 (strict) vs Kavini - gold 50 agreement

- Rows in file: 50
- Near-duplicate groups collapsed: 2 (ids: [[8871, 8836], [8985, 8835]])
- Rows scored (after dedupe): 48
- Agreement: 32/48 = 66.7%
- Cohen's kappa: 0.386

## Confusion matrix (rows = Claude v2, cols = Kavini)

| | followed/applied | distinguished | doubted/overruled | neutral |
|---|---|---|---|---|
| followed/applied | 8 | 0 | 0 | 2 |
| distinguished | 0 | 2 | 0 | 1 |
| doubted/overruled | 1 | 0 | 0 | 2 |
| neutral | 9 | 1 | 0 | 22 |

## Per-label support

| label | Claude v2 | Kavini |
|---|---|---|
| followed/applied | 10 | 18 |
| distinguished | 3 | 3 |
| doubted/overruled | 3 | 0 |
| neutral | 32 | 27 |