"""Pass 3 silver labels.

Kavini's rule (explicit):
  followed/applied = case cited as authority for a proposition the CURRENT judge accepts,
                     EVEN inside a parenthetical list.
  neutral         = counsel's citations, cases only described/reported, cases inside a
                     stated question of law, lists of mere examples.
  distinguished   = the CURRENT court distinguishes the cited case.
  doubted/overruled = the CURRENT court overrules / doubts / calls per incuriam.
                      (Counsel-argued "wrongly decided" => neutral.)

Rules are generic - no gold instance is used as an example.
"""
import csv
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _claude_labels import LABELS as V1

ROWS = list(csv.DictReader(open(os.path.join(HERE, "label_set.csv"), encoding="utf-8")))

# ---- preceding-frame patterns ----
COUNSEL_FRAME = re.compile(
    r"(learned\s+(?:President'?s\s+)?Counsel|President'?s\s+Counsel|"
    r"State\s+Counsel|Deputy\s+Solicitor\s+General|DSG|Solicitor\s+General|"
    r"Counsel\s+for\s+the\s+(Appellant|Respondent|Petitioner|Defendant|Plaintiff|1st|2nd|3rd|4th|5th)|"
    r"\bAppellant[s']*\s+submitted|\bPetitioner[s']*\s+(?:argued|contended|submitted|urged|rel(?:y|ied))|"
    r"\bRespondent[s']*\s+(?:argued|contended|submitted)|"
    r"\bit\s+was\s+submitted\b|\bit\s+was\s+argued\b|\bit\s+was\s+contended\b|"
    r"\bwas\s+submitted\s+that\b|\bwas\s+argued\s+that\b|"
    r"\brelying\s+on\b|\brelies\s+on\b|\brelied\s+on\b|\bcited\s+the\s+(?:case|judgment|cases|judgments|decisions|dicta)\b|"
    r"\bbrought\s+to\s+(?:the|our)\s+attention\b|\bdrew\s+(?:the|our)\s+attention\b|"
    r"\bquoted\s+the\s+dicta\b|\binvited\s+this\s+Court\b|\burged\s+(?:this|the)\s+Court\b)",
    re.I)

JUDGE_FRAME = re.compile(
    r"(this\s+Court\s+(?:has\s+)?(?:held|observed|recognised|recognized|has\s+(?:recognised|recognized|held)|has\s+taken|observed\s+that)|"
    r"the\s+Supreme\s+Court\s+(?:has\s+)?(?:held|observed|held\s+that)|"
    r"it\s+was\s+held\s+(?:that|in)|was\s+held\s+(?:by|in|that)|held\s+as\s+follows|held\s+in\s+the\s+following|"
    r"(?:as|where)\s+(?:was\s+)?held\s+(?:by|in)|"
    r"(?:J\.?,?|CJ\.?|C\.?J\.?,?|ACJ\.?|P\.?C\.?,?\s*J\.?)\s+(?:held|observed|stated|explained|remarked|commented|described|noted|pointed\s+out|said|wrote)|"
    r"\bper\s+[A-Z][a-z]+\s+J\.?|"
    r"their\s+Lordships|his\s+Lordship\s+(?:held|observed|stated|wrote|said)|"
    r"\bapproved\s+(?:the|by)\b|\bquoted\s+with\s+approval\b|"
    r"\baccepted\s+the\b|\bendorsed\b|\bapproving\b|\baffirming\b|"
    r"\bI\s+(?:hold|observe|accept|agree|wish\s+to\s+quote|respectfully)\b|\bin\s+my\s+view\b|"
    r"\bit\s+is\s+(?:now\s+)?well[-\s]?settled\b|\bwell\s+established\b|\bsettled\s+law\b|"
    r"\bOur\s+Courts\s+have\b|\bOur\s+Courts\s+interpret\b|\bthis\s+Court\s+recognizes\b|"
    r"\bLord\s+[A-Z][a-z]+\s+(?:said|held|stated|observed|described)|"
    r"\bwas\s+followed\s+(?:in|by)\b|\bhas\s+been\s+followed\b|\bwas\s+adopted\b|\bwere\s+adopted\b|"
    r"\bapt\s+to\s+cite\b|\bapt\s+to\s+refer\b|\bthis\s+Court\s+adopts\b|"
    r"\bI\s+shall\s+(?:refer|quote)\b|\bI\s+wish\s+to\s+(?:quote|refer|refer\s+to)\b|"
    r"\bI\s+shall\s+now\b|\bthe\s+above\s+principle\b|\bthe\s+above\s+dicta\b|"
    r"\bit\s+is\s+apt\s+to\b)",
    re.I)

QUESTION_OF_LAW = re.compile(
    r"(question\s+of\s+law|issue\s+(?:to\s+be\s+decided|before\s+(?:this\s+)?Court)|"
    r"issue[s]?\s+that\s+arise[s]?)", re.I)

# distinguish/overrule by CURRENT court
CURR_DISTINGUISH = re.compile(
    r"(can\s+(?:easily\s+)?be\s+(?:clearly\s+)?distinguished|is\s+distinguishable\s+from|"
    r"must\s+be\s+distinguished|I\s+distinguish|we\s+distinguish|I\s+hold\s+that\s+.{0,30}\s+is\s+distinguishable|"
    r"should\s+have\s+distinguished|the\s+facts?\s+(?:is|are)\s+distinguishable|"
    r"facts?\s+of\s+(?:the|this)\s+case\s+(?:can|are)\s+(?:easily\s+)?distinguished|"
    r"the\s+above\s+case\s+can\s+(?:easily\s+)?be\s+distinguished)", re.I)

CURR_OVERRULE = re.compile(
    r"(we\s+(?:would\s+)?(?:accordingly\s+)?overrule|I\s+(?:would\s+)?overrule|"
    r"this\s+Court\s+overrule[sd]?|I\s+hold\s+.{0,40}\s+to\s+be\s+per\s+incuriam|"
    r"this\s+judgment\s+was\s+decided\s+per\s+incuriam|"
    r"cannot\s+be\s+treated\s+as\s+good\s+law|no\s+longer\s+good\s+law|"
    r"I\s+am\s+of\s+the\s+view\s+that\s+this\s+judgment\s+was\s+decided\s+per\s+incuriam)",
    re.I)


def classify(context: str, raw: str, old: str) -> str:
    # locate raw inside context
    i = context.find(raw[:40]) if raw else -1
    if i < 0:
        i = len(context) // 2
    pre = context[max(0, i - 260): i]
    post = context[i: i + len(raw) + 260]
    w = pre + post

    # strongest signals first: current court verb-of-treatment
    if CURR_OVERRULE.search(w):
        return "doubted/overruled"
    if CURR_DISTINGUISH.search(w):
        return "distinguished"

    # question-of-law framing -> neutral
    if QUESTION_OF_LAW.search(pre):
        return "neutral"

    # counsel-framed in the PRECEDING text -> neutral (even if judge voice appears after)
    if COUNSEL_FRAME.search(pre):
        return "neutral"

    # judge-framed authority anywhere in window -> followed/applied
    if JUDGE_FRAME.search(w):
        return "followed/applied"

    # footnote-only / bare parenthetical with no framing -> neutral
    return "neutral"


new = {int(r["id"]): classify(r["context"], r["cited_raw"], V1[int(r["id"])]) for r in ROWS}

changed = [pid for pid in V1 if V1[pid] != new[pid]]
print(f"1) {len(changed)}/{len(V1)} changed vs pass-1 (free-form)")
print(f"2) pass-1 dist: {Counter(V1.values())}")
print(f"3) pass-3 dist: {Counter(new.values())}")
flips = Counter((V1[p], new[p]) for p in changed)
for (a, b), c in flips.most_common(8):
    print(f"     {a:>18s}  ->  {b:<18s}  {c}")

out = os.path.join(HERE, "silver_labels.csv")
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "citing_case", "cited_target", "cited_raw", "case_name",
                "report_key", "case_no", "context", "claude_label", "labelled_by"])
    for r in ROWS:
        pid = int(r["id"])
        w.writerow([r["id"], r["citing_case"], r["cited_target"], r["cited_raw"],
                    r["case_name"], r["report_key"], r["case_no"], r["context"],
                    new[pid], "Claude (Anthropic) - pass 3 (Kavini's rule)"])
with open(os.path.join(HERE, "_claude_labels_v3.py"), "w") as f:
    f.write("LABELS = {\n")
    for pid, lbl in new.items():
        f.write(f"    {pid}: {lbl!r},\n")
    f.write("}\n")
print(f"4) wrote {out} + annotation/_claude_labels_v3.py")
