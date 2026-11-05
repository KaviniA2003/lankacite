# Claude vs Kavini - gold 50 agreement

- Rows in file: 50
- Near-duplicate groups collapsed: 2 (ids: [['8871', '8836'], ['8985', '8835']])
- Rows scored (after dedupe): 48
- Agreement: 27/48 = 56.2%
- Cohen's kappa: 0.318

## Confusion matrix (rows = Claude, cols = Kavini)

| | followed/applied | distinguished | doubted/overruled | neutral |
|---|---|---|---|---|
| followed/applied | 14 | 0 | 0 | 13 |
| distinguished | 1 | 3 | 0 | 1 |
| doubted/overruled | 1 | 0 | 0 | 3 |
| neutral | 2 | 0 | 0 | 10 |

## Per-label support

| label | Claude | Kavini |
|---|---|---|
| followed/applied | 27 | 18 |
| distinguished | 5 | 3 |
| doubted/overruled | 4 | 0 |
| neutral | 12 | 27 |