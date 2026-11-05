"""Automatic audit of Sri Lankan case citations produced by ChatGPT (mini + 4o) and Llama.

Verdict categories (user's spec):
  verified-correct       - citation number resolves AND case name matches a DB record
  verified-wrong-details - citation number resolves but a detail differs (page, volume, year)
                           in DB; same case, wrong details  (rare without richer DB)
  name-mismatch          - citation number resolves to a DIFFERENT real case (likely fabricated)
  not-in-corpus          - cannot verify; not in our DB  (NOT the same as fake - may be real)
  undecidable            - partial info (model gave no name / DB has no name to check against)

For LLM answers we use the step-2 extractor PLUS a bare "SC <num>/<year>" fallback and a
token-overlap name matcher so short names like "Randeniya" match "Randeniya and Others v ...".

Outputs:
  evaluation/audit_results_per_model.md         - counts per model + verified-rate
  evaluation/audit_results_per_citation.csv     - every citation with its verdict + reason
  audit/needs_kavini.csv                        - short list of undecidables
  audit/verify_30.csv                           - 10 random not-in-corpus per model
"""
import csv
import json
import os
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "citations"))
sys.path.insert(0, os.path.join(ROOT, "scraping"))
from extract_citations import extract_from_judgment  # noqa: E402

DB = os.path.join(ROOT, "data", "judgments.db")
OUT_MD = os.path.join(ROOT, "evaluation", "audit_results_per_model.md")
OUT_CSV = os.path.join(ROOT, "evaluation", "audit_results_per_citation.csv")
NEEDS = os.path.join(HERE, "needs_kavini.csv")
VERIFY30 = os.path.join(HERE, "verify_30.csv")

SL_REPORTER_PREFIXES = ("NLR_", "SLR_", "BLR_", "CLW_")

# -------- external index (lankalaw.net) --------------------------------
EXT_PATH = os.path.join(ROOT, "data", "reported_cases_index.csv")
ext_by_key = {}      # report_key -> list of (name, citation, date)
ext_name_tokens = {} # (frozenset of content tokens) -> list of (name, citations, date)


def _key_from_cit(cit_str):
    """Normalise a (YYYY) V Sri LR P / NLR style citation into report_key."""
    m = re.search(r"\((\d{4})\)\s*(\d*)\s*Sri\s*L\.?R\.?\s*(\d+)", cit_str, re.I)
    if m:
        y, v, p = m.group(1), m.group(2) or "1", m.group(3)
        return f"SLR_{y}_{v}_{p}"
    m = re.search(r"\((\d{4})\)\s*(\d+)\s*NLR\s*(\d+)", cit_str, re.I)
    if m:
        return f"NLR_{m.group(2)}_{m.group(3)}"
    m = re.search(r"(\d+)\s+NLR\s+(\d+)", cit_str, re.I)
    if m:
        return f"NLR_{m.group(1)}_{m.group(2)}"
    return None


def _strip_name(n):
    # remove trailing " - NLR - ..." or " - SLR - ..."
    for marker in (" - NLR", " - SLR", " - Vol", " [19", " [20"):
        if marker in n:
            n = n.split(marker)[0]
    return n.strip()


if os.path.exists(EXT_PATH):
    for r in csv.DictReader(open(EXT_PATH, encoding="utf-8")):
        name = _strip_name(r["case_name"])
        cits = r["citations"] or ""
        date = r["decision_date"] or ""
        for cs in cits.split(";"):
            k = _key_from_cit(cs.strip())
            if k:
                ext_by_key.setdefault(k, []).append((name, cs.strip(), date))
    print(f"   external index: {len(ext_by_key)} report_keys from lankalaw.net")

# ---- DB index -----------------------------------------------------------
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
all_cits = {}
report_names = defaultdict(set)
for r in con.execute("SELECT report_key, case_name FROM citations "
                     "WHERE report_key IS NOT NULL AND report_key != ''"):
    all_cits.setdefault(r["report_key"], r)
    if r["case_name"]:
        report_names[r["report_key"]].add(r["case_name"])
judgments_by_id = {r["case_id"]: r for r in con.execute(
    "SELECT case_id, parties, case_no_raw FROM judgments")}
# case_no (CA/SC) in citations table too: targets we may have linked but not own
cn_names = defaultdict(set)
for r in con.execute("SELECT case_no, case_name FROM citations "
                     "WHERE case_no IS NOT NULL AND case_no != ''"):
    if r["case_name"]:
        cn_names[r["case_no"]].add(r["case_name"])
# flat name index (lowercase, original)
name_index = []
for r in judgments_by_id.values():
    if r["parties"]:
        name_index.append((r["parties"].lower(), r["parties"]))
for rk, names in report_names.items():
    for n in names:
        name_index.append((n.lower(), n))
con.close()
print(f"1) DB: {len(all_cits)} report_keys · {len(judgments_by_id)} judgments")

# ---- extra parser for bare "SC 452/2001" -------------------------------
BARE_SC_RE = re.compile(r"\bS\.?\s*C\.?\s+(?P<num>\d{1,5})\s*/\s*(?P<yr>(?:19|20)\d{2})(?!\d)")


def extra_case_nos(text):
    out = []
    for m in BARE_SC_RE.finditer(text):
        out.append(dict(kind="case_no", raw=m.group(0),
                        report_key=None, case_no=f"SC_APPEAL_{m.group('num')}_{m.group('yr')}",
                        case_name=None))
    return out


# ---- lenient name match -------------------------------------------------
STOPWORDS = {"v", "vs", "v.", "vs.", "and", "the", "of", "others", "another", "another.", "&",
             "ltd", "limited", "pvt", "private", "pte", "co", "company", "co.,", "ltd.",
             "attorney", "general", "hon", "hon.", "dr", "dr.", "mrs", "mr", "ms",
             "inspector", "police", "station", "secretary", "chairman", "minister",
             "a", "an", "to", "in", "or", "as", "at", "for", "with", "by", "on"}


def tokens(name):
    return [t for t in re.findall(r"[A-Za-z]+", (name or "").lower())
            if t and t not in STOPWORDS and len(t) > 2]


def name_matches(model_name, db_names):
    """Strict name matcher. Requires at least one shared content token between the
    model's name and a DB name. Empty content-tokens on either side => no match.
    """
    if not model_name or not db_names:
        return False
    mt = set(tokens(model_name))
    if not mt:
        return False
    for db in db_names:
        dt = set(tokens(db))
        if not dt:
            continue
        overlap = mt & dt
        if not overlap:
            continue
        # cover at least one side's tokens meaningfully, OR very high string similarity
        cov_m = len(overlap) / len(mt)
        cov_d = len(overlap) / len(dt)
        if max(cov_m, cov_d) >= 0.5:
            return True
        if SequenceMatcher(None, model_name.lower(), db.lower()).ratio() >= 0.85:
            return True
    return False


def cited_year(c):
    rk = c.get("report_key") or ""
    m = re.match(r"(?:NLR|SLR|BLR|CLW|Ch|AC|QB|KB|WLR|AIR|SCC|AllER)_(\d{4})_", rk)
    if m:
        return int(m.group(1))
    cn = c.get("case_no") or ""
    m = re.search(r"_(\d{4})$", cn)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(19|20)\d{2}\b", c.get("raw") or "")
    if m:
        return int(m.group(0))
    return None


def classify(c):
    rk = c.get("report_key") or ""
    cn = c.get("case_no") or ""
    raw_name = (c.get("case_name") or "").strip()
    yr = cited_year(c)

    # ---- case_no path
    if cn and cn in judgments_by_id:
        parties = judgments_by_id[cn]["parties"] or ""
        if raw_name:
            if parties and not name_matches(raw_name, {parties}):
                return "name-mismatch", f"case_no {cn} in DB as DIFFERENT case (model: {raw_name[:40]} | DB: {parties[:40]})"
            return "verified-correct", f"case_no {cn} matches judgment in DB ({parties[:60] or 'no name stored'})"
        # number matches, AI gave no name -> cannot confirm the AI meant THIS case
        return "number-exists-unverified", f"case_no {cn} exists in DB ({parties[:60] or 'no stored name'}); AI gave no case name"
    if cn and cn in cn_names and cn_names[cn]:
        if raw_name:
            if not name_matches(raw_name, cn_names[cn]):
                return "name-mismatch", f"case_no {cn} seen in citations as DIFFERENT case (model: {raw_name[:40]})"
            return "verified-correct", f"case_no {cn} seen in citations table ({list(cn_names[cn])[0][:60]})"
        return "number-exists-unverified", f"case_no {cn} seen in citations ({list(cn_names[cn])[0][:60]}); AI gave no case name"

    # ---- report_key path ----
    if rk and rk in all_cits:
        names = report_names.get(rk, set())
        if names:
            if raw_name and name_matches(raw_name, names):
                return "verified-correct", f"report_key match + name match ({list(names)[0][:60]})"
            if not raw_name:
                return "undecidable", f"report_key exists; model gave no case name (DB: {list(names)[0][:60]})"
            return "name-mismatch", f"report_key {rk} in DB as DIFFERENT case (model: {raw_name[:40]} | DB: {list(names)[0][:40]})"
        # rule 2: key exists but DB has no name - cannot be called wrong
        return "exists-name-unverified", f"report_key {rk} exists in graph; DB has no stored name to verify"

    # ---- external index lookup (lankalaw.net A-Z) --------------------
    if rk and rk in ext_by_key:
        ext = ext_by_key[rk]
        ext_names = [e[0] for e in ext]
        if raw_name:
            if name_matches(raw_name, ext_names):
                return "verified-correct-external", f"found in lankalaw index: {ext[0][0][:60]}"
            return "wrong-case", f"citation {rk} exists externally as DIFFERENT case ({ext[0][0][:60]}; AI said {raw_name[:40]})"
        return "number-exists-unverified", f"citation {rk} exists in external index ({ext[0][0][:60]}); AI gave no case name"

    # external name match without a matching citation -> real name, wrong citation
    if raw_name and len(raw_name) >= 8:
        mt = set(tokens(raw_name))
        if mt:
            for key_rk, entries in ext_by_key.items():
                for name, _, _ in entries:
                    dt = set(tokens(name))
                    if not dt:
                        continue
                    overlap = mt & dt
                    if overlap and max(len(overlap) / len(mt), len(overlap) / len(dt)) >= 0.8:
                        return "real-name-wrong-citation", f"name matches an external case ({name[:60]}) but citation {rk or cn or '?'} does not"

    # rule 3: pre-2009 year AND not in graph AND not in external index
    if yr is not None and yr > 2011 and yr < 2009:
        pass  # unreachable
    if yr is not None and 2011 < yr:
        return "unverifiable", f"cited year {yr} is after lankalaw index (2011); cannot verify"
    if yr is not None and yr < 2009:
        return "not-found-anywhere", f"cited year {yr} is before our corpus (2009-2025) and not in external index"
    return "not-found-anywhere", "no match in judgments.db / citations / external index"


def sl_citation(c):
    rk = c.get("report_key") or ""
    if rk.startswith(SL_REPORTER_PREFIXES):
        return True
    cn = c.get("case_no") or ""
    if re.match(r"^(SC|CA)_", cn):
        return True
    return False


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _collect_answers():
    answers = []
    for d in load_jsonl(os.path.join(HERE, "chatgpt_answers.jsonl")):
        answers.append((d["model"], d["q_id"], d.get("answer", "")))
    for d in load_jsonl(os.path.join(HERE, "llama_answers.jsonl")):
        answers.append(("llama-3.2-3b", d["q_id"], d.get("answer", "")))
    return answers

# attach nearest preceding case name (within 180 chars) to extra bare SC/CA citations
NAME_WINDOW = 180


def attach_name_from_text(c, text):
    if c.get("case_name"):
        return
    pos = text.find(c["raw"])
    if pos < 0:
        return
    pre = text[max(0, pos - NAME_WINDOW): pos]
    m = re.search(r"([A-Z][A-Za-z'.\-]+(?:\s+(?:v\.?|vs\.?|V)\s+[A-Z][A-Za-z'.\-]+(?:\s+[A-Za-z'.\-]+){0,6})?)\s*[,\(\[]?\s*$", pre)
    if m:
        c["case_name"] = m.group(1).strip()


def extract_principle(text, raw):
    """Return the sentence containing the citation (or the next sentence) as the claimed principle."""
    pos = text.find(raw)
    if pos < 0:
        return ""
    # back up to sentence start
    start = max(text.rfind(". ", 0, pos), text.rfind("\n", 0, pos), 0)
    end = pos + len(raw)
    for p in (". ", ".\n", "\n\n"):
        nxt = text.find(p, end)
        if 0 <= nxt < end + 240:
            end = nxt + 1
            break
    sent = text[start:end + 1].strip(" .\n")
    return " ".join(sent.split())[:260]


LABELS_ORDER = ["verified-correct", "verified-correct-external", "exists-name-unverified",
                "number-exists-unverified", "name-mismatch", "wrong-case",
                "real-name-wrong-citation", "not-found-anywhere", "unverifiable", "undecidable"]


if __name__ == "__main__":
    answers = _collect_answers()
    print(f"2) {len(answers)} answers from {len(set(m for m, _, _ in answers))} models")
    results = []
    for model, qid, text in answers:
        cits = [c for c in extract_from_judgment(f"{model}_{qid}", text) if c.get("kind") != "supra"]
        raws_seen = {c["raw"] for c in cits}
        for c in extra_case_nos(text):
            if c["raw"] not in raws_seen:
                attach_name_from_text(c, text)
                cits.append(c)
        for c in cits:
            if not sl_citation(c):
                continue
            verdict, reason = classify(c)
            results.append(dict(model=model, q_id=qid, raw=c["raw"],
                                report_key=c.get("report_key"), case_no=c.get("case_no"),
                                case_name=c.get("case_name") or "",
                                principle=extract_principle(text, c["raw"]),
                                verdict=verdict, reason=reason))

    agg = defaultdict(Counter)
    for r in results:
        agg[r["model"]][r["verdict"]] += 1

    md = ["# Automatic audit of Sri Lankan citations in model answers\n",
          f"Total SL citations checked: {len(results)}\n",
          "| model | " + " | ".join(LABELS_ORDER) + " | total | verified-rate |",
          "|---|" + "---|" * (len(LABELS_ORDER) + 2)]
    for model in sorted(agg):
        row = agg[model]
        tot = sum(row.values())
        ver = row["verified-correct"]
        rate = f"{100 * ver / tot:.1f}%" if tot else "n/a"
        md.append("| " + model + " | " + " | ".join(str(row[l]) for l in LABELS_ORDER)
                  + f" | {tot} | {rate} |")
    open(OUT_MD, "w").write("\n".join(md))
    print("\n".join(md))

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["model", "q_id", "raw", "report_key", "case_no",
                                          "case_name", "principle", "verdict", "reason"])
        w.writeheader()
        for r in results:
            w.writerow(r)

    examples = defaultdict(list)
    for r in results:
        if len(examples[r["verdict"]]) < 2:
            examples[r["verdict"]].append(r)
    with open(os.path.join(ROOT, "evaluation", "audit_verdict_examples.md"), "w") as f:
        f.write("# Example citations per verdict\n\n")
        for v in LABELS_ORDER:
            if not examples[v]:
                continue
            f.write(f"## {v}\n\n")
            for r in examples[v]:
                f.write(f"- **{r['model']} / {r['q_id']}** · raw `{r['raw']}` · "
                        f"name `{r['case_name'] or '-'}` · principle: *{r['principle'][:120]}* · "
                        f"reason: {r['reason'][:100]}\n")
            f.write("\n")

    rows_ud = [r for r in results if r["verdict"] in ("undecidable", "name-mismatch")]
    rows_ud.sort(key=lambda r: (r["model"], 0 if r["case_name"] else 1))
    cap = defaultdict(int)
    short = []
    for r in rows_ud:
        if cap[r["model"]] >= 10:
            continue
        short.append(r); cap[r["model"]] += 1
    with open(NEEDS, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "q_id", "raw", "report_key_or_case_no", "model_case_name",
                    "verdict", "db_hint", "kavini_verdict"])
        for r in short:
            w.writerow([r["model"], r["q_id"], r["raw"],
                        r["report_key"] or r["case_no"] or "",
                        r["case_name"] or "", r["verdict"], r["reason"], ""])
    print(f"\nwrote {NEEDS} ({len(short)} rows)")

    random.seed(42)
    by_model = defaultdict(list)
    for r in results:
        if r["verdict"] == "not-in-corpus":
            by_model[r["model"]].append(r)
    with open(VERIFY30, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "q_id", "case_name", "citation", "verdict", "found_online (Y/N)", "source"])
        for model, lst in sorted(by_model.items()):
            pick = random.sample(lst, min(10, len(lst)))
            for r in pick:
                w.writerow([model, r["q_id"], r["case_name"] or "",
                            r["raw"], r["verdict"], "", ""])
    print(f"wrote {VERIFY30}")
