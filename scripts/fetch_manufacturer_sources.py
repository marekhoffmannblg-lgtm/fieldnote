"""Fetch official manufacturer pages and manuals as primary research sources.

The script intentionally keeps manufacturer content separate from marketplace
offer pages.  It does not call Firecrawl and does not alter model groups or AI
state; those are updated by the existing registry and grouping scripts.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from firecrawl_client import FirecrawlClient, FirecrawlError


ROOT = Path(__file__).resolve().parent.parent
SOURCES_ROOT = ROOT / "input" / "manufacturer_sources"
USER_AGENT = "BenchmarkResearchBot/1.0 (+local manufacturer research)"
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def normalized_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[a-z0-9]+", normalized.lower())


def contains_exact_model(text: str, model: str) -> bool:
    """Match model tokens as a phrase, never through a substring match."""
    wanted = normalized_tokens(model)
    haystack = normalized_tokens(text)
    if not wanted or len(wanted) > len(haystack):
        return False
    return any(haystack[index:index + len(wanted)] == wanted for index in range(len(haystack) - len(wanted) + 1))


def canonicalize_url(value: str) -> str:
    parsed = urlparse(html.unescape(value.strip()))
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", urlencode(query), ""))


def source_identifier(brand: str, canonical_url: str) -> str:
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]
    return f"manufacturer:{slug(brand)}:{digest}"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def atomic_write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    if isinstance(content, bytes):
        temporary.write_bytes(content)
    else:
        temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


class PageParser(HTMLParser):
    """Small dependency-free HTML to research markdown converter."""

    BLOCK_TAGS = {"p", "div", "section", "article", "li", "tr", "td", "th", "br"}
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._chunks: list[str] = []
        self._current: list[str] = []
        self._current_heading = 0
        self._skip_depth = 0
        self._in_title = False
        self._link_href = ""
        self._link_text: list[str] = []
        self.links: list[dict[str, str]] = []

    def flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._current)).strip()
        self._current = []
        if not text:
            return
        if self._current_heading:
            self._chunks.append(f"{'#' * self._current_heading} {text}")
            self._current_heading = 0
        else:
            self._chunks.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        attributes = dict(attrs)
        if tag in self.BLOCK_TAGS:
            self.flush()
        if tag in self.HEADING_TAGS:
            self.flush()
            self._current_heading = int(tag[1])
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._link_href = attributes.get("href") or ""
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag == "a":
            link_text = re.sub(r"\s+", " ", "".join(self._link_text)).strip()
            if self._link_href:
                self.links.append({"url": html.unescape(self._link_href), "text": link_text})
            self._link_href = ""
            self._link_text = []
        if tag in self.HEADING_TAGS | self.BLOCK_TAGS:
            self.flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
        self._current.append(data)
        if self._link_href:
            self._link_text.append(data)

    def markdown(self) -> str:
        self.flush()
        lines: list[str] = []
        previous = ""
        for line in self._chunks:
            if line != previous:
                lines.append(line)
            previous = line
        return "\n\n".join(lines).strip() + ("\n" if lines else "")


def technical_clean(markdown: str) -> str:
    """Remove obvious navigation and consent text without inventing product facts."""
    noisy_markers = (
        "dbamy o twoja prywatnosc", "ustawienia plikow cookie", "cookies", "polityka prywatnosci",
        "zapisz sie do newslettera", "obserwuj nas", "wszystkie prawa zastrzezone",
    )
    result: list[str] = []
    for line in markdown.splitlines():
        plain = " ".join(normalized_tokens(line))
        if any(marker in plain for marker in noisy_markers):
            continue
        result.append(line)
    return "\n".join(result).strip() + ("\n" if result else "")


def fetch_bytes(url: str, *, expect_pdf: bool = False) -> tuple[bytes, dict[str, str], int]:
    """Fetch through the shared Firecrawl client; direct HTTP is dev-only."""
    if os.getenv("FIELDNOTE_ALLOW_DIRECT_HTTP") != "1":
        try:
            formats = ["pdf", "markdown", "html", "rawHtml"] if expect_pdf else ["markdown", "html", "rawHtml"]
            response = FirecrawlClient(timeout=60).scrape(url, formats=formats)
        except FirecrawlError as exc:
            raise RuntimeError(str(exc)) from exc
        data = response.data
        candidate = data.get("pdf") or data.get("rawBinary") or data.get("binary")
        if isinstance(candidate, str):
            if candidate.startswith("data:") and "," in candidate:
                candidate = candidate.split(",", 1)[1]
            try:
                candidate = base64.b64decode(candidate, validate=True)
            except (ValueError, TypeError):
                candidate = candidate.encode("utf-8")
        body = candidate if isinstance(candidate, bytes) else str(data.get("html") or data.get("rawHtml") or data.get("markdown") or "").encode("utf-8")
        if expect_pdf and not body.startswith(b"%PDF"):
            raise RuntimeError("Firecrawl nie zwrócił artefaktu PDF dla pdf-url.")
        content_type = "application/pdf" if expect_pdf else "text/html; charset=utf-8"
        return body, {"Content-Type": content_type, "X-Firecrawl-Request-Id": response.request_id}, response.status_code
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"})
    with urlopen(request, timeout=30) as response:  # nosec B310 - explicit user supplied official URL
        body = response.read()
        headers = {key: value for key, value in response.headers.items()}
        if expect_pdf and not body.startswith(b"%PDF"):
            raise RuntimeError("Odpowiedź pdf-url nie jest prawidłowym PDF-em.")
        return body, headers, int(getattr(response, "status", 200))


def infer_language(text: str) -> str:
    lowered = text.lower()
    return "pl" if any(word in lowered for word in ("wózek", "wozek", "produkt", "instrukcja", "koła", "kola")) else ""


def infer_source_type(url: str, is_pdf: bool) -> str:
    if is_pdf:
        return "manufacturer_manual_pdf"
    path = urlparse(url).path.lower()
    if any(marker in path for marker in ("support", "serwis", "pomoc", "help")):
        return "manufacturer_support_page"
    return "manufacturer_product_page"


def page_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return re.sub(r"\s+", " ", fallback).strip()


def write_source(
    *, brand: str, model: str, url: str, is_pdf: bool, resume: bool,
) -> tuple[str, bool, list[str]]:
    canonical_url = canonicalize_url(url)
    source_id = source_identifier(brand, canonical_url)
    target = SOURCES_ROOT / f"{slug(brand)}__{slug(model)}" / source_id
    metadata_path = target / "metadata.json"
    if resume and metadata_path.exists():
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        expected = target / ("document.pdf" if is_pdf else "page.html")
        valid_existing = expected.exists() and (not is_pdf or expected.read_bytes().startswith(b"%PDF"))
        if existing.get("canonical_url") == canonical_url and valid_existing:
            return source_id, True, ["resume_skipped_existing_source"]

    body, headers, status = fetch_bytes(url, expect_pdf=is_pdf)
    warnings: list[str] = []
    raw_response: dict[str, Any] = {
        "url": url,
        "canonical_url": canonical_url,
        "status": status,
        "headers": headers,
        "fetched_at": now(),
        "content_length": len(body),
    }
    title = ""
    links: list[dict[str, str]] = []
    document_pages: list[dict[str, Any]] = []

    if is_pdf:
        if not body.startswith(b"%PDF"):
            raise ValueError("Odmowa zapisania document.pdf: brak sygnatury %PDF.")
        atomic_write(target / "document.pdf", body)
        raw_response["body_encoding"] = "base64"
        raw_response["body_base64"] = base64.b64encode(body).decode("ascii")
        text = ""
        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]

            reader = PdfReader(target / "document.pdf")
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = (page.extract_text() or "").strip()
                heading = next((line.strip() for line in page_text.splitlines() if line.strip()), "")
                document_pages.append({"page_number": page_number, "heading": heading[:200], "text": page_text})
            text = "\n\n".join(
                f"## Strona {item['page_number']}\n\n### {item['heading']}\n\n{item['text']}".strip()
                for item in document_pages if item["text"]
            )
            if not text:
                warnings.append("pdf_text_not_extractable")
        except ImportError:
            warnings.append("pdf_text_extraction_dependency_missing_pypdf")
        except Exception as exc:  # malformed PDFs should still remain auditable
            warnings.append(f"pdf_text_extraction_failed:{type(exc).__name__}")
        title = next((item["heading"] for item in document_pages if item["heading"]), "")
        atomic_write(target / "document_text.md", text)
        atomic_write(target / "page.html", "")
        markdown = text
    else:
        charset_match = re.search(r"charset=([^;\s]+)", headers.get("Content-Type", ""), flags=re.IGNORECASE)
        encoding = charset_match.group(1).strip('"\'') if charset_match else "utf-8"
        decoded = body.decode(encoding, errors="replace")
        raw_response["body_encoding"] = "utf-8"
        raw_response["body"] = decoded
        parser = PageParser()
        parser.feed(decoded)
        parser.close()
        markdown = parser.markdown()
        title = page_title(markdown, parser.title)
        links = parser.links
        atomic_write(target / "page.html", decoded)

    cleaned = technical_clean(markdown)
    model_match = contains_exact_model(f"{title}\n{cleaned}", model)
    if not model_match:
        warnings.append("exact_model_name_not_found")
    content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    metadata = {
        "source_id": source_id,
        "brand": brand,
        "model": model,
        "marketplace": "manufacturer",
        "source_type": infer_source_type(canonical_url, is_pdf),
        "source_url": url,
        "canonical_url": canonical_url,
        "domain": urlparse(canonical_url).netloc.lower(),
        "title": title,
        "language": infer_language(cleaned),
        "fetched_at": now(),
        "content_hash": content_hash,
        "authority_level": "primary",
        "model_match": model_match,
        "model_variant": model if model_match else "",
        "region": "PL" if urlparse(canonical_url).netloc.lower().endswith(".pl") else "",
        "warnings": warnings,
        "document_pages": document_pages,
    }
    raw_response["title"] = title
    raw_response["warnings"] = warnings
    atomic_write(target / "raw_response.json", json.dumps(raw_response, ensure_ascii=False, indent=2))
    atomic_write(target / "markdown.md", markdown)
    atomic_write(target / "technical_clean.md", cleaned)
    atomic_write(target / "extracted_links.json", json.dumps(links, ensure_ascii=False, indent=2))
    atomic_write(metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2))
    return source_id, False, warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pobiera oficjalne źródła producenta jako źródła pierwotne.")
    parser.add_argument("--brand", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--url", required=True, help="Oficjalna strona produktu lub wsparcia.")
    parser.add_argument("--pdf-url", help="Opcjonalny oficjalny PDF instrukcji.")
    parser.add_argument("--resume", action="store_true", help="Pomiń już zapisane źródła o tym samym canonical URL.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results: list[tuple[str, bool, list[str], bool]] = []
    for url, is_pdf in ((args.url, False), (args.pdf_url, True)):
        if not url:
            continue
        try:
            source_id, skipped, warnings = write_source(
                brand=args.brand.strip(), model=args.model.strip(), url=url.strip(), is_pdf=is_pdf, resume=args.resume,
            )
            results.append((source_id, skipped, warnings, is_pdf))
            print(f"source_id={source_id}")
            print(f"source_status={'skipped' if skipped else 'fetched'}")
            if warnings:
                print(f"warnings={','.join(warnings)}")
        except Exception as exc:
            print(f"source_error={type(exc).__name__}:{exc}")
            return 1
    fetched = sum(not skipped for _source, skipped, _warnings, _pdf in results)
    print(f"manufacturer_sources_fetched={fetched}")
    print(f"manufacturer_pages={sum(not pdf and not skipped for _source, skipped, _warnings, pdf in results)}")
    print(f"manufacturer_pdfs={sum(pdf and not skipped for _source, skipped, _warnings, pdf in results)}")
    print(f"manufacturer_sources_skipped={sum(skipped for _source, skipped, _warnings, _pdf in results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
