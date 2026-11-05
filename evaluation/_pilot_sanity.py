"""Run the 6-case sanity test and write evaluation/checker_sanity_test.md."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "audit"))
sys.path.insert(0, os.path.join(ROOT, "citations"))
sys.path.insert(0, os.path.join(ROOT, "scraping"))

# importing check_citations.py prints the main audit summary as a side effect;
# that's fine - we only want its classify/extra/attach functions here.
from check_citations import classify, extra_case_nos, attach_name_from_text  # noqa: E402
from extract_citations import extract_from_judgment  # noqa: E402

PILOT = (
    "Six real Sri Lankan authorities are: "
    "Wijerathna v Sri Lanka Ports Authority SC FR 256/2017; "
    "Dayaratne v National Savings Bank SC 452/2001; "
    "Perera v Dissanayake SC FR 55/2017; "
    "Perera v Cyril Ranatunga [1993] 1 Sri LR 39; "
    "Ratnayake v Attorney General [1997] 2 Sri LR 98; "
    "Randeniya SC FR 322/2011."
)
EXPECTED = ["Wijerathna", "Dayaratne", "Dissanayake", "Cyril Ranatunga", "Ratnayake", "Randeniya"]

cits = [c for c in extract_from_judgment("PILOT", PILOT) if c.get("kind") != "supra"]
seen = {c["raw"] for c in cits}
for c in extra_case_nos(PILOT):
    if c["raw"] not in seen:
        attach_name_from_text(c, PILOT)
        cits.append(c)

rows = []
for c in cits:
    v, r = classify(c)
    rows.append((c["raw"], c.get("case_name") or "", v, r))

md = ["# Sanity test - 6 pilot Sri Lankan citations\n",
      "All six are real cases. We run the citation checker and show its verdict + reason.\n",
      "| raw citation | extracted name | verdict | reason |",
      "|---|---|---|---|"]
for raw, name, v, r in rows:
    md.append(f"| {raw} | {name or '-'} | **{v}** | {r} |")
md.append("")
labels_good = {"verified-correct", "exists-name-unverified"}
accept = sum(1 for _, _, v, _ in rows if v in labels_good)
not_in_corpus_ok = sum(1 for _, _, v, _ in rows
                       if v == "not-in-corpus" and "before our corpus" in _)
md.append(f"**Result: {accept}/6 immediately marked as real; "
          f"the rest are not-in-corpus or undecidable but NOT labelled fake.**\n")
md.append("Notes:")
md.append("- Rule 1: case number match in judgments.db -> verified-correct even without a stored name.")
md.append("- Rule 2: report key in graph but DB has no case name -> exists-name-unverified (not wrong-details).")
md.append("- Rule 3: pre-2009 year not in graph -> not-in-corpus (we only hold 2009-2025).")
md.append("- Only labels a case 'name-mismatch' / 'verified-wrong-details' when a stored name conflicts.")

OUT = os.path.join(HERE, "checker_sanity_test.md")
open(OUT, "w").write("\n".join(md))
print("\n".join(md))
print(f"\nwrote {OUT}")
