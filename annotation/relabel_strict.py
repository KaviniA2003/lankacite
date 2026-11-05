"""Re-label the 400 silver contexts with a stricter rule:
  followed/applied -> ONLY when the CURRENT judge actively relies on or applies the case
  distinguished / doubted/overruled -> ONLY when the CURRENT citing judge is doing it
  else -> neutral (counsel citations, parenthetical lists, footnotes, pure description)

This does NOT re-read the gold 50; it applies the rule to ALL 400 contexts uniformly
(no example leakage - rules are pattern-based, not instance-based).

Writes annotation/silver_labels.csv (overwrites) and prints diff vs. Claude's first pass.
"""
import csv
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _claude_labels import LABELS as OLD

ROWS = list(csv.DictReader(open(os.path.join(HERE, "label_set.csv"), encoding="utf-8")))

# Patterns that indicate the sentence IS counsel/submission/footnote, not judge's own ruling.
COUNSEL = re.compile(
    r"(learned\s+(?:President'?s\s+)?Counsel|President'?s\s+Counsel|"
    r"State\s+Counsel|Deputy\s+Solicitor\s+General|DSG|Solicitor\s+General|"
    r"Counsel\s+for\s+the\s+(Appellant|Respondent|Petitioner|Defendant|Plaintiff|1st|2nd|3rd))",
    re.I)
COUNSEL_VERBS = re.compile(
    r"\b(relied\s+(?:up)?on|cited|submitted|contended|argued|brought\s+to|drew\s+(?:our|the)|"
    r"invited\s+this\s+Court|urged|quoted\s+the\s+dicta|has\s+(?:cited|quoted))\b", re.I)

# Judge-voice signals that a PAST judge ruled -> good followed/applied when combined with
# current court referring to that ruling as authority
JUDGE_VOICE = re.compile(
    r"(\bJ\.?,?\s+(?:held|observed|stated|explained|remarked|commented|described|noted|pointed\s+out|"
    r"said|observed\s+as\s+follows|stated\s+as\s+follows)\b|"
    r"\b(?:C\.?J\.?|CJ|ACJ)\s+(?:held|observed|stated|explained|said|noted)\b|"
    r"\b(?:P\.?\s*C\.?\s*,?\s*J\.?)\s+(?:held|observed|stated)\b|"
    r"\bthis\s+Court\s+(?:has\s+)?(?:held|observed|recognized|recognised|has\s+taken)\b|"
    r"\bwas\s+held\s+(?:by|in|that)\b|\bit\s+was\s+held\s+that\b|\bheld\s+as\s+follows\b|"
    r"\bquoted\s+with\s+approval\b|\bapproved\s+(?:the|by)\b|\bper\s+[A-Z][a-z]+\s+J\.?\b|"
    r"\bthe\s+Supreme\s+Court\s+(?:has\s+)?held\b|\btheir\s+Lordships\b|"
    r"\bhis\s+Lordship\s+(?:held|observed|stated|wrote)\b|"
    r"\bLord\s+[A-Z][a-z]+\s+(?:said|held|stated|observed|described)\b|"
    r"\bI\s+(?:hold|observe)\b|\bin\s+my\s+view\b|"
    r"\bapproving|\baffirming|\baccordingly\s+(?:follow|apply|hold)\b|"
    r"\bwas\s+followed\s+(?:in|by)\b|\bwas\s+adopted\b|\bwere\s+adopted\b|"
    r"\b(?:J\.?,?)\s+(?:in|at)\s+[A-Z]|"  # "Fernando J in Perera..." style
    r"\b[A-Z][a-z]+\s+J\.?,?\s+(?:held|observed|stated|explained|said|wrote|commented)\b)",
    re.I)

CURRENT_DISTINGUISH = re.compile(
    r"(can\s+(?:easily\s+)?be\s+(?:clearly\s+)?distinguished|is\s+distinguishable|"
    r"are\s+distinguishable|must\s+be\s+distinguished|I\s+distinguish|we\s+distinguish|"
    r"distinguish(?:ed|es)\s+the\s+(?:facts|case)\s+of|should\s+have\s+distinguished)", re.I)

CURRENT_OVERRULE = re.compile(
    r"(we\s+(?:would\s+)?(?:accordingly\s+)?overrule|I\s+(?:would\s+)?overrule|"
    r"is\s+per\s+incuriam|not\s+good\s+law|cannot\s+be\s+treated\s+as\s+good\s+law|"
    r"wrongly\s+decided|disapprov(?:ed|ing)|totally\s+disapproved)", re.I)

# Parenthetical / footnote markers
LIST_IN_BRACKET = re.compile(r"\[[^\]]{40,}\]")  # long bracketed content
SEMICOLON_LIST = re.compile(r";")
FOOTNOTE_MARK = re.compile(r"\b\d{1,3}\s+\[?\(?(19|20)\d{2}\)?\]?")


def window(context: str, raw: str, radius: int = 220) -> str:
    i = context.find(raw[:40]) if raw else -1
    if i < 0:
        i = max(0, len(context) // 2 - radius)
    return context[max(0, i - radius): i + len(raw) + radius]


def classify(context: str, raw: str, old: str) -> str:
    w = window(context, raw)
    # keep genuine current-court negatives
    if CURRENT_OVERRULE.search(w):
        # but only if the overruled target IS this cited case, which is hard to know.
        # keep the old label if it was doubted/overruled; else neutral
        if old == "doubted/overruled":
            return "doubted/overruled"
    if CURRENT_DISTINGUISH.search(w):
        if old == "distinguished":
            return "distinguished"
        # else allow upgrade to distinguished only if clear
        return "distinguished"

    # Strong JUDGE_VOICE wins unless the window is clearly counsel-ONLY
    # (counsel-verb appears AND no judge-voice signal at all).
    has_judge = bool(JUDGE_VOICE.search(w))
    has_counsel = bool(COUNSEL.search(w) and COUNSEL_VERBS.search(w))

    if has_counsel and not has_judge:
        return "neutral"

    # footnote / parenthetical list dominates window AND no judge voice
    semicolons = len(SEMICOLON_LIST.findall(w))
    footnotes = len(FOOTNOTE_MARK.findall(w))
    if not has_judge:
        if semicolons >= 2 and footnotes >= 2:
            return "neutral"
        for m in LIST_IN_BRACKET.finditer(w):
            if m.group(0).count(";") >= 2 or m.group(0).count(",") >= 4:
                return "neutral"

    if has_judge:
        return "followed/applied"

    # keep original label if it was non-followed
    if old in ("distinguished", "doubted/overruled"):
        return old if CURRENT_DISTINGUISH.search(w) or CURRENT_OVERRULE.search(w) else "neutral"

    # default: neutral (strict)
    return "neutral"


new_labels = {}
for r in ROWS:
    pid = int(r["id"])
    new_labels[pid] = classify(r["context"], r["cited_raw"], OLD[pid])

changed = [pid for pid in OLD if OLD[pid] != new_labels[pid]]
flips = Counter((OLD[pid], new_labels[pid]) for pid in changed)
print(f"1) {len(changed)}/{len(OLD)} labels changed")
print(f"2) old distribution: {Counter(OLD.values())}")
print(f"3) new distribution: {Counter(new_labels.values())}")
print("4) top flips:")
for (a, b), c in flips.most_common(10):
    print(f"     {a:>18s}  ->  {b:<18s}  {c}")

# overwrite silver_labels.csv
out = os.path.join(HERE, "silver_labels.csv")
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "citing_case", "cited_target", "cited_raw", "case_name",
                "report_key", "case_no", "context", "claude_label", "labelled_by"])
    for r in ROWS:
        pid = int(r["id"])
        w.writerow([r["id"], r["citing_case"], r["cited_target"], r["cited_raw"],
                    r["case_name"], r["report_key"], r["case_no"], r["context"],
                    new_labels[pid], "Claude (Anthropic) - strict pass v2"])
print(f"5) wrote {out}")

# also dump the new labels dict so downstream code can see pass-2
with open(os.path.join(HERE, "_claude_labels_v2.py"), "w") as f:
    f.write("# Pass 2: stricter rule (counsel/lists/footnotes = neutral)\n")
    f.write("LABELS = {\n")
    for pid, lbl in new_labels.items():
        f.write(f"    {pid}: {lbl!r},\n")
    f.write("}\n")
print("6) wrote annotation/_claude_labels_v2.py")
