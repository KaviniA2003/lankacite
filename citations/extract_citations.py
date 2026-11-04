"""
LankaCite - Step 2: Extract case citations from judgments and build the citation graph.

Input : data/judgments.db   (from step 1)
Output: data/judgments.db   new table `citations` (one row per citation found)
        data/citation_graph.json     graph as nodes + edges (with context sentences)
        data/citation_graph.graphml  same graph, opens in Gephi
        data/citations_sample.csv    50 random judgments' citations, for your manual check (evaluation)
        data/citations_sample_judgments.csv  the same 50 judgments, one row each (for writing down missed citations)

What it finds
  - Sri Lankan law reports : (1952) 54 NLR 1 | [1997] 2 Sri LR 98 | (2004) 1 SLR 12 | (1950) 42 CLW 1 | 11 C.L.R. 48
                             (1977) 79(i) NLR 421 (NLR part-volumes) | BALR [2013] Vol. XX 20 | SLLR
  - Case numbers           : SC FR 256/2017 | SC (FR) Application No. 256/2017 | SC/APPEAL/154/2017 | SC (CHC) Appeal 25/2011
                             SC/HCCA/LA 105/2010 | SC/TAB/4/2023 | CA Writ 123/2010
    with an optional date  : (SC/APPEAL/154/2017, SC Minutes of 21.11.2022)
  - Foreign reports        : AC, QB, KB, Ch, WLR, All ER, AIR, SCC  (kept, but marked foreign)
                             incl. no-volume forms [1970] AC 942 and AIR 1981 SC 852
  - Case names next to a citation: "Ratnayake v. Attorney-General [1997] 2 Sri LR 98"
  - "supra" back-references: "in Ratnayake (supra)"  -> linked to the earlier full citation in the same judgment

What it ignores (these are not citations)
  - running page headers/footers ("[SC APPEAL 120/2021] Page 6 of 19") - lines repeated on most pages are removed first
  - the judgment's own case number in any format
  - case numbers in the caption (before "BEFORE:"): the same case in lower courts, or cases heard together with it

How citations are linked to cases (in this order)
  1. Case number matches a judgment in our database             -> that judgment ("case_number"; "case_number+date"
                                                                    when an "SC Minutes of <date>" matches its decision date)
  2. Case name matches BOTH parties of a judgment in our database, and the report year is 0-3 years after that judgment
     was decided (only possible for Sri Lankan reports from 2009 on) -> that judgment ("name_fuzzy")
     A weaker or ambiguous match is NOT accepted: link_method = "needs_review", the guess is kept in `candidate`
  3. Otherwise a node for the reported case, keyed by its report  -> e.g. SLR_1997_2_98

Run:
  pip install -r requirements.txt
  python3 citations/extract_citations.py --db data/judgments.db --out data            # everything
  python3 citations/extract_citations.py --db data/judgments.db --out data --limit 50 # quick test
"""

import argparse
import csv
import json
import os
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scraping"))
from collect_judgments import normalise_case_no  # same case-number format as step 1

# ---------------------------------------------------------------- patterns

SL_REPORTERS = {
    "NLR": r"N\.?\s*L\.?\s*R\.?",
    "SLR": r"(?:Sri\.?\s*L\.?\s*R\.?|S\.?\s*L\.?\s*L\.?\s*R\.?|S\.?\s*L\.?\s*R\.?)",
    "CLW": r"C\.?\s*L\.?\s*W\.?",
    "CLR": r"Ceylon\s+Law\s+Recorder|C\.?\s*L\.?\s*Rec\.?|C\.\s*L\.\s*R\.",
    "BLR": r"B\.?\s*L\.?\s*R\.?|B\.?\s*A\.?\s*L\.?\s*R\.?",
}
FOREIGN_REPORTERS = {
    "AC": r"A\.?\s*C\.?", "QB": r"Q\.?\s*B\.?", "KB": r"K\.?\s*B\.?", "Ch": r"Ch\.?",
    "WLR": r"W\.?\s*L\.?\s*R\.?", "AllER": r"All\s*E\.?\s*R\.?",
    "AIR": r"A\.?\s*I\.?\s*R\.?", "SCC": r"S\.?\s*C\.?\s*C\.?",
}
# reports cited by year only: [1970] AC 942, [1949] Ch 333, (2008) BLR 127
NO_VOLUME_OK = {"AC", "QB", "KB", "Ch", "WLR", "AllER", "BLR"}

YEAR = r"(?:[\(\[]\s*(?P<year>1[89]\d\d|20\d\d)\s*[\)\]]|(?<!\d)(?P<year_bare>1[89]\d\d|20\d\d))"
# volume, never the tail of a year; NLR part-volumes: 79(i) / 79 (2)
VOL = r"\(?\s*(?<![\d/])(?P<vol>\d{1,3})(?:\s*\(\s*(?P<part>i{1,3}|I{1,3}|[1-3])\s*\))?\s*\)?"


# (1997) 2 Sri LR 98  |  [1997] 2 Sri LR 98  |  54 NLR 1 (no year)  |  1997 (2) SLR 98  |  [1970] AC 942
def _reporter_regex(code, rx):
    return re.compile(
        rf"(?:{YEAR}\s*,?\s*)?(?:{VOL}\s*)?\b(?P<rep>{rx})(?![A-Za-z])\s*,?\s*(?:p\.?\s*)?(?P<page>\d{{1,4}})\b",
        0 if code in ("Ch", "AC", "QB", "KB") else re.I,
    )


REPORTER_RES = [(c, _reporter_regex(c, rx), False) for c, rx in SL_REPORTERS.items()] + \
               [(c, _reporter_regex(c, rx), True) for c, rx in FOREIGN_REPORTERS.items()]

# AIR 1981 SC 852 | A.I.R. 1950 Bom 12
AIR_RE = re.compile(r"\bA\.?\s*I\.?\s*R\.?\s*(?P<year>1[89]\d\d|20\d\d)\s*(?P<court>S\.?\s*C\.?|[A-Z][A-Za-z]{1,10}\.?)\s*(?P<page>\d{1,4})\b")
# 2008 Part II B.L.R. 169 | (2008) Part II BLR 169
BALR_PART_RE = re.compile(r"[\(\[]?\s*(?P<year>(?:19|20)\d\d)\s*[\)\]]?\s*Part\s*(?P<vol>[IVX]+|\d)\s*,?\s*"
                          r"B\.?\s*A?\.?\s*L\.?\s*R\.?\s*,?\s*(?:p(?:g|age)?\.?\s*)?(?P<page>\d{1,4})\b")
# BALR [2013] Vol. XX 20
BALR_VOL_RE = re.compile(r"\bB\.?\s*A\.?\s*L\.?\s*R\.?\s*[\(\[]\s*(?P<year>(?:19|20)\d\d)\s*[\)\]]\s*(?:Vol\.?\s*)?"
                         r"(?P<vol>[IVXL]+|\d{1,3})\s*,?\s*(?:p\.?\s*)?(?P<page>\d{1,4})\b")

# SC / CA case numbers. Kept broad, then normalised with normalise_case_no().
_TYPE = (r"(?:F\.?\s*/?\s*R\.?|H\.?\s*C\.?\s*C\.?\s*A\.?|C\.?\s*H\.?\s*C\.?|H\.?\s*C\.?|S\.?\s*P\.?\s*L\.?|L\.?\s*A\.?|"
         r"Appeal|Appl\.?|Rule|S\.?\s*D\.?|Reference|Ref\.?|Writ|Wrt|P\.?\s*H\.?\s*C\.?|Revision|Rev\.?|TAB|"
         r"Miscellaneous|Misc\.?|Expulsion)")
CASE_NO_RE = re.compile(
    r"\b(?:S\.?\s*C\.?|C\.?\s*A\.?)(?:[\(/\-\s.]*\(?\s*" + _TYPE + r"\s*\)?){1,3}"
    r"[\s/\-]*(?:\(?\s*(?:Application|Appln\.?|App\.?|APN)\s*\)?)?[\s/]*(?:Case\s*)?(?:No\.?|Number)?\s*[:.]?\s*"
    r"(?P<num>\d{1,5})\s*/\s*(?P<yr>(?:19|20)?\d{2})(?!\d)",
    re.I,
)

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}
_DATE = (r"(?:\d{1,2}\s*[./\-]\s*\d{1,2}\s*[./\-]\s*\d{4}|\d{4}\s*[./\-]\s*\d{1,2}\s*[./\-]\s*\d{1,2}|"
         r"\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?[A-Z][a-z]+,?\s+\d{4})")
# right after a case number: ", SC Minutes of 21.11.2022" | "decided on 08th October 2008"
MINUTES_RE = re.compile(r"[\s,;:\]\)]*(?:S\.?\s*C\.?\s*)?(?:Minutes?\s*(?:of|dated|dt\.?|on)?|decided\s+on|dated)\s*:?\s*"
                        r"(?P<date>" + _DATE + ")", re.I)
DECIDED_RE = re.compile(r"(?:Decided|Judgment\s+delivered|Delivered)\s*(?:on|date)?\s*:?\s*(?P<date>" + _DATE + ")", re.I)
CAPTION_END_RE = re.compile(r"\b(?:BEFORE|Before|CORAM|Coram)\s*:|\b(?:COUNSEL|Counsel)\s*:|\bArgued\s+on\b")

# Case name just before a citation: "Perera v. Attorney-General", "Linea Acqua (Pvt) Ltd v. Lakdeva De Silva"
_TOK = r"(?:[A-Z][\w.'’&\-]*,?|\((?:Pvt|Private|Pte)\)\.?)"
NAME_RE = re.compile(
    rf"(?P<name>{_TOK}(?:\s+(?:{_TOK}|and|&|de|of)){{0,8}}?"
    r"\s+(?:v|vs|V)\.?\s+"
    rf"(?:{_TOK}|and|of|the|de|others|Others|&|\(.*?\))(?:\s+(?:{_TOK}|and|of|the|de|for|others|Others|&|\(.*?\)))*?)"
    r"\s*[,\(\[]?\s*$"
)
SUPRA_RE = re.compile(r"(?P<name>[A-Z][\w.'’\-]+(?:\s+(?:v|vs)\.?\s+[A-Z][\w.'’\-]+)?(?:'s)?)\s*\(?\s*supra\s*\)?", re.I)

# split sentences, but not after "v.", "No.", "J.", "Sri L.R.", initials like "W.P.S." etc.
SENT_SPLIT = re.compile(
    r"(?<!\bv\.)(?<!\bvs\.)(?<!\bNo\.)(?<!\bJ\.)(?<!\bCJ\.)(?<!\bMr\.)(?<!\bDr\.)(?<!\bR\.)(?<!\bp\.)"
    r"(?<!\bpp\.)(?<!\bArt\.)(?<!\bs\.)(?<!\b[A-Z]\.)(?<=[.!?])\s+(?=[A-Z\"“(])"
)

# Sri Lankan reports that can contain judgments from our database (2009-2025). NLR/CLW/CLR stopped long before.
LINKABLE_REPORTERS = {"SLR", "BLR"}
FIRST_DB_YEAR = 2009
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}


# ---------------------------------------------------------------- helpers

def strip_running_headers(raw: str, n_pages: int | None) -> tuple[str, int]:
    """Remove lines that repeat on most pages (page headers/footers like '[SC APPEAL 120/2021] Page 6 of 19').
    Numbers are ignored when comparing lines, so 'Page 6 of 19' and 'Page 7 of 19' count as the same line.
    Only lines with a letter AND a number are removed, so normal text and citations split over lines stay."""
    lines = raw.split("\n")
    key = [re.sub(r"\d+", "#", re.sub(r"\s+", " ", ln)).strip().lower() for ln in lines]
    counts = Counter(key)
    min_repeats = max(3, int(0.4 * (n_pages or 1)))
    keep, removed = [], 0
    for ln, k in zip(lines, key):
        if counts[k] >= min_repeats and len(k) >= 4 and "#" in k and re.search(r"[a-z]", k):
            removed += 1
            continue
        keep.append(ln)
    return "\n".join(keep), removed


def clean_text(t: str) -> str:
    t = t.replace(" ", " ").replace("ﬁ", "fi").replace("ﬂ", "fl")
    t = re.sub(r"-\n(?=[a-z])", "", t)        # re-join hyphenated words split over lines
    t = re.sub(r"[ \t]*\n[ \t]*", " ", t)     # PDF line breaks -> spaces
    return re.sub(r"\s{2,}", " ", t)


def parse_date(s: str) -> str | None:
    """'21.11.2022' | '2019 - 06 - 07' | '08th October 2008' -> '2022-11-21' (ISO). None if unreadable."""
    if not s:
        return None
    s = s.strip()
    try:
        m = re.fullmatch(r"(\d{4})\s*[./\-]\s*(\d{1,2})\s*[./\-]\s*(\d{1,2})", s)
        if m:
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        m = re.fullmatch(r"(\d{1,2})\s*[./\-]\s*(\d{1,2})\s*[./\-]\s*(\d{4})", s)
        if m:                                      # Sri Lankan judgments write day.month.year
            return date(int(m[3]), int(m[2]), int(m[1])).isoformat()
        m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]+),?\s+(\d{4})", s)
        if m and m[2].lower() in MONTHS:
            return date(int(m[3]), MONTHS[m[2].lower()], int(m[1])).isoformat()
    except ValueError:
        return None
    return None


def decision_date(text: str) -> str | None:
    m = DECIDED_RE.search(text[:15000])
    return parse_date(m.group("date")) if m else None


def caption_end(text: str) -> int:
    """Where the caption (parties, case numbers, lower-court numbers) ends: at 'BEFORE:' / 'Coram:' / 'Counsel:'."""
    m = CAPTION_END_RE.search(text, 0, max(3000, int(len(text) * 0.35)))
    return m.start() if m else 0


def context_window(text: str, start: int, end: int, chars: int = 600) -> str:
    """The sentence containing the citation, plus one sentence either side (what the judge said about it)."""
    lo, hi = max(0, start - chars), min(len(text), end + chars)
    chunk = text[lo:hi]
    sents = SENT_SPLIT.split(chunk)
    pos, rel = 0, start - lo
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
    window = re.split(r"[;:]|\bin\b(?=\s+[A-Z])|\bsee\b|\bSee\b|\bcase of\b|(?<=[a-z]{3})\.\s+(?=[A-Z])", window)[-1]
    m = NAME_RE.search(window.strip())
    if not m:
        return ""
    name = re.sub(r"^(?:In|in|The|the|See|see|Also|also|In the case of)\s+", "", m.group("name").strip(" ,([")).strip()
    return name if 5 < len(name) < 140 else ""


def norm_name(n: str) -> str:
    n = n.lower()
    n = re.sub(r"\b(?:hon\.?\s*)?(?:the\s+)?a\.?\s*g\.?(?=\s|$)|\battorney[\s\-]+general\b", " attorney general ", n)
    n = re.sub(r"\b(and others|and another|others|another|the|hon|honourable|ltd|limited|plc|pvt|private|\(pvt\))\b", " ", n)
    n = re.sub(r"[^a-z ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def split_parties(n: str) -> tuple[str, str] | None:
    parts = re.split(r"\s+(?:v|vs|V|VS|Vs)\.?\s+", n or "", maxsplit=1)
    if len(parts) != 2:
        return None
    a, b = norm_name(parts[0]), norm_name(parts[1])
    return (a, b) if a and b else None


def first_party(n: str) -> str:
    return norm_name(re.split(r"\s+(?:v|vs)\.?\s+", n, maxsplit=1, flags=re.I)[0])


def roman_to_int(s: str) -> int:
    s = s.upper()
    if s.isdigit():
        return int(s)
    total = 0
    for i, ch in enumerate(s):
        v = ROMAN[ch]
        total += -v if i + 1 < len(s) and ROMAN[s[i + 1]] > v else v
    return total


# ---------------------------------------------------------------- extraction

def own_ids(case_id: str, case_no_raw: str | None) -> set[str]:
    """The judgment's own ID(s): its case_id, plus the parsed form of its raw number (for UNPARSED_n judgments)."""
    ids = {case_id}
    if case_no_raw:
        n = normalise_case_no(case_no_raw)
        if n:
            ids.add(n)
    return ids


def parse_case_no(raw: str) -> str | None:
    norm = normalise_case_no(raw)
    if norm:
        return norm
    ca = re.search(r"C\.?\s*A\.?.*?(\w+)?\D*(\d{1,5})\s*/\s*((?:19|20)?\d{2})", raw, re.I)
    if ca:
        y = ca.group(3)
        yr = y if len(y) == 4 else ("20" if int(y) <= 40 else "19") + y
        return f"CA_{int(ca.group(2))}_{yr}"
    return None


def extract_from_judgment(case_id: str, raw_text: str, n_pages: int | None = None,
                          case_no_raw: str | None = None, stats: Counter | None = None) -> list[dict]:
    stats = stats if stats is not None else Counter()
    text, removed = strip_running_headers(raw_text, n_pages)
    stats["header_lines_removed"] += removed
    text = clean_text(text)
    found, taken = [], []

    def overlaps(a, b):
        return any(a < y and b > x for x, y in taken)

    def add_report(m, code, foreign, year, vol, page, key):
        taken.append((m.start(), m.end()))
        found.append(dict(kind="report", reporter=code, foreign=foreign, year=year, volume=vol, page=page,
                          report_key=key, case_no=None, minutes_date=None,
                          raw=m.group(0).strip(), start=m.start(), end=m.end()))

    # 1) law-report citations (special shapes first, then the general one)
    for m in AIR_RE.finditer(text):
        court = re.sub(r"[\s.]", "", m.group("court"))
        add_report(m, "AIR", True, m.group("year"), None, m.group("page"), f"AIR_{m.group('year')}_{court}_{m.group('page')}")
    for m in list(BALR_PART_RE.finditer(text)) + list(BALR_VOL_RE.finditer(text)):
        if not overlaps(m.start(), m.end()):
            vol = str(roman_to_int(m.group("vol")))
            add_report(m, "BLR", False, m.group("year"), vol, m.group("page"), f"BLR_{m.group('year')}_{vol}_{m.group('page')}")
    for code, rx, foreign in REPORTER_RES:
        for m in rx.finditer(text):
            if overlaps(m.start(), m.end()):
                continue
            vol, part = m.group("vol"), m.group("part")
            year = m.group("year") or m.group("year_bare")
            if not vol and not (year and code in NO_VOLUME_OK):
                continue                           # e.g. bare "AC 942" or "NLR 12": not enough to identify a case
            if part:
                part = str(roman_to_int(part)) if not part.isdigit() else part
                vol = f"{vol}({part})"
            pk = vol.replace("(", "-").replace(")", "") if vol else "NA"
            key = f"NLR_{pk}_{m.group('page')}" if code == "NLR" else f"{code}_{year or 'NA'}_{pk}_{m.group('page')}"
            add_report(m, code, foreign, year, vol, m.group("page"), key)

    # 2) case-number citations; skip own number and every number in the caption (same case / heard together)
    mine = own_ids(case_id, case_no_raw)
    cap = caption_end(text)
    in_caption = set()
    for m in CASE_NO_RE.finditer(text, 0, cap):
        n = parse_case_no(m.group(0))
        if n:
            in_caption.add(n)
    for m in CASE_NO_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        norm = parse_case_no(m.group(0))
        if not norm:
            continue
        if norm in mine:
            stats["skipped_own_number"] += 1
            continue
        if norm in in_caption:
            stats["skipped_caption_number"] += 1
            continue
        mm = MINUTES_RE.match(text, m.end(), m.end() + 80)
        end = mm.end() if mm else m.end()
        taken.append((m.start(), end))
        found.append(dict(kind="case_no", reporter=None, foreign=False, year=norm.rsplit("_", 1)[-1],
                          volume=None, page=None, report_key=None, case_no=norm,
                          minutes_date=parse_date(mm.group("date")) if mm else None,
                          raw=text[m.start():end], start=m.start(), end=end))

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

def party_score(a: str, b: str) -> float:
    """How alike two party names are (0-100). A one-word name ('Fernando') inside a longer one is not a full match."""
    from rapidfuzz import fuzz
    s = fuzz.token_set_ratio(a, b)
    ta, tb = len(a.split()), len(b.split())
    if min(ta, tb) == 1 and max(ta, tb) >= 3:
        s = min(s, 85)
    return s


def link(citations: list[dict], judgments: dict[str, dict]):
    """judgments: case_id -> {parties, decided (ISO date or None), year (decision year), aliases}"""
    alias = {}
    for cid, j in judgments.items():
        for a in j.get("aliases", ()):
            alias.setdefault(a, cid)
    by_year = defaultdict(list)
    for cid, j in judgments.items():
        p = split_parties(j.get("parties") or "")
        if p and j.get("year"):
            by_year[j["year"]].append((cid, p))

    for c in citations:
        c["candidate"] = None
        c["target"], c["link_method"], c["link_score"] = None, None, None
        if c["kind"] in ("case_no", "supra") and c["case_no"]:
            hit = c["case_no"] if c["case_no"] in judgments else alias.get(c["case_no"])
            if not hit:
                c["target"], c["link_method"], c["link_score"] = c["case_no"], "case_number_not_in_db", 100
                continue
            known = judgments[hit].get("decided")
            if c["minutes_date"] and known and c["minutes_date"] != known:
                # same case, but the date points to a different order/judgment in it
                c["target"], c["link_method"], c["link_score"], c["candidate"] = c["case_no"], "needs_review", 50, hit
            else:
                c["target"] = hit
                c["link_method"] = "case_number+date" if c["minutes_date"] and known else "case_number"
                c["link_score"] = 100

    report_links = defaultdict(set)  # report key -> judgments it was confidently linked to
    for c in citations:
        if c["target"] or c["kind"] == "case_no":
            continue
        if c["foreign"]:
            c["target"], c["link_method"], c["link_score"] = c["report_key"], "foreign_report", 100
            continue
        c["target"], c["link_method"], c["link_score"] = c["report_key"], "report_key", 100
        cy = int(c["year"]) if c["year"] else None
        parties = split_parties(c["case_name"]) if c["case_name"] else None
        if not (parties and cy and c["reporter"] in LINKABLE_REPORTERS and cy >= FIRST_DB_YEAR):
            continue
        citing_year = judgments.get(c["citing_case"], {}).get("year") or 9999
        scored = []
        for y in range(cy - 3, cy + 1):            # report year is 0-3 years after the decision
            if y > citing_year:                    # can't cite a case decided after the citing judgment
                continue
            for cid, (j1, j2) in by_year.get(y, ()):
                if cid == c["citing_case"]:
                    continue
                s = min(party_score(parties[0], j1), party_score(parties[1], j2))
                if s >= 75:
                    scored.append((s, cid))
        if not scored:
            continue
        scored.sort(reverse=True)
        best_s, best = scored[0]
        ambiguous = len(scored) > 1 and scored[1][0] >= best_s - 5
        generic = all(len(p.split()) == 1 for p in parties) or parties[0] == parties[1]
        if best_s >= 90 and not ambiguous and not generic:
            c["target"], c["link_method"], c["link_score"] = best, "name_fuzzy", best_s
            report_links[c["report_key"]].add(best)
        else:
            c["link_method"], c["link_score"], c["candidate"] = "needs_review", best_s, best

    # second pass: a report key linked to exactly one judgment -> use that for its other mentions (no name / supra)
    for c in citations:
        if c["link_method"] == "report_key" and len(report_links.get(c["report_key"], ())) == 1:
            c["target"], c["link_method"] = next(iter(report_links[c["report_key"]])), "report_key_via_name"


# ---------------------------------------------------------------- outputs

def build_graph(citations, judgments, out_dir):
    import networkx as nx
    G = nx.MultiDiGraph()
    for cid, j in judgments.items():
        G.add_node(cid, kind="judgment_in_db", parties=j["parties"] or "", year=str(j.get("year") or ""))
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
        case_no TEXT, minutes_date TEXT, report_key TEXT, target TEXT, link_method TEXT, link_score REAL,
        candidate TEXT, start_char INTEGER, context TEXT)""")
    con.executemany("""INSERT INTO citations (citing_case, kind, raw, case_name, reporter, foreign_report, year,
        volume, page, case_no, minutes_date, report_key, target, link_method, link_score, candidate, start_char, context)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(c["citing_case"], c["kind"], c["raw"], c["case_name"], c["reporter"], int(c["foreign"]), c["year"],
          c["volume"], c["page"], c["case_no"], c["minutes_date"], c["report_key"], c["target"], c["link_method"],
          c["link_score"], c["candidate"], c["start"], c["context"]) for c in citations])
    con.commit()


def _already_filled(path):
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as f:
        return any(any(row.get(k, "").strip() for k in row if k and k.startswith("correct_"))
                   for row in csv.DictReader(f))


def write_sample(citations, judgments, out_dir, n=50, seed=42):
    """Pick 50 random judgments (same 50 every run). Never overwrites a sample you have started filling in."""
    cases = sorted(judgments)
    random.Random(seed).shuffle(cases)
    pick = sorted(cases[:n])
    path = os.path.join(out_dir, "citations_sample.csv")
    jpath = os.path.join(out_dir, "citations_sample_judgments.csv")
    if _already_filled(path):
        path = os.path.join(out_dir, "citations_sample_NEW.csv")
        jpath = os.path.join(out_dir, "citations_sample_judgments_NEW.csv")
        print(f"   ! citations_sample.csv already has your answers - not touched. New version: {path}")
    pickset = set(pick)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["citing_case", "kind", "raw", "case_name", "target", "link_method", "candidate",
                    "correct_citation? (Y/N)", "correct_link? (Y/N/NA)", "notes", "context"])
        for c in citations:
            if c["citing_case"] in pickset:
                w.writerow([c["citing_case"], c["kind"], c["raw"], c["case_name"], c["target"], c["link_method"],
                            c["candidate"] or "", "", "", "", c["context"][:400]])
    per = Counter(c["citing_case"] for c in citations)
    with open(jpath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["citing_case", "pdf_path", "n_found", "n_missed (you count)", "missed citations (copy them here)"])
        for cid in pick:
            w.writerow([cid, judgments[cid].get("pdf_path") or "", per[cid], "", ""])
    return pick, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/judgments.db")
    ap.add_argument("--out", default="data")
    ap.add_argument("--limit", type=int, help="only the first N judgments (quick test)")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    q = "SELECT case_id, case_no_raw, parties, listed_year, n_pages, pdf_path, text FROM judgments WHERE status='ok' ORDER BY case_id"
    rows = con.execute(q + (f" LIMIT {int(args.limit)}" if args.limit else "")).fetchall()
    judgments, texts = {}, {}
    for cid, raw_no, p, ly, npg, pdf, t in rows:
        decided = decision_date(t)
        judgments[cid] = {"parties": p, "case_no_raw": raw_no, "n_pages": npg, "pdf_path": pdf, "decided": decided,
                          "year": int(decided[:4]) if decided else ly, "aliases": own_ids(cid, raw_no) - {cid}}
        texts[cid] = t
    print(f"1) {len(judgments)} judgments with text "
          f"(decision date read from the text for {sum(1 for j in judgments.values() if j['decided'])})")

    stats, citations = Counter(), []
    for i, (cid, j) in enumerate(judgments.items(), 1):
        citations += extract_from_judgment(cid, texts.pop(cid), j["n_pages"], j["case_no_raw"], stats)
        if i % 200 == 0:
            print(f"   {i} judgments read, {len(citations)} citations so far")
    print(f"2) {len(citations)} citations found  (ignored: {stats['header_lines_removed']} page-header lines, "
          f"{stats['skipped_own_number']} own case numbers, {stats['skipped_caption_number']} caption numbers)")

    link(citations, judgments)
    save_table(con, citations)
    G = build_graph(citations, judgments, args.out)
    sample, sample_path = write_sample(citations, judgments, args.out)

    print("3) Citations by type     :", dict(Counter(c["kind"] for c in citations)))
    print("   Law reports cited     :", dict(Counter(c["reporter"] for c in citations if c["reporter"]).most_common()))
    print("   How they were linked  :", dict(Counter(c["link_method"] for c in citations).most_common()))
    print(f"   With a case name      : {sum(1 for c in citations if c['case_name'])}/{len(citations)}")
    print(f"   'SC Minutes' dates    : {sum(1 for c in citations if c['minutes_date'])}")
    internal = sum(1 for _, v in G.edges() if G.nodes[v].get("kind") == "judgment_in_db")
    print(f"4) Graph: {G.number_of_nodes()} cases, {G.number_of_edges()} citation links "
          f"({internal} link two judgments in our database)")
    citing = defaultdict(set)
    for u, v in G.edges():
        if G.nodes[v].get("kind") != "foreign":
            citing[v].add(u)
    print("   Most-cited Sri Lankan cases (number of different judgments citing them):")
    for node, s in sorted(citing.items(), key=lambda kv: -len(kv[1]))[:10]:
        print(f"     {len(s):4d}  {node}  {G.nodes[node].get('parties', '')[:70]}")
    print(f"5) Saved: citations table in {args.db}, citation_graph.json/.graphml, "
          f"{os.path.basename(sample_path)} ({len(sample)} judgments for your manual check)")


if __name__ == "__main__":
    main()
