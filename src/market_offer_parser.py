from __future__ import annotations

import csv
import base64
import json
import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

from url_normalizer import detect_allegro_url_type, extract_offer_id_from_url, normalize_allegro_url


SAMPLES_ROOT = Path(__file__).resolve().parent.parent / "input" / "firecrawl_samples" / "kinderkraft_wozki"
MARKET_OFFERS_CSV = Path(__file__).resolve().parent.parent / "output" / "market_offers.csv"
AUDIT_CSV = Path(__file__).resolve().parent.parent / "output" / "firecrawl_audit.csv"
AUDIT_SUMMARY_JSON = Path(__file__).resolve().parent.parent / "output" / "firecrawl_audit_summary.json"

PRICE_RE = re.compile(r"(\d[\d\s\xa0]*[,.]\d{2}\s*zł|\d[\d\s\xa0]*\s*zł)", re.IGNORECASE)
RATING_RE = re.compile(r"(\d,\d{1,2})\((\d+)\)")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
URL_RE = re.compile(r"https?://[^\s<>\"]+")
GENERIC_TEXT_PATTERNS = (
    "polityka cookies",
    "pomoc",
    "porownanie",
    "porównanie",
    "ulubione",
    "filtry",
    "sortowanie",
    "przejdź do",
    "przejdz do",
    "następna strona",
    "nastepna strona",
    "poprzednia",
    "podobne",
    "allegro smart",
    "dostosuj ustawienia wyświetlania",
)
GENERIC_ALT_TEXTS = {
    "",
    "smart!",
    "zamknij",
    "logotyp",
    "informacja",
    "pokaż podpowiedź",
    "pokaz podpowiedz",
    "więcej informacji",
    "reklama banerowa",
    "allegro pay",
    "super sprzedawcy",
}
SOURCE_URL_TEMPLATE = "https://allegro.pl/kategoria/wozki-82593?string=kinderkraft"
OUTPUT_COLUMNS = (
    "source_page",
    "source_url",
    "source_file",
    "source_format",
    "offer_id",
    "raw_url",
    "normalized_url",
    "url_type",
    "title",
    "price",
    "rating",
    "reviews_count",
    "is_sponsored",
    "image_alt_texts",
    "nearby_text",
    "extraction_method",
    "confidence",
)


@dataclass(frozen=True)
class SamplePage:
    source_page: str
    source_url: str
    page_dir: Path
    markdown_path: Path
    links_path: Path
    html_path: Path


@dataclass
class MarketOfferCandidate:
    source_page: str
    source_url: str
    source_file: str
    source_format: str
    offer_id: str
    raw_url: str
    normalized_url: str
    url_type: str
    title: str = ""
    price: str = ""
    rating: str = ""
    reviews_count: str = ""
    is_sponsored: bool = False
    image_alt_texts: list[str] = field(default_factory=list)
    nearby_text: str = ""
    extraction_method: str = ""
    confidence: float = 0.0

    def dedupe_key(self) -> str:
        if self.offer_id:
            return f"offer_id:{self.offer_id}"
        if self.normalized_url:
            return f"normalized_url:{self.normalized_url}"
        if self.raw_url:
            return f"raw_url:{self.raw_url}"
        return ""

    def to_row(self) -> dict[str, str]:
        data = asdict(self)
        data["offer_id"] = normalize_offer_id(self.offer_id)
        data["is_sponsored"] = "true" if self.is_sponsored else "false"
        data["image_alt_texts"] = " | ".join(self.image_alt_texts)
        data["confidence"] = f"{self.confidence:.2f}"
        return {key: str(data.get(key, "")) for key in OUTPUT_COLUMNS}


def normalize_text(value: str) -> str:
    return " ".join((value or "").replace("\xa0", " ").split()).strip()


def normalize_offer_id(value: object) -> str:
    text = normalize_text(str(value))
    if text.isdigit():
        return text
    try:
        decimal_value = Decimal(text)
    except InvalidOperation:
        return ""
    if decimal_value == decimal_value.to_integral_value():
        return format(decimal_value.quantize(Decimal("1")), "f")
    return ""


def looks_generic_text(value: str) -> bool:
    lowered = normalize_text(value).lower()
    return any(pattern in lowered for pattern in GENERIC_TEXT_PATTERNS)


def clean_alt_text(value: str) -> str:
    text = normalize_text(value)
    lowered = text.lower()
    if lowered in GENERIC_ALT_TEXTS:
        return ""
    if looks_generic_text(text):
        return ""
    return text


def infer_source_url(page_number: int) -> str:
    if page_number <= 1:
        return SOURCE_URL_TEMPLATE
    return f"{SOURCE_URL_TEMPLATE}&p={page_number}"


def load_sample_pages(samples_root: Path = SAMPLES_ROOT) -> list[SamplePage]:
    pages: list[SamplePage] = []
    if not samples_root.exists():
        return pages

    for page_dir in sorted(path for path in samples_root.iterdir() if path.is_dir()):
        match = re.search(r"page_(\d+)$", page_dir.name)
        if not match:
            continue
        page_number = int(match.group(1))
        pages.append(
            SamplePage(
                source_page=page_dir.name,
                source_url=infer_source_url(page_number),
                page_dir=page_dir,
                markdown_path=page_dir / "markdown.md",
                links_path=page_dir / "links.txt",
                html_path=page_dir / "html.html",
            )
        )
    return pages


def normalize_market_url(raw_url: str) -> tuple[str, str, str]:
    normalized = normalize_allegro_url(raw_url)
    url_type = detect_allegro_url_type(normalized.normalized_url)
    normalized_url = normalized.normalized_url if url_type in {"offer", "product"} else ""
    offer_id = normalized.offer_id or extract_offer_id_from_url(normalized_url or raw_url)
    return normalized_url, offer_id, url_type


def looks_like_offer_link(raw_url: str, normalized_url: str, url_type: str) -> bool:
    if url_type in {"offer", "product"} and normalized_url:
        return True
    lowered = raw_url.lower()
    return (
        "type=offer" in lowered
        or "emission_element_type=offer" in lowered
        or "offerid=" in lowered
    )


def extract_prices(text: str) -> list[str]:
    return [normalize_text(match.group(1)) for match in PRICE_RE.finditer(text)]


def extract_prices_from_text_parts(parts: list[str]) -> list[str]:
    joined = " ".join(normalize_text(part) for part in parts if normalize_text(part))
    joined = re.sub(r"(\d),\s+(\d{2})", r"\1,\2", joined)
    joined = re.sub(r"(\d)\s+zł", r"\1 zł", joined)
    return extract_prices(joined)


def select_primary_price(parts: list[str]) -> str:
    joined = " ".join(normalize_text(part) for part in parts if normalize_text(part))
    joined = re.sub(r"(\d),\s+(\d{2})", r"\1,\2", joined)
    joined = re.sub(r"(\d)\s+zł", r"\1 zł", joined)

    joined_candidates: list[str] = []
    for match in PRICE_RE.finditer(joined):
        context = joined[max(0, match.start() - 20) : match.end() + 40].lower()
        if any(marker in context for marker in (" rat", "ratz", "z dostaw", "cena z 30 dni")):
            continue
        joined_candidates.append(normalize_text(match.group(1)))
    if joined_candidates:
        return joined_candidates[-1]

    candidates: list[str] = []
    fallback: list[str] = []
    for part in parts:
        text = normalize_text(part)
        prices = extract_prices_from_text_parts([text])
        fallback.extend(prices)
        lowered = text.lower()
        if any(marker in lowered for marker in (" rat", "ratz", "z dostaw", "cena z 30 dni")):
            continue
        candidates.extend(prices)
    return (candidates or fallback or [""])[-1]


def extract_rating_and_reviews(lines: list[str], index: int) -> tuple[str, str]:
    start = max(0, index - 6)
    end = min(len(lines), index + 6)
    for pointer in range(start, end):
        match = RATING_RE.search(lines[pointer])
        if match:
            return match.group(1), match.group(2)
    return "", ""


def extract_nearby_text(lines: list[str], index: int, window: int = 6) -> str:
    start = max(0, index - window)
    end = min(len(lines), index + window + 1)
    chunk = " ".join(normalize_text(line) for line in lines[start:end] if normalize_text(line))
    return chunk[:800]


def is_sponsored_url(raw_url: str) -> bool:
    parsed = urlparse(raw_url)
    if parsed.path not in {"/events/clicks", "/dss-proxy/clicks"}:
        return False

    decoded = unquote(raw_url).lower()
    query = parse_qs(parsed.query)
    redirect = unquote(query.get("redirect", [""])[0])
    if redirect and not redirect.lower().startswith(("http://", "https://")):
        try:
            redirect += "=" * (-len(redirect) % 4)
            redirect = base64.urlsafe_b64decode(redirect).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            redirect = ""

    ad_text = f"{decoded} {unquote(redirect).lower()}"
    return "bi_s=ads" in ad_text or "ads_premium" in ad_text or "productlisting" in ad_text


def _offer_keys_in_line(line: str) -> set[str]:
    keys: set[str] = set()
    for _, raw_url in MARKDOWN_LINK_RE.findall(line):
        normalized_url, offer_id, url_type = normalize_market_url(normalize_text(raw_url))
        if looks_like_offer_link(raw_url, normalized_url, url_type):
            keys.add(offer_id or normalized_url)
    return keys


def extract_markdown_offer_block(lines: list[str], index: int, offer_key: str) -> list[str]:
    start = max(0, index - 160)
    end = min(len(lines), index + 160)

    for pointer in range(index - 1, start - 1, -1):
        keys = _offer_keys_in_line(lines[pointer])
        if keys and offer_key not in keys:
            start = pointer + 1
            break

    for pointer in range(index + 1, end):
        keys = _offer_keys_in_line(lines[pointer])
        if keys and offer_key not in keys:
            end = pointer
            break

    return lines[start:end]


def extract_compact_markdown_card(lines: list[str], index: int, title: str) -> list[str]:
    """Return the image-to-link card when Firecrawl emits compact sponsored tiles."""
    normalized_title = normalize_text(title).lower()
    start = max(0, index - 20)
    for pointer in range(index - 1, start - 1, -1):
        if lines[pointer].strip().startswith("## ["):
            break
        alt_texts = [normalize_text(alt).lower() for alt, _ in MARKDOWN_IMAGE_RE.findall(lines[pointer])]
        if any(alt == normalized_title for alt in alt_texts):
            return lines[pointer : index + 1]
    return []


def extract_image_alts_from_lines(lines: list[str], index: int) -> list[str]:
    start = max(0, index - 30)
    collected: list[str] = []
    for pointer in range(index - 1, start - 1, -1):
        line = lines[pointer]
        if pointer < index - 1 and line.strip().startswith("## ["):
            break
        for alt, _ in MARKDOWN_IMAGE_RE.findall(line):
            cleaned = clean_alt_text(alt)
            if cleaned:
                collected.append(cleaned)
    unique = list(dict.fromkeys(reversed(collected)))
    return unique[:20]


def extract_price_from_markdown_block(block: list[str]) -> str:
    return select_primary_price(block)


def score_confidence(title: str, price: str, rating: str, image_alt_texts: list[str], normalized_url: str, is_sponsored: bool, source_format: str) -> float:
    score = 0.2
    if normalized_url:
        score += 0.3
    if title:
        score += 0.2
    if price:
        score += 0.1
    if rating:
        score += 0.05
    if image_alt_texts:
        score += 0.1
    if is_sponsored:
        score += 0.03
    if source_format == "html":
        score += 0.01
    if source_format == "links":
        score -= 0.15
    return max(0.05, min(score, 0.99))


def candidate_quality_score(candidate: MarketOfferCandidate) -> float:
    score = candidate.confidence
    if candidate.title:
        score += 0.08
    if candidate.price:
        score += 0.08
    if candidate.rating:
        score += 0.06
    if candidate.reviews_count:
        score += 0.04
    if candidate.is_sponsored:
        score += 0.03
    if candidate.image_alt_texts:
        score += 0.02
    if candidate.source_format == "markdown":
        score += 0.03
    return score


def extraction_method_rank(candidate: MarketOfferCandidate) -> int:
    method = candidate.extraction_method
    if "markdown_h2" in method:
        return 4
    if "html_offer_tile" in method:
        return 3
    if "markdown_link" in method:
        return 2
    if "links_url" in method:
        return 1
    return 0


def select_best_field(candidates: list[MarketOfferCandidate], field_name: str) -> str:
    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: (extraction_method_rank(candidate), candidate_quality_score(candidate)),
        reverse=True,
    )
    for candidate in sorted_candidates:
        value = getattr(candidate, field_name)
        if isinstance(value, str) and value:
            return value
    return ""


def choose_url_from_markdown_line(line: str) -> tuple[str, str]:
    for title, url in MARKDOWN_LINK_RE.findall(line):
        cleaned_title = normalize_text(title.strip("*"))
        cleaned_url = normalize_text(url)
        if cleaned_title and cleaned_url:
            return cleaned_title, cleaned_url
    return "", ""


def parse_markdown_candidates(page: SamplePage) -> list[MarketOfferCandidate]:
    if not page.markdown_path.exists():
        return []

    lines = page.markdown_path.read_text(encoding="utf-8").splitlines()
    candidates: list[MarketOfferCandidate] = []

    for index, raw_line in enumerate(lines):
        line = normalize_text(raw_line)
        if not line or "[" not in line or "](" not in line:
            continue

        title, raw_url = choose_url_from_markdown_line(line)
        if not title or not raw_url or looks_generic_text(title):
            continue

        normalized_url, offer_id, url_type = normalize_market_url(raw_url)
        if not looks_like_offer_link(raw_url, normalized_url, url_type):
            continue

        method = "markdown_h2" if line.startswith("## [") else "markdown_link"
        offer_key = offer_id or normalized_url
        compact_card = extract_compact_markdown_card(lines, index, title) if method == "markdown_link" else []
        offer_block = compact_card or extract_markdown_offer_block(lines, index, offer_key)
        price = extract_price_from_markdown_block(offer_block)
        rating, reviews_count = extract_rating_and_reviews(lines, index)
        image_alt_texts = extract_image_alts_from_lines(lines, index)
        sponsored = is_sponsored_url(raw_url) or any("sponsorowane" in line.lower() for line in offer_block)
        nearby_text = extract_nearby_text(lines, index)
        candidates.append(
            MarketOfferCandidate(
                source_page=page.source_page,
                source_url=page.source_url,
                source_file=str(page.markdown_path.relative_to(page.page_dir.parent.parent.parent)),
                source_format="markdown",
                offer_id=normalize_offer_id(offer_id),
                raw_url=raw_url,
                normalized_url=normalized_url,
                url_type=url_type,
                title=title,
                price=price,
                rating=rating,
                reviews_count=reviews_count,
                is_sponsored=sponsored,
                image_alt_texts=image_alt_texts,
                nearby_text=nearby_text,
                extraction_method=method,
                confidence=score_confidence(title, price, rating, image_alt_texts, normalized_url, sponsored, "markdown"),
            )
        )

    return candidates


def parse_links_candidates(page: SamplePage) -> list[MarketOfferCandidate]:
    if not page.links_path.exists():
        return []

    candidates: list[MarketOfferCandidate] = []
    for raw_line in page.links_path.read_text(encoding="utf-8").splitlines():
        raw_url = normalize_text(raw_line)
        if not raw_url.startswith("http"):
            continue
        normalized_url, offer_id, url_type = normalize_market_url(raw_url)
        if not looks_like_offer_link(raw_url, normalized_url, url_type):
            continue

        candidates.append(
            MarketOfferCandidate(
                source_page=page.source_page,
                source_url=page.source_url,
                source_file=str(page.links_path.relative_to(page.page_dir.parent.parent.parent)),
                source_format="links",
                offer_id=normalize_offer_id(offer_id),
                raw_url=raw_url,
                normalized_url=normalized_url,
                url_type=url_type,
                extraction_method="links_url",
                confidence=score_confidence("", "", "", [], normalized_url, False, "links"),
            )
        )

    return candidates


class OfferTileHTMLParser(HTMLParser):
    def __init__(self, source_page: str, source_url: str, source_file: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_page = source_page
        self.source_url = source_url
        self.source_file = source_file
        self.stack: list[str] = []
        self.tiles: list[dict[str, object]] = []
        self.current_tile: dict[str, object] | None = None
        self.current_anchor_href: str | None = None
        self.tile_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: (value or "") for key, value in attrs}
        self.stack.append(tag)

        if attr_map.get("data-role") == "offer-tile":
            raw_url = attr_map.get("data-analytics-view-opbox-custom-destination-url", "")
            offer_id = attr_map.get("data-analytics-view-custom-item-id", "")
            self.current_tile = {
                "raw_url": unquote(raw_url),
                "offer_id": normalize_offer_id(offer_id),
                "title": "",
                "texts": [],
                "image_alt_texts": [],
                "is_sponsored": is_sponsored_url(unquote(raw_url)),
            }
            self.tile_depth = 1
            return

        if self.current_tile is None:
            return

        if tag == "div":
            self.tile_depth += 1

        if tag == "a":
            href = attr_map.get("href", "")
            self.current_anchor_href = unquote(href) if href else None
            if href and not self.current_tile.get("raw_url"):
                self.current_tile["raw_url"] = unquote(href)

        if tag == "img":
            alt = clean_alt_text(attr_map.get("alt", ""))
            if alt:
                image_alt_texts = self.current_tile.setdefault("image_alt_texts", [])
                if isinstance(image_alt_texts, list) and alt not in image_alt_texts:
                    image_alt_texts.append(alt)

    def handle_endtag(self, tag: str) -> None:
        if self.current_tile is not None and tag == "a":
            self.current_anchor_href = None

        if self.stack:
            self.stack.pop()

        if self.current_tile is not None and tag == "div":
            self.tile_depth -= 1
            if self.tile_depth > 0:
                return

            raw_url = str(self.current_tile.get("raw_url", ""))
            normalized_url, offer_id, url_type = normalize_market_url(raw_url)
            title = normalize_text(str(self.current_tile.get("title", "")))
            texts = [normalize_text(text) for text in self.current_tile.get("texts", []) if normalize_text(str(text))]
            price = select_primary_price(texts)
            rating_match = None
            for text in texts:
                rating_match = RATING_RE.search(text)
                if rating_match:
                    break

            candidate = MarketOfferCandidate(
                source_page=self.source_page,
                source_url=self.source_url,
                source_file=self.source_file,
                source_format="html",
                offer_id=normalize_offer_id(offer_id or self.current_tile.get("offer_id", "")),
                raw_url=raw_url,
                normalized_url=normalized_url,
                url_type=url_type,
                title=title,
                price=price,
                rating=rating_match.group(1) if rating_match else "",
                reviews_count=rating_match.group(2) if rating_match else "",
                is_sponsored=bool(self.current_tile.get("is_sponsored", False)),
                image_alt_texts=list(self.current_tile.get("image_alt_texts", [])),
                nearby_text=" ".join(texts)[:800],
                extraction_method="html_offer_tile",
                confidence=score_confidence(
                    title,
                    price,
                    rating_match.group(1) if rating_match else "",
                    list(self.current_tile.get("image_alt_texts", [])),
                    normalized_url,
                    bool(self.current_tile.get("is_sponsored", False)),
                    "html",
                ),
            )
            if looks_like_offer_link(candidate.raw_url, candidate.normalized_url, candidate.url_type):
                self.tiles.append(candidate.__dict__)
            self.current_tile = None
            self.tile_depth = 0

    def handle_data(self, data: str) -> None:
        if self.current_tile is None:
            return

        text = normalize_text(data)
        if not text:
            return

        texts = self.current_tile.setdefault("texts", [])
        if isinstance(texts, list):
            texts.append(text)

        if text.lower() == "sponsorowane":
            self.current_tile["is_sponsored"] = True

        if self.current_anchor_href:
            raw_url = str(self.current_tile.get("raw_url", ""))
            if self.current_anchor_href == raw_url or self.current_anchor_href in raw_url or raw_url in self.current_anchor_href:
                current_title = normalize_text(str(self.current_tile.get("title", "")))
                if len(text) > len(current_title) and not looks_generic_text(text):
                    self.current_tile["title"] = text


def parse_html_candidates(page: SamplePage) -> list[MarketOfferCandidate]:
    if not page.html_path.exists():
        return []

    parser = OfferTileHTMLParser(
        source_page=page.source_page,
        source_url=page.source_url,
        source_file=str(page.html_path.relative_to(page.page_dir.parent.parent.parent)),
    )
    parser.feed(page.html_path.read_text(encoding="utf-8"))
    candidates: list[MarketOfferCandidate] = []
    for tile in parser.tiles:
        candidates.append(MarketOfferCandidate(**tile))
    return candidates


def parse_all_candidates(pages: Iterable[SamplePage]) -> list[MarketOfferCandidate]:
    candidates: list[MarketOfferCandidate] = []
    for page in pages:
        candidates.extend(parse_markdown_candidates(page))
        candidates.extend(parse_links_candidates(page))
        candidates.extend(parse_html_candidates(page))
    return candidates


def _prefer_value(current: str, incoming: str) -> str:
    return current if current else incoming


def merge_candidates(existing: MarketOfferCandidate, incoming: MarketOfferCandidate) -> MarketOfferCandidate:
    candidates = [existing, incoming]
    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: (candidate_quality_score(candidate), extraction_method_rank(candidate)),
        reverse=True,
    )
    primary = sorted_candidates[0]
    secondary = sorted_candidates[1]

    merged = MarketOfferCandidate(
        source_page=primary.source_page,
        source_url=primary.source_url,
        source_file=primary.source_file,
        source_format=primary.source_format,
        offer_id=select_best_field(candidates, "offer_id"),
        raw_url=select_best_field(candidates, "raw_url"),
        normalized_url=select_best_field(candidates, "normalized_url"),
        url_type=select_best_field(candidates, "url_type"),
        title=select_best_field(candidates, "title"),
        price=select_best_field(candidates, "price"),
        rating=select_best_field(candidates, "rating"),
        reviews_count=select_best_field(candidates, "reviews_count"),
        is_sponsored=primary.is_sponsored or secondary.is_sponsored,
        image_alt_texts=list(dict.fromkeys(primary.image_alt_texts + secondary.image_alt_texts)),
        nearby_text=select_best_field(candidates, "nearby_text"),
        extraction_method=f"{primary.extraction_method}+{secondary.extraction_method}" if secondary.extraction_method not in primary.extraction_method else primary.extraction_method,
        confidence=max(primary.confidence, secondary.confidence),
    )
    return merged


def deduplicate_candidates(candidates: Iterable[MarketOfferCandidate]) -> list[MarketOfferCandidate]:
    deduped: dict[str, MarketOfferCandidate] = {}
    for candidate in candidates:
        key = candidate.dedupe_key()
        if not key:
            continue
        if key in deduped:
            deduped[key] = merge_candidates(deduped[key], candidate)
        else:
            deduped[key] = candidate
    return list(deduped.values())


def write_market_offers_csv(candidates: Iterable[MarketOfferCandidate], output_path: Path = MARKET_OFFERS_CSV) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(candidate.to_row())


def build_url_statistics_from_files(page: SamplePage) -> dict[str, int]:
    file_paths = [path for path in (page.markdown_path, page.links_path, page.html_path) if path.exists()]
    all_urls: list[str] = []
    for file_path in file_paths:
        content = file_path.read_text(encoding="utf-8")
        all_urls.extend(URL_RE.findall(content))

    normalized_offer_urls = 0
    offer_ids = 0
    for raw_url in all_urls:
        normalized_url, offer_id, url_type = normalize_market_url(raw_url)
        if url_type in {"offer", "product"} and normalized_url:
            normalized_offer_urls += 1
        if offer_id:
            offer_ids += 1

    return {
        "files_count": len(file_paths),
        "all_links_count": len(all_urls),
        "offer_links_count": sum(1 for url in all_urls if "/oferta/" in url),
        "product_links_count": sum(1 for url in all_urls if "/produkt/" in url),
        "events_clicks_count": sum(1 for url in all_urls if "/events/clicks" in url),
        "dss_proxy_clicks_count": sum(1 for url in all_urls if "/dss-proxy/clicks" in url),
        "normalized_offer_links_count": normalized_offer_urls,
        "offer_ids_count": offer_ids,
    }


def build_audit(pages: list[SamplePage]) -> tuple[list[dict[str, int | str]], dict[str, int]]:
    all_candidates = parse_all_candidates(pages)
    deduped = deduplicate_candidates(all_candidates)

    per_page_rows: list[dict[str, int | str]] = []
    total = {
        "pages_count": len(pages),
        "files_count": 0,
        "all_links_count": 0,
        "offer_links_count": 0,
        "product_links_count": 0,
        "events_clicks_count": 0,
        "dss_proxy_clicks_count": 0,
        "normalized_offer_links_count": 0,
        "offer_ids_count": 0,
        "offer_candidates_before_deduplication": len(all_candidates),
        "offer_candidates_after_deduplication": len(deduped),
        "with_title_count": sum(1 for item in deduped if item.title),
        "with_price_count": sum(1 for item in deduped if item.price),
        "with_rating_count": sum(1 for item in deduped if item.rating),
        "with_image_alt_texts_count": sum(1 for item in deduped if item.image_alt_texts),
        "sponsored_count": sum(1 for item in deduped if item.is_sponsored),
    }

    for page in pages:
        page_stats = build_url_statistics_from_files(page)
        page_candidates = [item for item in all_candidates if item.source_page == page.source_page]
        page_deduped = deduplicate_candidates(page_candidates)
        row = {
            "source_page": page.source_page,
            "source_url": page.source_url,
            **page_stats,
            "offer_candidates_before_deduplication": len(page_candidates),
            "offer_candidates_after_deduplication": len(page_deduped),
            "with_title_count": sum(1 for item in page_deduped if item.title),
            "with_price_count": sum(1 for item in page_deduped if item.price),
            "with_rating_count": sum(1 for item in page_deduped if item.rating),
            "with_image_alt_texts_count": sum(1 for item in page_deduped if item.image_alt_texts),
            "sponsored_count": sum(1 for item in page_deduped if item.is_sponsored),
        }
        per_page_rows.append(row)

        for key, value in page_stats.items():
            total[key] += value

    return per_page_rows, total


def write_audit_outputs(rows: list[dict[str, int | str]], summary: dict[str, int], csv_path: Path = AUDIT_CSV, json_path: Path = AUDIT_SUMMARY_JSON) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    if fieldnames:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
