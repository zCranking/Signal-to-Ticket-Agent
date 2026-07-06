"""SEC EDGAR API fetcher and filing parser."""
import re
import time
import requests
from typing import Optional
from .config import EDGAR_USER_AGENT

HEADERS = {"User-Agent": EDGAR_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
EDGAR_BASE = "https://data.sec.gov"
SEC_BASE = "https://www.sec.gov"

_ticker_to_cik: dict[str, str] = {}


def get_cik(ticker: str) -> Optional[str]:
    global _ticker_to_cik
    if not _ticker_to_cik:
        resp = requests.get(
            f"{SEC_BASE}/files/company_tickers.json", headers=HEADERS, timeout=10
        )
        resp.raise_for_status()
        for entry in resp.json().values():
            _ticker_to_cik[entry["ticker"].upper()] = str(entry["cik_str"]).zfill(10)
    return _ticker_to_cik.get(ticker.upper())


def get_recent_8k(ticker: str, count: int = 5) -> list[dict]:
    cik = get_cik(ticker)
    if not cik:
        return []

    resp = requests.get(f"{EDGAR_BASE}/submissions/CIK{cik}.json", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    items = recent.get("items", [])

    results = []
    for i, form in enumerate(forms):
        if form == "8-K" and len(results) < count:
            results.append({
                "ticker": ticker,
                "cik": cik,
                "form": "8-K",
                "filing_date": dates[i] if i < len(dates) else "",
                "accession": accessions[i] if i < len(accessions) else "",
                "primary_document": primary_docs[i] if i < len(primary_docs) else "",
                "items": items[i] if i < len(items) else "",
            })
    return results


def fetch_filing_text(cik: str, accession: str, primary_document: str = "") -> str:
    acc_clean = accession.replace("-", "")
    cik_int = int(cik)

    if primary_document:
        url = f"{SEC_BASE}/Archives/edgar/data/{cik_int}/{acc_clean}/{primary_document}"
    else:
        index_url = f"{SEC_BASE}/Archives/edgar/data/{cik_int}/{acc_clean}/"
        resp = requests.get(index_url, headers=HEADERS, timeout=10)
        hrefs = re.findall(r'href="([^"]+\.(htm|txt))"', resp.text, re.IGNORECASE)
        if not hrefs:
            return ""
        doc_path = hrefs[0][0]
        url = f"{SEC_BASE}{doc_path}" if doc_path.startswith("/") else f"{SEC_BASE}/Archives/edgar/data/{cik_int}/{acc_clean}/{doc_path}"

    time.sleep(0.12)  # EDGAR polite rate limit
    resp = requests.get(url, headers=HEADERS, timeout=15)
    text = _strip_html(resp.text)
    return text[:8000]


def get_recent_filing_text(cik: str, form_types: list[str] = None) -> str:
    """Fetch most recent 10-Q or 10-K text for freshness check."""
    if form_types is None:
        form_types = ["10-Q", "10-K"]

    resp = requests.get(f"{EDGAR_BASE}/submissions/CIK{cik}.json", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    for i, form in enumerate(forms):
        if form in form_types:
            pd = primary_docs[i] if i < len(primary_docs) else ""
            return fetch_filing_text(cik, accessions[i], pd)

    return ""


_ENTITIES = {
    "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
    "&quot;": '"', "&apos;": "'", "&#8217;": "'", "&#8220;": '"',
    "&#8221;": '"', "&#8211;": "-", "&#8212;": "--",
}


def _strip_html(html: str) -> str:
    """Reduce an EDGAR filing to prose the classifier can use.

    Filings arrive as inline-XBRL HTML wrapped in SGML headers; most of the
    byte count is markup and cover-page metadata, not disclosure text.
    """
    # Drop script/style blocks and SGML/XBRL header sections entirely
    text = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<\?xml[\s\S]*?\?>", " ", text)
    text = re.sub(r"<(SEC-HEADER|IMS-HEADER)[\s\S]*?</\1>", " ", text, flags=re.IGNORECASE)

    text = re.sub(r"<[^>]+>", " ", text)

    for entity, char in _ENTITIES.items():
        text = text.replace(entity, char)
    text = re.sub(r"&#?\w+;", " ", text)  # remaining entities

    text = re.sub(r"\s+", " ", text).strip()

    # Skip past the cover page to the first Item disclosure when present
    match = re.search(r"Item\s+\d+\.\d+", text)
    if match and match.start() > 200:
        text = text[match.start():]

    return text
