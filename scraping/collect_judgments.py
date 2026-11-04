"""
LankaCite - Step 1: Collect Sri Lankan Supreme Court judgments.

Sources
  1. lankalaw.net  - one index page per year (2009-2025): Case No. | Parties (linked to PDF)
  2. supremecourt.lk - one page per month: Date | Case No. | Parties | Judgment by | Keywords | ...
     (optional: list the monthly page URLs in supremecourt_pages.txt, one per line)

What it does
  - reads the index pages and builds one metadata table
  - normalises case numbers so the same case from both sources is merged
  - downloads each PDF (skips files already downloaded, so you can re-run safely)
  - extracts the text with PyMuPDF
  - saves everything to data/judgments.db (SQLite) and data/judgments.csv

Run on Google Colab:
  !pip install requests beautifulsoup4 pymupdf pandas
  !python collect_judgments.py --years 2009-2025 --out data
  # quick test first:
  !python collect_judgments.py --years 2021 --limit 10 --out data

Please be polite to these sites: keep the delay, and don't run many copies at once.
"""

import argparse
import csv
import os
import re
import sqlite3
import time
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

LANKALAW_YEAR_URL = "https://lankalaw.net/supreme-court-law-reports-{year}/"
HEADERS = {"User-Agent": "LankaCite research crawler (academic project)"}
DELAY_SECONDS = 2.0

# ---------------------------------------------------------------- case numbers

# Case types we recognise, mapped to one standard label.
CASE_TYPES = [
    # added in step 2 (only catch formats the older patterns below could not parse)
    (r"s\.?\s*c\.?\s*[\(/\-\s]*c\.?\s*h\.?\s*c\.?\s*\)?\s*/?\s*(?:appea?l+)?", "SC_CHC"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*h\.?\s*c\.?\s*c\.?\s*a\.?\s*\)?\s*[\(/\-\s]*l\.?\s*a\.?", "SC_HCCA_LA"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*h\.?\s*c\.?\s*\)\s*[/\-\s]*l\.?\s*a\.?", "SC_HC_LA"),   # SC (HC) LA
    (r"s\.?\s*c\.?\s*[\(/\-\s]*\(?\s*s\.?\s*p\.?\s*l\.?\s*[\)/\-]\s*[/\-\s]*l\.?\s*a\.?", "SC_SPL_LA"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*t\.?\s*a\.?\s*b\b\.?", "SC_TAB"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*writ\b", "SC_WRIT"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*misc?(?:ellaneous)?\b\.?", "SC_MISC"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*exp(?:ulsion)?\b\.?", "SC_EXP"),
    (r"\bc\.?\s*a\.?\s*[\(/\-\s]*wri?t\b", "CA_WRIT"),
    (r"\bc\.?\s*a\.?\s*[\(/\-\s]*p\.?\s*h\.?\s*c\.?\s*\)?", "CA_PHC"),
    # original step-1 patterns
    (r"s\.?\s*c\.?\s*[\(/\-\s]*f\.?\s*/?\s*r\.?\)?", "SC_FR"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*h\.?\s*c\.?\s*[\(/\-\s]*l\.?\s*a\.?", "SC_HC_LA"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*s\.?\s*p\.?\s*l\.?\s*l\.?\s*a\.?", "SC_SPL_LA"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*l\.?\s*a\.?", "SC_LA"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*appea?l+", "SC_APPEAL"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*rule", "SC_RULE"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*s\.?\s*d\.?", "SC_SD"),
    (r"s\.?\s*c\.?\s*[\(/\-\s]*reference", "SC_REF"),
]


def _full_year(y: str) -> str:
    y = y.strip()
    if len(y) == 4:
        return y
    n = int(y)
    return str(2000 + n) if n <= 40 else str(1900 + n)


def normalise_case_no(raw: str) -> str | None:
    """'sc-fr-403-2016', 'SC (FR) Application No. 256/2017', 'scfr_542_09.pdf'
    -> 'SC_FR_403_2016' etc. Returns None if it can't be parsed."""
    if not raw:
        return None
    s = unquote(raw).lower().replace("_", " ").replace("-", " ")
    s = re.sub(r"\.pdf$", "", s)
    s = re.sub(r"\b(application|no\.?|number)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    ctype = None
    for pattern, label in CASE_TYPES:
        m = re.search(pattern, s)
        if m:
            ctype = label
            s = s[m.end():]
            break
    if not ctype:
        return None
    m = re.search(r"(\d{1,5})\s*[/\s]\s*(\d{2,4})\b", s)
    if not m:
        return None
    number, year = str(int(m.group(1))), _full_year(m.group(2))
    return f"{ctype}_{number}_{year}"


# ---------------------------------------------------------------- index pages

def get(url: str, session: requests.Session, binary=False):
    for attempt in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=60)
            if r.status_code == 200:
                return r.content if binary else r.text
            print(f"  ! HTTP {r.status_code} for {url}")
            return None
        except requests.RequestException as e:
            print(f"  ! attempt {attempt + 1} failed for {url}: {e}")
            time.sleep(5 * (attempt + 1))
    return None


def parse_lankalaw_year(html: str, page_url: str, year: int) -> list[dict]:
    """Rows look like: <td>sc-fr-403-2016</td><td><a href='...pdf'><em>Perera v. ...</em></a></td>"""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        link = tr.find("a", href=re.compile(r"\.pdf", re.I))
        if len(cells) < 2 or not link:
            continue
        raw_no = cells[0].get_text(" ", strip=True)
        pdf_url = urljoin(page_url, link["href"])
        rows.append({
            "case_id": normalise_case_no(raw_no) or normalise_case_no(os.path.basename(pdf_url)),
            "case_no_raw": raw_no,
            "parties": cells[1].get_text(" ", strip=True),
            "pdf_url": pdf_url,
            "listed_year": year,
            "judgment_date": "",
            "judge": "",
            "keywords": "",
            "source": "lankalaw",
        })
    return rows


def parse_supremecourt_month(html: str, page_url: str) -> list[dict]:
    """Columns: Date of Judgment | Case No. | Parties | Judgment by | Keywords | Legislation | Document.
    Reads the header row to find columns, so it still works if their order changes."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for table in soup.find_all("table"):
        header = [c.get_text(" ", strip=True).lower() for c in table.find("tr").find_all(["th", "td"])] \
            if table.find("tr") else []

        def col(name):
            for i, h in enumerate(header):
                if name in h:
                    return i
            return None

        i_date, i_no, i_parties = col("date"), col("case"), col("part")
        i_judge, i_kw = col("judgment by"), col("keyword")
        if i_no is None:
            continue
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if len(cells) <= i_no:
                continue
            link = tr.find("a", href=re.compile(r"\.pdf", re.I))
            text = lambda i: cells[i].get_text(" ", strip=True) if i is not None and i < len(cells) else ""
            raw_no = text(i_no)
            rows.append({
                "case_id": normalise_case_no(raw_no),
                "case_no_raw": raw_no,
                "parties": text(i_parties),
                "pdf_url": urljoin(page_url, link["href"]) if link else "",
                "listed_year": None,
                "judgment_date": text(i_date),
                "judge": text(i_judge),
                "keywords": text(i_kw),
                "source": "supremecourt",
            })
    return rows


def merge(records: list[dict]) -> dict[str, dict]:
    """One record per case. supremecourt.lk adds date/judge/keywords; lankalaw usually has the PDF."""
    merged: dict[str, dict] = {}
    unparsed = 0
    for r in records:
        key = r["case_id"]
        if not key:
            unparsed += 1
            key = f"UNPARSED_{unparsed}"
            r["case_id"] = key
        if key not in merged:
            merged[key] = dict(r)
            continue
        m = merged[key]
        for field in ("pdf_url", "parties", "judgment_date", "judge", "keywords", "listed_year"):
            if not m.get(field) and r.get(field):
                m[field] = r[field]
        if r["source"] not in m["source"]:
            m["source"] += "+" + r["source"]
    if unparsed:
        print(f"  note: {unparsed} case numbers could not be parsed (kept as UNPARSED_n - check them by hand)")
    return merged


# ---------------------------------------------------------------- PDFs + text

def extract_text(pdf_path: str) -> tuple[str, int]:
    import fitz  # PyMuPDF
    with fitz.open(pdf_path) as doc:
        return "\n".join(page.get_text() for page in doc), doc.page_count


def save(records: dict[str, dict], out_dir: str):
    db_path = os.path.join(out_dir, "judgments.db")
    con = sqlite3.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS judgments (
        case_id TEXT PRIMARY KEY, case_no_raw TEXT, parties TEXT, judgment_date TEXT,
        judge TEXT, keywords TEXT, listed_year INTEGER, source TEXT, pdf_url TEXT,
        pdf_path TEXT, n_pages INTEGER, n_chars INTEGER, status TEXT, text TEXT)""")
    cols = ["case_id", "case_no_raw", "parties", "judgment_date", "judge", "keywords", "listed_year",
            "source", "pdf_url", "pdf_path", "n_pages", "n_chars", "status", "text"]
    con.executemany(f"INSERT OR REPLACE INTO judgments ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [[r.get(c) for c in cols] for r in records.values()])
    con.commit()
    con.close()
    with open(os.path.join(out_dir, "judgments.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols[:-1], extrasaction="ignore")
        w.writeheader()
        w.writerows(records.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2009-2025", help="e.g. 2021 or 2009-2025")
    ap.add_argument("--supremecourt-pages", default="supremecourt_pages.txt",
                    help="optional text file with supremecourt.lk monthly page URLs, one per line")
    ap.add_argument("--limit", type=int, default=0, help="download only this many PDFs (for testing)")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    a, _, b = args.years.partition("-")
    years = range(int(a), int(b or a) + 1)
    pdf_dir = os.path.join(args.out, "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    session = requests.Session()
    records: list[dict] = []

    print("1) Reading lankalaw.net year pages")
    for y in years:
        url = LANKALAW_YEAR_URL.format(year=y)
        html = get(url, session)
        found = parse_lankalaw_year(html, url, y) if html else []
        print(f"   {y}: {len(found)} cases")
        records += found
        time.sleep(DELAY_SECONDS)

    if os.path.exists(args.supremecourt_pages):
        print("2) Reading supremecourt.lk monthly pages")
        for url in [l.strip() for l in open(args.supremecourt_pages) if l.strip()]:
            html = get(url, session)
            found = parse_supremecourt_month(html, url) if html else []
            print(f"   {url}: {len(found)} cases")
            records += found
            time.sleep(DELAY_SECONDS)
    else:
        print("2) No supremecourt_pages.txt found - skipping supremecourt.lk (optional)")

    merged = merge(records)
    print(f"3) {len(merged)} unique cases after merging")

    print("4) Downloading PDFs and extracting text")
    done = 0
    for case_id, r in merged.items():
        if args.limit and done >= args.limit:
            r["status"] = "not_attempted"
            continue
        if not r.get("pdf_url"):
            r["status"] = "no_pdf_link"
            continue
        path = os.path.join(pdf_dir, f"{case_id}.pdf")
        if not os.path.exists(path):
            data = get(r["pdf_url"], session, binary=True)
            time.sleep(DELAY_SECONDS)
            if not data or not data[:5] == b"%PDF-":
                r["status"] = "download_failed"
                continue
            with open(path, "wb") as f:
                f.write(data)
        try:
            text, pages = extract_text(path)
        except Exception as e:  # damaged PDF
            r["status"] = f"pdf_error: {e}"
            continue
        r.update(pdf_path=path, text=text, n_pages=pages, n_chars=len(text),
                 status="ok" if len(text.strip()) > 500 else "little_text_maybe_scanned")
        done += 1
        if done % 25 == 0:
            print(f"   {done} done")
            save(merged, args.out)  # save progress

    save(merged, args.out)
    statuses: dict[str, int] = {}
    for r in merged.values():
        statuses[r.get("status") or "unknown"] = statuses.get(r.get("status") or "unknown", 0) + 1
    print("5) Finished. Status summary:", statuses)
    print(f"   Saved to {os.path.join(args.out, 'judgments.db')} and judgments.csv")


if __name__ == "__main__":
    main()