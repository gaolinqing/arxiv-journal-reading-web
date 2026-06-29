#!/usr/bin/env python3
"""Fetch daily arXiv and PRL metadata for the reading app."""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ARXIV_API = "https://export.arxiv.org/api/query"
CROSSREF_WORKS_API = "https://api.crossref.org/works"
PRL_ISSN = "0031-9007"
ARXIV_RECENT_URLS = {
    "hep-ph": "https://arxiv.org/list/hep-ph/recent",
    "astro-ph.HE": "https://arxiv.org/list/astro-ph.HE/recent",
}
PRL_RECENT_URL = "https://journals.aps.org/prl/recent?toc_section%5B%5D=cosmology-astrophysics-and-gravitation"
PRD_RECENT_URL = "https://journals.aps.org/prd/recent"
APS_BASE_URL = "https://journals.aps.org"
PRL_FALLBACK_INCLUDE = [
    r"\bastrophys",
    r"\bblack hole",
    r"\bcosmic",
    r"\bcosmolog",
    r"\bdark matter",
    r"\bdark energy",
    r"\bgamma[- ]ray",
    r"\bgravitation",
    r"\bgravitational wave",
    r"\binflation",
    r"\bneutrino",
    r"\bpulsar",
    r"\btev\b",
]
PRL_FALLBACK_EXCLUDE = [
    r"\bcondensed matter",
    r"\bmagnon",
    r"\bmany[- ]body",
    r"\bphonon",
    r"\bquasiparticle",
    r"\bspin\b",
    r"\bsuperconduct",
    r"\btopological",
]


def request_text(url: str, user_agent: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def clean_text(value: Optional[str]) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_arxiv_date(value: str) -> str:
    return value[:10]


def fetch_arxiv_category(category: str, max_results: int, user_agent: str) -> list[dict]:
    query = urllib.parse.urlencode(
        {
            "search_query": f"cat:{category}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(max_results),
        }
    )
    xml_text = request_text(f"{ARXIV_API}?{query}", user_agent, timeout=45)
    root = ET.fromstring(xml_text)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    papers = []

    for entry in root.findall("atom:entry", ns):
        arxiv_url = clean_text(entry.findtext("atom:id", namespaces=ns))
        arxiv_id = arxiv_url.rsplit("/", 1)[-1]
        authors = [
            clean_text(author.findtext("atom:name", namespaces=ns))
            for author in entry.findall("atom:author", ns)
        ]
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href", "")

        papers.append(
            {
                "source": "arxiv",
                "source_label": f"arXiv {category}",
                "category": category,
                "source_url": ARXIV_RECENT_URLS.get(category, ""),
                "id": f"arXiv:{arxiv_id}",
                "title": clean_text(entry.findtext("atom:title", namespaces=ns)),
                "authors": authors,
                "abstract": clean_text(entry.findtext("atom:summary", namespaces=ns)),
                "published": parse_arxiv_date(clean_text(entry.findtext("atom:published", namespaces=ns))),
                "updated": parse_arxiv_date(clean_text(entry.findtext("atom:updated", namespaces=ns))),
                "url": arxiv_url,
                "pdf_url": pdf_url,
            }
        )

    return papers


class ApsRecentParser(HTMLParser):
    """Small tolerant parser for APS recent article listing pages."""

    def __init__(self) -> None:
        super().__init__()
        self.papers: list[dict] = []
        self.current: Optional[dict] = None
        self.stack: list[str] = []
        self.capture: Optional[str] = None
        self.capture_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr = dict(attrs)
        classes = attr.get("class", "")
        href = attr.get("href", "")
        self.stack.append(classes)

        if tag == "div" and "article" in classes and self.current is None:
            self.current = {"title": "", "authors": [], "abstract": "", "published": "", "url": ""}

        if self.current is None:
            return

        if tag == "a" and "/prl/abstract/" in href and not self.current.get("url"):
            self.current["url"] = urllib.parse.urljoin(APS_BASE_URL, href)
            doi = href.rsplit("/", 1)[-1]
            self.current["doi"] = doi
            self.current["doi_url"] = f"https://doi.org/{doi}"
            self.capture = "title"
            self.capture_chunks = []
            return

        if any(name in classes for name in ["authors", "article-authors"]):
            self.capture = "authors"
            self.capture_chunks = []
        elif any(name in classes for name in ["description", "abstract", "article-description"]):
            self.capture = "abstract"
            self.capture_chunks = []
        elif any(name in classes for name in ["pub-info", "published", "article-meta"]):
            self.capture = "published"
            self.capture_chunks = []

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.capture_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current is not None and self.capture:
            value = clean_text(" ".join(self.capture_chunks))
            if self.capture == "authors":
                self.current["authors"] = split_authors(value)
            elif value:
                self.current[self.capture] = value
            self.capture = None
            self.capture_chunks = []

        if self.current is not None and tag == "div" and self.stack:
            classes = self.stack.pop()
            if "article" in classes:
                if self.current.get("title") and self.current.get("url"):
                    self.papers.append(format_prl_paper(self.current))
                self.current = None
        elif self.stack:
            self.stack.pop()


def split_authors(value: str) -> list[str]:
    value = re.sub(r"\band\b", ",", value)
    return [clean_text(part) for part in value.split(",") if clean_text(part)]


def format_prl_paper(item: dict) -> dict:
    published_match = re.search(r"\b\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\b|\b[A-Z][a-z]+\s+\d{1,2},\s+\d{4}\b", item.get("published", ""))
    return {
        "source": "prl",
        "source_label": "PRL Cosmology/Astrophysics/Gravitation",
        "category": "prl",
        "source_url": PRL_RECENT_URL,
        "doi": item.get("doi", ""),
        "title": clean_text(item.get("title", "")),
        "authors": item.get("authors", []),
        "abstract": clean_text(item.get("abstract", "")),
        "published": published_match.group(0) if published_match else clean_text(item.get("published", "")),
        "url": item.get("url", ""),
        "doi_url": item.get("doi_url", ""),
    }


def fetch_prl(user_agent: str) -> list[dict]:
    html_text = request_text(PRL_RECENT_URL, user_agent)
    if "cf-mitigated" in html_text or "Just a moment" in html_text or "challenge-platform" in html_text:
        raise RuntimeError("APS PRL page returned a Cloudflare challenge instead of article HTML.")
    parser = ApsRecentParser()
    parser.feed(html_text)
    return parser.papers


def crossref_date(parts: dict) -> str:
    date_parts = parts.get("date-parts") or []
    if not date_parts or not date_parts[0]:
        return ""
    values = date_parts[0]
    year = values[0]
    month = values[1] if len(values) > 1 else 1
    day = values[2] if len(values) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def author_name(author: dict) -> str:
    given = author.get("given", "")
    family = author.get("family", "")
    return clean_text(f"{given} {family}") or clean_text(author.get("name", ""))


def prl_fallback_matches(item: dict) -> bool:
    title = " ".join(item.get("title", []))
    abstract = item.get("abstract", "")
    subject = " ".join(item.get("subject", []))
    text = clean_text(f"{title} {abstract} {subject}").lower()
    if any(re.search(pattern, text) for pattern in PRL_FALLBACK_EXCLUDE):
        return False
    return any(re.search(pattern, text) for pattern in PRL_FALLBACK_INCLUDE)


def fetch_prl_crossref_fallback(days_back: int, rows: int, user_agent: str) -> list[dict]:
    today = dt.date.today()
    from_date = today - dt.timedelta(days=days_back)
    filters = ",".join(
        [
            f"issn:{PRL_ISSN}",
            f"from-pub-date:{from_date.isoformat()}",
            f"until-pub-date:{today.isoformat()}",
            "type:journal-article",
        ]
    )
    query = urllib.parse.urlencode(
        {
            "filter": filters,
            "sort": "published",
            "order": "desc",
            "rows": str(rows),
            "select": "DOI,title,author,abstract,published-print,published-online,published,URL,subject,container-title",
        }
    )
    data = json.loads(request_text(f"{CROSSREF_WORKS_API}?{query}", user_agent, timeout=15))
    papers = []

    for item in data.get("message", {}).get("items", []):
        if not prl_fallback_matches(item):
            continue
        doi = item.get("DOI", "")
        published = (
            crossref_date(item.get("published-online", {}))
            or crossref_date(item.get("published-print", {}))
            or crossref_date(item.get("published", {}))
        )
        papers.append(
            {
                "source": "prl",
                "source_label": "PRL fallback",
                "category": "prl",
                "source_url": PRL_RECENT_URL,
                "doi": doi,
                "title": clean_text(" ".join(item.get("title", []))),
                "authors": [author_name(author) for author in item.get("author", [])],
                "abstract": clean_text(re.sub(r"<[^>]+>", " ", item.get("abstract", ""))),
                "published": published,
                "url": item.get("URL", ""),
                "doi_url": f"https://doi.org/{doi}" if doi else item.get("URL", ""),
            }
        )

    return papers


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_payload(args: argparse.Namespace) -> dict:
    user_agent = f"{args.user_agent} (mailto:{args.email})" if args.email else args.user_agent
    generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    local_date = dt.date.today()
    papers: list[dict] = []
    warnings: list[str] = []

    window_start = local_date - dt.timedelta(days=args.window_days - 1)

    for category in args.categories:
        papers.extend(fetch_arxiv_category(category, args.arxiv_max_results, user_agent))
        time.sleep(args.pause)

    try:
        papers.extend(fetch_prl(user_agent))
    except Exception as exc:
        if args.allow_prl_fallback:
            fallback_papers = fetch_prl_crossref_fallback(args.prl_fallback_days_back, args.prl_fallback_rows, user_agent)
            papers.extend(fallback_papers)
            warning = f"APS PRL page was blocked ({exc}); showing {len(fallback_papers)} PRL fallback records from Crossref keyword filtering."
        else:
            warning = f"PRL is manual: APS blocks scripted access ({exc}). Open the PRL source directly: {PRL_RECENT_URL}"
        warnings.append(warning)
        print(f"Warning: {warning}", file=sys.stderr)

    seen = set()
    unique_papers = []
    for paper in papers:
        paper_date = paper.get("published") or paper.get("updated") or ""
        if paper_date[:10] < window_start.isoformat() or paper_date[:10] > local_date.isoformat():
            continue
        key = paper.get("id") or paper.get("doi") or paper.get("url") or paper.get("title")
        if key in seen:
            continue
        seen.add(key)
        unique_papers.append(paper)

    return {
        "generated_at": generated_at,
        "local_date": local_date.isoformat(),
        "time_windows": {
            "today": local_date.isoformat(),
            "week_days": args.window_days,
        },
        "sources": {
            "arxiv_recent_urls": {category: ARXIV_RECENT_URLS.get(category, "") for category in args.categories},
            "arxiv_api_categories": args.categories,
            "prl_recent_url": PRL_RECENT_URL,
            "prd_recent_url": PRD_RECENT_URL,
            "prl_fallback": "Disabled by default because Crossref cannot identify the APS PRL section exactly.",
        },
        "warnings": warnings,
        "papers": unique_papers,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--categories", nargs="+", default=["astro-ph.HE", "hep-ph"])
    parser.add_argument("--arxiv-max-results", type=int, default=160)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--allow-prl-fallback", action="store_true")
    parser.add_argument("--prl-fallback-days-back", type=int, default=60)
    parser.add_argument("--prl-fallback-rows", type=int, default=50)
    parser.add_argument("--pause", type=float, default=3.0, help="Pause between arXiv API requests.")
    parser.add_argument("--email", default="", help="Optional contact email for polite API use.")
    parser.add_argument("--user-agent", default="arxiv-prl-reading-app/0.1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload(args)
    today = dt.date.today().isoformat()
    write_json(DATA_DIR / "latest.json", payload)
    write_json(DATA_DIR / f"{today}.json", payload)
    print(f"Wrote {len(payload['papers'])} papers to {DATA_DIR / 'latest.json'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"fetch_papers.py failed: {exc}", file=sys.stderr)
        raise
