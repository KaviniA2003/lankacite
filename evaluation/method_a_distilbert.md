# Method A - DistilBERT fine-tuned on silver labels

- Train: 400 silver rows (Claude pass-3)
- Test: 68 Kavini gold rows (50 + 20, deduped)
- Device: mps  |  epochs: 6  |  batch: 16  |  lr: 3e-05

- **Macro-F1: 0.551**

## Per-class F1

| label | F1 | support in test |
|---|---|---|
| followed/applied | 0.634 | 23 |
| distinguished | 0.750 | 4 |
| doubted/overruled | 0.000 | 3 |
| neutral | 0.819 | 38 |

## Confusion matrix (rows=gold, cols=predicted)

| | followed/applied | distinguished | doubted/overruled | neutral |
|---|---|---|---|---|
| followed/applied | 13 | 0 | 1 | 9 |
| distinguished | 1 | 3 | 0 | 0 |
| doubted/overruled | 1 | 0 | 0 | 2 |
| neutral | 3 | 1 | 0 | 34 |

```
                   precision    recall  f1-score   support

 followed/applied      0.722     0.565     0.634        23
    distinguished      0.750     0.750     0.750         4
doubted/overruled      0.000     0.000     0.000         3
          neutral      0.756     0.895     0.819        38

         accuracy                          0.735        68
        macro avg      0.557     0.552     0.551        68
     weighted avg      0.711     0.735     0.716        68

```