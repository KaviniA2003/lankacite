"""
LankaCite - Step 2: Extract case citations from judgments and build the citation graph.

Input : data/judgments.db   (from step 1)
Output: data/judgments.db   new table `citations` (one row per citation found)
        data/citation_graph.json     graph as nodes + edges (with context sentences)
        data/citation_graph.graphml  same graph, opens in Gephi
        data/citations_sample.csv    50 random judgments' citations, for your manual check (evaluation)

What it finds
  - Sri Lankan law reports : (1952) 54 NLR 1 | [1997] 2 Sri LR 98 | (2004) 1 SLR 12 | (1950) 42 CLW 1
  - Case numbers           : SC FR 256/2017 | SC (FR) Application No. 256/2017 | SC Appeal 45/2010 | CA Writ 123/2010
  - Foreign reports        : AC, QB, KB, Ch, WLR, All ER, AIR, SCC  (kept, but marked foreign)
  - Case names next to a citation: "Ratnayake v. Attorney-General [1997] 2 Sri LR 98"
  - "supra" back-references: "in Ratnayake (supra)"  -> linked to the earlier full citation in the same judgment

How citations are linked to cases (in this order)
  1. Case number matches a judgment in our database             -> that judgment
  2. Case name + year closely matches a judgment's parties      -> that judgment (fuzzy match, flagged)
  3. Otherwise a node for the reported case, keyed by its report  -> e.g. SLR_1997_2_98

Run:
  pip install rapidfuzz networkx
  python3 citations/extract_citations.py --db data/judgments.db --out data
"""

import argparse
import json
import os
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scraping"))
from collect_judgments import normalise_case_no  # same case-number format as step 1

# ---------------------------------------------------------------- patterns


SL_REPORTERS = {
    "NLR": r"N\.?\s*L\.?\s*R\.?",
    "SLR": r"(?:Sri\.?\s*L\.?\s*R\.?|S\.?\s*L\.?\s*R\.?)",
    "CLW": r"C\.?\s*L\.?\s*W\.?",
    "CLR": r"Ceylon\s+Law\s+Recorder|C\.?\s*L\.?\s*Rec\.?",
    "BLR": r"B\.?\s*L\.?\s*R\.?|BALR",
}
FOREIGN_REPORTERS = {
    "AC": r"A\.?\s*C\.?", "QB": r"Q\.?\s*B\.?", "KB": r"K\.?\s*B\.?", "Ch": r"Ch\.?",
    "WLR": r"W\.?\s*L\.?\s*R\.?", "AllER": r"All\s*E\.?\s*R\.?",
    "AIR": r"A\.?\s*I\.?\s*R\.?", "SCC": r"S\.?\s*C\.?\s*C\.?",
}

# (1997) 2 Sri LR 98   |  [1997] 2 Sri LR 98   |  54 NLR 1 (no year)   |  1997 (2) SLR 98
def _reporter_regex(code, rx):
    year = r"(?:[\(\[]\s*(?P<year>1[89]\d\d|20\d\d)\s*[\)\]]|(?P<year_bare>1[89]\d\d|20\d\d))"
    return re.compile(
        rf"(?:{year}\s*)?\(?\s*(?P<vol>\d{{1,3}})\s*\)?\s*\b(?P<rep>{rx})(?![A-Za-z])\s*,?\s*(?:p\.?\s*)?(?P<page>\d{{1,4}})\b",
        0 if code in ("Ch", "AC", "QB", "KB") else re.I,
    )

REPORTER_RES = [(c, _reporter_regex(c, rx), False) for c, rx in SL_REPORTERS.items()] + \
               [(c, _reporter_regex(c, rx), True) for c, rx in FOREIGN_REPORTERS.items()]

# SC / CA case numbers. Kept broad, then normalised.
CASE_NO_RE = re.compile(
    r"\b(?:S\.?\s*C\.?|C\.?\s*A\.?)\s*[\(/\-\s]*"
    r"(?:F\.?\s*/?\s*R\.?|H\.?\s*C\.?\s*[\(/\-\s]*L\.?\s*A\.?|S\.?\s*P\.?\s*L\.?\s*L\.?\s*A\.?|L\.?\s*A\.?|"
    r"Appeal|Appl\.?|Rule|S\.?\s*D\.?|Reference|Writ|P\.?\s*H\.?\s*C\.?|Revision|Rev\.?)"
    r"[\)\s]*(?:\(?\s*(?:Application|Appln\.?|App\.?)\s*\)?)?\s*(?:No\.?|Number)?\s*"
    r"\d{1,5}\s*/\s*(?:19|20)?\d{2}\b",
    re.I,
)

# Case name just before a citation: "Perera v. Attorney-General", "Perera and Another vs. Cyril Ranatunga"
NAME_RE = re.compile(
    r"(?P<name>[A-Z][\w.'’&\-]*,?(?:\s+(?:[A-Z][\w.'’&\-]*,?|and|&|de|of)){0,8}?"
    r"\s+(?:v|vs|V)\.?\s+"
    r"(?:[A-Z][\w.'’&\-]*,?|and|of|the|de|others|Others|&|\(.*?\))(?:\s+(?:[A-Z][\w.'’&\-]*,?|and|of|the|de|for|others|Others|&|\(.*?\)))*?)"
    r"\s*[,\(\[]?\s*$"
)
SUPRA_RE = re.compile(r"(?P<name>[A-Z][\w.'’\-]+(?:\s+(?:v|vs)\.?\s+[A-Z][\w.'’\-]+)?(?:'s)?)\s*\(?\s*supra\s*\)?", re.I)

# split sentences, but not after "v.", "No.", "J.", "Sri L.R.", initials like "W.P.S." etc.
SENT_SPLIT = re.compile(
    r"(?<!\bv\.)(?<!\bvs\.)(?<!\bNo\.)(?<!\bJ\.)(?<!\bCJ\.)(?<!\bMr\.)(?<!\bDr\.)(?<!\bR\.)(?<!\bp\.)"
    r"(?<!\bpp\.)(?<!\bArt\.)(?<!\bs\.)(?<!\b[A-Z]\.)(?<=[.!?])\s+(?=[A-Z\"“(])"
)


# ---------------------------------------------------------------- helpers

def clean_text(t: str) -> str:
    t = t.replace(" ", " ").replace("ﬁ", "fi").replace("ﬂ", "fl")
    t = re.sub(r"-\n(?=[a-z])", "", t)        # re-join hyphenated words split over lines
    t = re.sub(r"[ \t]*\n[ \t]*", " ", t)     # PDF line breaks -> spaces
    return re.sub(r"\s{2,}", " ", t)


def context_window(text: str, start: int, end: int, chars: int = 600) -> str:
    """The sentence containing the citation, plus one sentence either side (what the judge said about it)."""
    lo, hi = max(0, start - chars), min(len(text), end + chars)
    chunk = text[lo:hi]
    sents = SENT_SPLIT.split(chunk)
    pos, out, rel = 0, [], start - lo
    spans = []
    for s in sents:
        i = chunk.find(s, pos)
        spans.append((i, i + len(s), s))
        pos = i + len(s)
    idx = next((k for k, (a, b, _) in enumerate(spans) if a <= rel <= b), None)
    if idx is None:
        return chunk.strip()
    keep = spans[max(0, idx - 1): idx + 2]
    return " ".join(s for _, _, s in keep).strip()


def name_before(text: str, start: int) -> str:
    window = text[max(0, start - 160):start]
    window = re.split(r"[;:]|\bin\b(?=\s+[A-Z])|\bsee\b|\bSee\b|\bcase of\b", window)[-1]
    m = NAME_RE.search(window.strip())
    if not m:
        return ""
    name = re.sub(r"^(?:In|in|The|the|See|see|Also|also|In the case of)\s+", "", m.group("name").strip(" ,([")).strip()
    return name if 5 < len(name) < 140 else ""


def norm_name(n: str) -> str:
    n = n.lower()
    n = re.sub(r"\b(and others|and another|others|another|the|hon|honourable|ltd|limited|plc|pvt|\(pvt\))\b", " ", n)
    n = re.sub(r"[^a-z ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def first_party(n: str) -> str:
    return norm_name(re.split(r"\s+(?:v|vs)\.?\s+", n, maxsplit=1, flags=re.I)[0])


# ---------------------------------------------------------------- extraction

def extract_from_judgment(case_id: str, raw_text: str) -> list[dict]:
    text = clean_text(raw_text)
    found, taken = [], []

    def overlaps(a, b):
        return any(a < y and b > x for x, y in taken)

    # 1) law-report citations
    for code, rx, foreign in REPORTER_RES:
        for m in rx.finditer(text):
            if overlaps(m.start(), m.end()):
                continue
            vol = m.group("vol")
            year = m.group("year") or m.group("year_bare")
            if code == "NLR" and not vol:
                continue
            key = f"{code}_{year or 'NA'}_{vol}_{m.group('page')}" if code != "NLR" else f"NLR_{vol}_{m.group('page')}"
            taken.append((m.start(), m.end()))
            found.append(dict(kind="report", reporter=code, foreign=foreign, year=year, volume=vol,
                              page=m.group("page"), report_key=key, case_no=None,
                              raw=m.group(0), start=m.start(), end=m.end()))

    # 2) case-number citations
    for m in CASE_NO_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        norm = normalise_case_no(m.group(0))
        if not norm:
            ca = re.search(r"C\.?\s*A\.?.*?(\w+)?\D*(\d{1,5})\s*/\s*((?:19|20)?\d{2})", m.group(0), re.I)
            if ca:
                yr = ca.group(3) if len(ca.group(3)) == 4 else ("20" if int(ca.group(3)) <= 40 else "19") + ca.group(3)
                norm = f"CA_{int(ca.group(2))}_{yr}"
        if not norm or norm == case_id:      # skip the judgment's own number in its header
            continue
        taken.append((m.start(), m.end()))
        found.append(dict(kind="case_no", reporter=None, foreign=False, year=norm.rsplit("_", 1)[-1],
                          volume=None, page=None, report_key=None, case_no=norm,
                          raw=m.group(0), start=m.start(), end=m.end()))

    # 3) case names + context
    for c in found:
        c["case_name"] = name_before(text, c["start"])
        c["context"] = context_window(text, c["start"], c["end"])

    # 4) supra back-references -> copy the earlier full citation with the same first party
    by_party = {}
    for c in sorted(found, key=lambda c: c["start"]):
        if c["case_name"]:
            by_party.setdefault(first_party(c["case_name"]), c)
    for m in SUPRA_RE.finditer(text):
        party = first_party(m.group("name").replace("'s", ""))
        if party in by_party and not overlaps(m.start(), m.end()):
            src = by_party[party]
            found.append({**src, "kind": "supra", "raw": m.group(0), "start": m.start(), "end": m.end(),
                          "context": context_window(text, m.start(), m.end())})

    for c in found:
        c["citing_case"] = case_id
    return sorted(found, key=lambda c: c["start"])


# ---------------------------------------------------------------- linking

def link(citations: list[dict], judgments: dict[str, dict]):
    from rapidfuzz import fuzz, process

    names = {cid: norm_name(j["parties"] or "") for cid, j in judgments.items()}
    years = {cid: int(cid.rsplit("_", 1)[-1]) if cid.rsplit("_", 1)[-1].isdigit() else None for cid in judgments}
    choices = list(names.items())

    report_to_case = {}  # learn: same report key cited with a case number elsewhere
    for c in citations:
        if c["kind"] == "case_no" and c["case_no"] in judgments:
            c["target"], c["link_method"], c["link_score"] = c["case_no"], "case_number", 100
        elif c["kind"] == "case_no":
            c["target"], c["link_method"], c["link_score"] = c["case_no"], "case_number_not_in_db", 100
        else:
            c["target"], c["link_method"], c["link_score"] = None, None, None

    for c in citations:
        if c["target"] or c["foreign"]:
            if c["foreign"]:
                c["target"], c["link_method"], c["link_score"] = c["report_key"], "foreign_report", 100
            continue
        # fuzzy: case name close to a judgment's parties, and judgment no later than the citing year window
        cname = norm_name(c["case_name"]) if c["case_name"] else ""
        best = None
        if cname:
            cands = process.extract(cname, dict(choices), scorer=fuzz.token_set_ratio, limit=3)
            for _, score, cid in cands:
                y = years.get(cid)
                if score >= 88 and (not c["year"] or not y or abs(int(c["year"]) - y) <= 4):
                    best = (cid, score)
                    break
        if best:
            c["target"], c["link_method"], c["link_score"] = best[0], "name_fuzzy", best[1]
            report_to_case.setdefault(c["report_key"], best[0])
        else:
            c["target"], c["link_method"], c["link_score"] = c["report_key"], "report_key", 100

    # second pass: a report key linked to a judgment once -> use that for all other mentions
    for c in citations:
        if c["link_method"] == "report_key" and c["report_key"] in report_to_case:
            c["target"], c["link_method"] = report_to_case[c["report_key"]], "report_key_via_name"


# ---------------------------------------------------------------- outputs

def build_graph(citations, judgments, out_dir):
    import networkx as nx
    G = nx.MultiDiGraph()
    for cid, j in judgments.items():
        G.add_node(cid, kind="judgment_in_db", parties=j["parties"] or "", year=cid.rsplit("_", 1)[-1])
    names = defaultdict(Counter)
    for c in citations:
        if c["case_name"]:
            names[c["target"]][c["case_name"]] += 1
    for c in citations:
        t = c["target"]
        if t and t not in G:
            G.add_node(t, kind="foreign" if c["foreign"] else "external_case",
                       parties=names[t].most_common(1)[0][0] if names[t] else "", year=c["year"] or "")
        if t and t != c["citing_case"]:
            G.add_edge(c["citing_case"], t, raw=c["raw"], kind=c["kind"], link_method=c["link_method"],
                       context=c["context"])
    nx.write_graphml(G, os.path.join(out_dir, "citation_graph.graphml"))
    data = {"nodes": [{"id": n, **d} for n, d in G.nodes(data=True)],
            "edges": [{"source": u, "target": v, **d} for u, v, d in G.edges(data=True)]}
    with open(os.path.join(out_dir, "citation_graph.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return G


def save_table(con, citations):
    con.execute("DROP TABLE IF EXISTS citations")
    con.execute("""CREATE TABLE citations (id INTEGER PRIMARY KEY, citing_case TEXT, kind TEXT, raw TEXT,
        case_name TEXT, reporter TEXT, foreign_report INTEGER, year TEXT, volume TEXT, page TEXT,
        case_no TEXT, report_key TEXT, target TEXT, link_method TEXT, link_score REAL,
        start_char INTEGER, context TEXT)""")
    con.executemany("""INSERT INTO citations (citing_case, kind, raw, case_name, reporter, foreign_report, year,
        volume, page, case_no, report_key, target, link_method, link_score, start_char, context)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(c["citing_case"], c["kind"], c["raw"], c["case_name"], c["reporter"], int(c["foreign"]), c["year"],
          c["volume"], c["page"], c["case_no"], c["report_key"], c["target"], c["link_method"],
          c["link_score"], c["start"], c["context"]) for c in citations])
    con.commit()


def write_sample(citations, out_dir, n=50, seed=42):
    import csv
    cases = sorted({c["citing_case"] for c in citations})
    random.Random(seed).shuffle(cases)
    pick = set(cases[:n])
    with open(os.path.join(out_dir, "citations_sample.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["citing_case", "raw", "case_name", "target", "link_method",
                    "correct_citation? (Y/N)", "correct_link? (Y/N)", "notes", "context"])
        for c in citations:
            if c["citing_case"] in pick:
                w.writerow([c["citing_case"], c["raw"], c["case_name"], c["target"], c["link_method"], "", "", "",
                            c["context"][:400]])
    return sorted(pick)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/judgments.db")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    rows = con.execute("SELECT case_id, parties, text FROM judgments WHERE status='ok'").fetchall()
    judgments = {cid: {"parties": p, "text": t} for cid, p, t in rows}
    print(f"1) {len(judgments)} judgments with text")

    citations = []
    for i, (cid, j) in enumerate(judgments.items(), 1):
        citations += extract_from_judgment(cid, j["text"])
        if i % 200 == 0:
            print(f"   {i} judgments read, {len(citations)} citations so far")
    print(f"2) {len(citations)} citations found")

    link(citations, judgments)
    save_table(con, citations)
    G = build_graph(citations, judgments, args.out)
    sample = write_sample(citations, args.out)

    print("3) Citations by type     :", dict(Counter(c["kind"] for c in citations)))
    print("   Law reports cited     :", dict(Counter(c["reporter"] for c in citations if c["reporter"]).most_common()))
    print("   How they were linked  :", dict(Counter(c["link_method"] for c in citations)))
    print(f"   With a case name      : {sum(1 for c in citations if c['case_name'])}/{len(citations)}")
    internal = sum(1 for _, v in G.edges() if G.nodes[v].get("kind") == "judgment_in_db")
    print(f"4) Graph: {G.number_of_nodes()} cases, {G.number_of_edges()} citation links "
          f"({internal} link two judgments in our database)")
    top = Counter(v for _, v in G.edges() if G.nodes[v].get("kind") != "foreign").most_common(10)
    print("   Most-cited Sri Lankan cases:")
    for node, k in top:
        print(f"     {k:4d}  {node}  {G.nodes[node].get('parties', '')[:70]}")
    print(f"5) Saved: citations table in {args.db}, citation_graph.json/.graphml, "
          f"citations_sample.csv ({len(sample)} judgments for your manual check)")


if __name__ == "__main__":
    main()