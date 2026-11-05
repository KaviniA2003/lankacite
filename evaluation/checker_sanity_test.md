# Sanity test - 6 pilot Sri Lankan citations

All six are real cases. We run the citation checker and show its verdict + reason.

| raw citation | extracted name | verdict | reason |
|---|---|---|---|
| SC FR 256/2017 | Wijerathna v Sri Lanka Ports Authority | **verified-correct** | case_no SC_FR_256_2017 matches judgment in DB (Wijerathna v. Sri Lanka Ports Authority and Others) |
| SC FR 55/2017 | Perera v Dissanayake | **verified-correct** | case_no SC_FR_55_2017 matches judgment in DB (Perera v. Dissanayake and Others) |
| [1993] 1 Sri LR 39 | Perera v Cyril Ranatunga | **verified-correct** | report_key match + name match (Perera v Ranatunga) |
| [1997] 2 Sri LR 98 | Ratnayake v Attorney General | **verified-correct-external** | found in lankalaw index: Ratnayake v. Attorney General |
| SC FR 322/2011 | - | **number-exists-unverified** | case_no SC_FR_322_2011 exists in DB (Randeniya and Others v. Fernando and Others); AI gave no case name |
| SC 452/2001 | Dayaratne v National Savings Bank | **real-name-wrong-citation** | name matches an external case (Dayaratne and Others v. National Savings Bank and Others) but citation SC_APPEAL_452_2001 does not |

**Result: 3/6 immediately marked as real; the rest are not-in-corpus or undecidable but NOT labelled fake.**

Notes:
- Rule 1: case number match in judgments.db -> verified-correct even without a stored name.
- Rule 2: report key in graph but DB has no case name -> exists-name-unverified (not wrong-details).
- Rule 3: pre-2009 year not in graph -> not-in-corpus (we only hold 2009-2025).
- Only labels a case 'name-mismatch' / 'verified-wrong-details' when a stored name conflicts.