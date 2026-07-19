from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from url_normalizer import extract_offer_id_from_url


LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
PRICE_RE = re.compile(r"(\d[\d\s\xa0]*[,.]\d{2}\s*zł|\d[\d\s\xa0]*\s*zł)", re.IGNORECASE)
IGNORE_TEXT_PATTERNS = (
    "polityka cookies",
    "regulamin",
    "pomoc",
    "porownanie",
    "porównanie",
    "ulubione",
    "zaloguj",
    "zarejestruj",
    "kup allegro smart",
    "smart!",
    "szukaj",
    "wyniki wyszukiwania",
    "nastepna strona",
    "następna strona",
    "poprzednia strona",
    "podobne wyszukiwania",
    "sugerowane",
    "sprawdź również",
    "sprawdz rowniez",
    "baner",
    "reklama",
)
IGNORE_URL_PATTERNS = (
    "/pomoc",
    "/regulamin",
    "/moje-allegro",
    "/smart",
    "#",
)


@dataclass(frozen=True)
class ParsedListing:
    source_file: str
    page_url: str
    title: str
    price: str
    url: str
    offer_id: str
    is_sponsored: bool


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().split()).lower()


def _is_ignored_link(title: str, url: str) -> bool:
    normalized_title = _normalize(title)
    normalized_url = url.lower()

    if any(pattern in normalized_title for pattern in IGNORE_TEXT_PATTERNS):
        return True
    if any(pattern in normalized_url for pattern in IGNORE_URL_PATTERNS):
        return True
    if "allegro.pl" not in normalized_url and not normalized_url.startswith("/"):
        return True
    if "/oferta/" not in normalized_url and "/events/clicks" not in normalized_url and "/dss-proxy/clicks" not in normalized_url:
        return True
    return False


def _extract_price(lines: list[str], index: int) -> str:
    nearby = lines[index : index + 4]
    for line in nearby:
        match = PRICE_RE.search(line)
        if match:
            return " ".join(match.group(1).split())
    return ""


def _is_sponsored(lines: list[str], index: int) -> bool:
    start = max(0, index - 2)
    end = min(len(lines), index + 3)
    context = " ".join(lines[start:end]).lower()
    return "sponsorowane" in context


def _strip_markdown_prefix(line: str) -> str:
    return re.sub(r"^\s*(?:#+|\-|\*|\d+\.)\s*", "", line).strip()


def parse_markdown_listings(markdown: str, source_file: str = "", page_url: str = "") -> list[ParsedListing]:
    lines = [line.rstrip() for line in markdown.splitlines() if line.strip()]
    results: list[ParsedListing] = []

    for index, line in enumerate(lines):
        prepared_line = _strip_markdown_prefix(line)
        match = LINK_RE.search(prepared_line)
        if not match:
            continue

        title = " ".join(match.group(1).split())
        raw_url = match.group(2).strip()
        absolute_url = urljoin(page_url, raw_url) if page_url else raw_url

        if not title or _is_ignored_link(title, absolute_url):
            continue

        price = _extract_price(lines, index)
        offer_id = extract_offer_id_from_url(absolute_url)
        results.append(
            ParsedListing(
                source_file=source_file,
                page_url=page_url,
                title=title,
                price=price,
                url=absolute_url,
                offer_id=offer_id,
                is_sponsored=_is_sponsored(lines, index),
            )
        )

    return results
