# Method B - Llama-3.2-3B zero-shot

- Test: 68 Kavini gold rows
- Device: mps

- **Macro-F1: 0.389**

## Per-class F1

| label | F1 | support in test |
|---|---|---|
| followed/applied | 0.565 | 23 |
| distinguished | 0.276 | 4 |
| doubted/overruled | 0.400 | 3 |
| neutral | 0.314 | 38 |

## Confusion matrix (rows=gold, cols=predicted)

| | followed/applied | distinguished | doubted/overruled | neutral |
|---|---|---|---|---|
| followed/applied | 13 | 3 | 2 | 5 |
| distinguished | 0 | 4 | 0 | 0 |
| doubted/overruled | 1 | 0 | 2 | 0 |
| neutral | 9 | 18 | 3 | 8 |

```
                   precision    recall  f1-score   support

 followed/applied      0.565     0.565     0.565        23
    distinguished      0.160     1.000     0.276         4
doubted/overruled      0.286     0.667     0.400         3
          neutral      0.615     0.211     0.314        38

         accuracy                          0.397        68
        macro avg      0.407     0.611     0.389        68
     weighted avg      0.557     0.397     0.400        68

```