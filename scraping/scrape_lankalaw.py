"""Scrape lankalaw.net A-Z case indexes (SC 1878-2011 + CA 1809-2011).

Saves data/reported_cases_index.csv with columns:
  court, letter, case_name, lksc_ref, citations, decision_date, url
"""
import csv
import os
import re
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "reported_cases_index.csv")

BASES = {
    "SC": "https://lankalaw.net/case-laws/supreme-court-cases-from-1878-2011/all-case-laws-from-1878-2011-{letter}/",
    "CA": "https://lankalaw.net/case-laws/court-of-appeal-cases-from-1809-2011/all-case-laws-from-1809-2011-{letter}/",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (LankaCite research scraper, student project)"}
LI_RE = re.compile(r'<li><a href="([^"]+)"[^>]*>(.+?)</a></li>', re.S)


def fetch(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        except Exception as e:
            print(f"   retry {i+1}/{retries} for {url}: {e}")
            time.sleep(4)
    return None


def clean(s):
    return (s.replace("&#8211;", "-").replace("&#8217;", "'").replace("&amp;", "&")
             .replace("&nbsp;", " ").replace("\n", " ").strip())


DATE_RE = re.compile(r"\(([\d]{1,2}\s+[A-Za-z]+\s+\d{4})\)\s*$")
LKSC_RE = re.compile(r"\[(\d{4})\]\s*(LKSC|LKCA)\s*(\d+)", re.I)
CIT_RE = re.compile(r"(\(\d{4}\)\s*\d*\s*(?:Sri\s*L\.?R\.?|NLR|Bar\.?\s*Rep\.?|BLR)\s*\d+|"
                    r"\d+\s+NLR\s+\d+)")


def parse(txt):
    txt = clean(txt)
    m = DATE_RE.search(txt)
    date = m.group(1) if m else ""
    m2 = LKSC_RE.search(txt)
    lksc = f"[{m2.group(1)}] {m2.group(2).upper()} {m2.group(3)}" if m2 else ""
    cits = "; ".join(CIT_RE.findall(txt))
    # name = everything before " - " first token or before the first LKSC/citation
    name = txt
    for marker in (" [", " - SLR", " - NLR", " - "):
        if marker in name:
            name = name.split(marker)[0]
            break
    return clean(name), lksc, cits, date


rows = []
for court, pat in BASES.items():
    for letter in "abcdefghijklmnopqrstuvwxyz":
        url = pat.format(letter=letter)
        html = fetch(url)
        time.sleep(2)
        if not html:
            print(f"{court} {letter}: FAILED")
            continue
        n = 0
        for m in LI_RE.finditer(html):
            href = m.group(1)
            if "LKSC" not in href and "LKCA" not in href:
                continue
            name, lksc, cits, date = parse(m.group(2))
            if not name:
                continue
            rows.append({"court": court, "letter": letter, "case_name": name,
                         "lksc_ref": lksc, "citations": cits, "decision_date": date,
                         "url": href})
            n += 1
        print(f"{court} {letter}: {n} cases")

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["court", "letter", "case_name", "lksc_ref",
                                      "citations", "decision_date", "url"])
    w.writeheader()
    w.writerows(rows)
print(f"\nwrote {OUT}: {len(rows)} cases")
