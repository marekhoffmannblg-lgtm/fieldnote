"""Shared offline visual-context contracts for FIELDNOTE source adapters.

Visual artifacts describe the page context of a source.  They never create
product facts or evidence on their own, so the text quality gate remains the
only producer of benchmark data.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from p0_runtime import atomic_write_json, atomic_write_text


ROOT = Path(__file__).resolve().parent.parent
VISUAL_SCHEMA_VERSION = "1"
NOISE_MARKERS = (
    "recommendation", "recommended", "similar products", "similar offer",
    "propozycje", "podobne oferty", "sponsored", "sponsorowane", "cookie",
    "footer", "delivery", "payment", "newsletter", "icon", "logo",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalized(value: object) -> str:
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def stable_id(prefix: str, *values: object) -> str:
    basis = "|".join(normalized(value).casefold() for value in values)
    return f"{prefix}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:20]}"


def relative_path(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return None


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


@dataclass
class VisualSourceSnapshotV1:
    schema_version: str = VISUAL_SCHEMA_VERSION
    visual_snapshot_id: str = ""
    source_id: str = ""
    product_slug: str = ""
    source_type: str = "other"
    canonical_url: str = ""
    capture_status: str = "partial"
    capture_provider: str = "cache_html"
    full_page_screenshot_path: str | None = None
    rendered_html_path: str | None = None
    viewport: dict[str, int] | None = None
    page_dimensions: dict[str, int] | None = None
    blocks_count: int = 0
    media_count: int = 0
    content_hash: str = ""
    captured_at: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None


@dataclass
class VisualBlockV1:
    schema_version: str = VISUAL_SCHEMA_VERSION
    block_id: str = ""
    visual_snapshot_id: str = ""
    source_id: str = ""
    product_slug: str = ""
    region: str = "other"
    heading: str | None = None
    body_text: str | None = None
    page_order: int | None = None
    dom_path: str | None = None
    bounding_box: dict[str, float] | None = None
    section_screenshot_path: str | None = None
    media_ids: list[str] = field(default_factory=list)
    classification: str = "possibly_relevant"
    classification_reason: str | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass
class MediaAssetV1:
    schema_version: str = VISUAL_SCHEMA_VERSION
    media_id: str = ""
    visual_snapshot_id: str = ""
    block_id: str | None = None
    source_id: str = ""
    product_slug: str = ""
    media_type: str = "image"
    original_url: str | None = None
    resolved_url: str | None = None
    local_path: str | None = None
    alt_text: str | None = None
    title_text: str | None = None
    caption_text: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    content_hash: str | None = None
    role: str = "unknown"
    exact_product_match: bool | None = None
    used_as_visual_context: bool = False
    created_at: str = field(default_factory=utc_now)


class Node:
    def __init__(self, tag: str, attrs: dict[str, str], parent: "Node | None" = None) -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[Node] = []
        self.parts: list[str] = []
        self.order = 0

    @property
    def class_name(self) -> str:
        return self.attrs.get("class", "")

    def text(self) -> str:
        values = list(self.parts)
        for child in self.children:
            values.append(child.text())
        return normalized(" ".join(values))


class TreeParser(HTMLParser):
    VOID = {"img", "source", "br", "meta", "link", "input", "hr", "area", "embed"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {})
        self.current = self.root
        self.index = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.index += 1
        node = Node(tag.lower(), {key.lower(): value or "" for key, value in attrs}, self.current)
        node.order = self.index
        self.current.children.append(node)
        if tag.lower() not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        node = self.current
        while node.parent is not None and node.tag != tag.lower():
            node = node.parent
        if node.parent is not None:
            self.current = node.parent

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.current.parts.append(data)


def walk(node: Node) -> Iterable[Node]:
    yield node
    for child in node.children:
        yield from walk(child)


def node_path(node: Node) -> str:
    parts: list[str] = []
    current: Node | None = node
    while current and current.parent:
        token = current.tag
        if current.attrs.get("id"):
            token += f"#{current.attrs['id']}"
        elif current.class_name:
            token += "." + ".".join(current.class_name.split()[:2])
        parts.append(token)
        current = current.parent
    return " > ".join(reversed(parts))


def is_noise(node: Node) -> bool:
    text = f"{node.class_name} {node.attrs.get('id', '')} {node.text()}".casefold()
    return any(marker in text for marker in NOISE_MARKERS)


def first_heading(node: Node) -> str | None:
    for child in walk(node):
        if child.attrs.get("data-role") == "title":
            value = child.text()
            if value:
                return value[:300]
        if child.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            value = child.text()
            if value:
                return value[:300]
        if "title" in child.class_name.casefold() or "heading" in child.class_name.casefold():
            value = child.text()
            if value and len(value) < 300:
                return value
    return None


def first_body(node: Node, heading: str | None) -> str | None:
    candidates: list[str] = []
    for child in walk(node):
        class_name = child.class_name.casefold()
        if child.attrs.get("data-role") == "description" or child.tag in {"p", "figcaption"} or "text" in class_name or "description" in class_name or "caption" in class_name:
            value = child.text()
            if value and value != heading and len(value) > 12:
                candidates.append(value)
    if not candidates:
        value = node.text()
        if heading and value.startswith(heading):
            value = value[len(heading):].strip()
        candidates.append(value)
    value = normalized(candidates[0] if candidates else "")
    return value[:900] if value else None


def media_urls(node: Node) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for child in walk(node):
        if child.tag not in {"img", "source", "video", "picture"}:
            continue
        values = [child.attrs.get(key, "") for key in ("src", "data-src", "data-lazy-src", "poster")]
        for srcset_key in ("srcset", "data-srcset"):
            values.extend(item.strip().split(" ")[0] for item in child.attrs.get(srcset_key, "").split(",") if item.strip())
        for value in values:
            url = normalized(value)
            if url and not url.startswith("data:"):
                records.append({"url": url, "tag": child.tag, "alt": normalized(child.attrs.get("alt", "")), "title": normalized(child.attrs.get("title", ""))})
    return records


def media_type(url: str, tag: str) -> str:
    path = urlparse(url).path.casefold()
    if tag == "video" or path.endswith((".webm", ".mp4", ".mov")):
        return "video"
    if "poster" in path:
        return "video_poster"
    return "image"


def region_for(node: Node, source_type: str) -> str:
    token = f"{node.class_name} {node.attrs.get('id', '')}".casefold()
    if "recommend" in token:
        return "recommendation"
    if "dimension" in token or "specification" in token:
        return "dimensions"
    if "included" in token or "in-the-box" in token or "zestaw" in token:
        return "included"
    if "accessor" in token:
        return "accessory"
    if "gallery" in token or "carousel" in token or "image" in token:
        return "gallery" if source_type == "marketplace" else "feature"
    return "feature"


def choose_container(media_node: Node, source_type: str) -> Node:
    current: Node | None = media_node
    best = media_node
    for _ in range(6):
        if current is None:
            break
        text = current.text()
        classes = current.class_name.casefold()
        if source_type == "manufacturer" and ("b-highlight" in classes or "feature-panel" in classes or "highlight" in classes):
            return current
        if len(text) <= 1500 and (first_heading(current) or len(media_urls(current)) == 1):
            best = current
        current = current.parent
    return best


def artifact_directory(source_id: str, product_slug: str = "") -> Path | None:
    if source_id.startswith("allegro:"):
        offer_id = source_id.split(":", 1)[1]
        candidate = ROOT / "input" / "firecrawl_offer_pages" / offer_id
        return candidate if candidate.exists() else None
    if source_id.startswith("manufacturer:"):
        roots = [ROOT / "input" / "manufacturer_sources" / product_slug] if product_slug else []
        roots.append(ROOT / "input" / "manufacturer_sources")
        for base in roots:
            for candidate in base.glob("**/metadata.json"):
                metadata = read_json(candidate, {})
                if isinstance(metadata, dict) and str(metadata.get("source_id", "")) == source_id:
                    return candidate.parent
    return None


def source_metadata(source_id: str, directory: Path, product_slug: str) -> tuple[str, str, str, str]:
    metadata = read_json(directory / "metadata.json", {})
    if not isinstance(metadata, dict):
        metadata = {}
    canonical_url = str(metadata.get("canonical_url") or metadata.get("source_url") or "")
    if not canonical_url and source_id.startswith("allegro:"):
        offer_sections = read_json(directory / "offer_sections.json", {})
        if isinstance(offer_sections, dict):
            canonical_url = str(offer_sections.get("source_url") or "")
    source_type = "manufacturer" if source_id.startswith("manufacturer:") else "marketplace"
    if not product_slug:
        if source_type == "manufacturer":
            product_slug = directory.parent.name
        else:
            product_slug = ""
    html_path = directory / ("page.html" if (directory / "page.html").exists() else "html.html")
    return product_slug, source_type, canonical_url, relative_path(html_path) or ""


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    atomic_write_text(path, "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records))


def extract_visual_context(source_id: str, *, product_slug: str = "", directory: Path | None = None, provider: str = "cache_html", screenshot_path: Path | None = None, refresh: bool = False) -> dict[str, Any]:
    directory = directory or artifact_directory(source_id, product_slug)
    if directory is None:
        raise FileNotFoundError(f"Brak lokalnych artefaktów źródła: {source_id}")
    product_slug, source_type, canonical_url, html_relative = source_metadata(source_id, directory, product_slug)
    html_path = directory / ("page.html" if (directory / "page.html").exists() else "html.html")
    if not html_path.exists():
        raise FileNotFoundError(f"Brak HTML dla źródła: {source_id}")
    html = html_path.read_text(encoding="utf-8", errors="replace")
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    visual_dir = directory / "visual"
    snapshot_path = visual_dir / "visual_snapshot.json"
    existing = read_json(snapshot_path, {})
    if not refresh and isinstance(existing, dict) and existing.get("content_hash") == content_hash and (visual_dir / "visual_blocks.jsonl").exists():
        return {"status": "skipped", "snapshot": existing, "blocks": len(read_jsonl(visual_dir / "visual_blocks.jsonl")), "media": len(read_jsonl(visual_dir / "media_manifest.jsonl"))}

    parser = TreeParser()
    parser.feed(html)
    snapshot_id = stable_id("visual", source_id, content_hash)
    block_rows: list[dict[str, Any]] = []
    media_rows: list[dict[str, Any]] = []
    media_seen: set[tuple[str, str, str]] = set()
    block_seen: set[tuple[str, str, tuple[str, ...]]] = set()

    def add_block(container: Node, candidates: list[dict[str, str]], region: str | None = None) -> None:
        if (region or "") != "gallery" and is_noise(container):
            return
        heading = first_heading(container)
        body = first_body(container, heading)
        if not candidates:
            return
        actual_region = region or region_for(container, source_type)
        if actual_region == "recommendation":
            return
        asset_ids: list[str] = []
        for candidate in candidates:
            url = candidate["url"]
            key = (url, heading or "", body or "")
            media_id = stable_id("media", snapshot_id, url)
            if key not in media_seen:
                media_seen.add(key)
                asset = MediaAssetV1(
                    media_id=media_id, visual_snapshot_id=snapshot_id, source_id=source_id, product_slug=product_slug,
                    media_type=media_type(url, candidate["tag"]), original_url=url, resolved_url=url,
                    alt_text=candidate.get("alt") or None, title_text=candidate.get("title") or None,
                    role="product_gallery" if actual_region == "gallery" else "feature", exact_product_match=None,
                )
                media_rows.append(asdict(asset))
            asset_ids.append(media_id)
        unique_assets = list(dict.fromkeys(asset_ids))
        identity = (normalized(heading).casefold(), normalized(body).casefold(), tuple(unique_assets))
        if identity in block_seen:
            return
        block_seen.add(identity)
        block_id = stable_id("block", snapshot_id, node_path(container), heading or "", body or "", "|".join(unique_assets))
        for asset in media_rows:
            if asset["media_id"] in unique_assets and not asset.get("block_id"):
                asset["block_id"] = block_id
        block = VisualBlockV1(
            block_id=block_id, visual_snapshot_id=snapshot_id, source_id=source_id, product_slug=product_slug,
            region=actual_region, heading=heading, body_text=body, page_order=container.order,
            dom_path=node_path(container), section_screenshot_path=None, media_ids=unique_assets,
            classification="relevant" if heading or body else "possibly_relevant",
            classification_reason="same_dom_container",
        )
        block_rows.append(asdict(block))

    if source_type == "marketplace":
        images_payload = read_json(directory / "product_images.json", [])
        images = images_payload.get("images", []) if isinstance(images_payload, dict) else images_payload
        gallery: list[dict[str, str]] = []
        gallery_seen: set[str] = set()
        for item in images if isinstance(images, list) else []:
            if isinstance(item, dict):
                url = str(item.get("url") or item.get("src") or item.get("image_url") or "").strip()
                # Product images exist in several Allegro sizes. Keep one stable
                # original/s720 candidate instead of turning thumbnails into blocks.
                stable_key = re.sub(r"/(?:s128|s480|s720|original)/", "/", url)
                if url and "allegro" in url and stable_key not in gallery_seen and len(gallery) < 12:
                    gallery_seen.add(stable_key)
                    gallery.append({"url": url, "tag": "img", "alt": str(item.get("alt") or item.get("alt_text") or ""), "title": ""})
        if gallery:
            gallery_node = Node("section", {"id": "product-gallery"})
            gallery_node.order = 1
            gallery_node.parts = ["Galeria produktu"]
            add_block(gallery_node, gallery, "gallery")
        sections_payload = read_json(directory / "offer_sections.json", {})
        sections = sections_payload.get("sections", {}) if isinstance(sections_payload, dict) else {}
        description = str(sections.get("description") or "") if isinstance(sections, dict) else ""
        if description:
            description_node = Node("section", {"id": "offer-description"})
            description_node.order = 999999
            description_node.parts = [description]
            # Marketplace description stays textual unless an image is actually inside its DOM region.
            description_media = []
            for node in walk(parser.root):
                token = f"{node.attrs.get('id', '')} {node.class_name}".casefold()
                if "opis" in token or "description" in token:
                    description_media.extend(media_urls(node)[:8])
            if description_media:
                add_block(description_node, description_media[:8], "description")
            else:
                block = VisualBlockV1(block_id=stable_id("block", snapshot_id, "description", description), visual_snapshot_id=snapshot_id, source_id=source_id, product_slug=product_slug, region="description", heading="Opis", body_text=normalized(description)[:900], page_order=999999, dom_path="offer_sections.description", classification="relevant", classification_reason="offer_sections")
                block_rows.append(asdict(block))
    else:
        # Adapter-specific region rules still emit the same VisualBlockV1
        # contract. They deliberately avoid global navigation/gallery clones.
        nodes = list(walk(parser.root))
        if "kinderkraft" in source_id.casefold():
            containers = [
                node for node in nodes
                if node.tag == "li" and "splide__slide" in node.class_name and any(child.attrs.get("data-role") == "title" for child in walk(node))
            ]
        elif "cybex" in source_id.casefold():
            containers = [
                node for node in nodes
                if "b-highlight" in node.class_name.casefold() and "b-highlight-image" not in node.class_name.casefold()
            ]
        else:
            containers = [choose_container(node, source_type) for node in nodes if media_urls(node)]
        seen_containers: set[int] = set()
        for container in containers:
            if id(container) in seen_containers:
                continue
            seen_containers.add(id(container))
            candidates = media_urls(container)
            if candidates:
                add_block(container, candidates)

    # Stable page order and strict de-duplication make --resume idempotent.
    block_rows.sort(key=lambda item: (item.get("page_order") is None, item.get("page_order") or 0, item["block_id"]))
    unique_media = {item["media_id"]: item for item in media_rows}
    media_rows = list(unique_media.values())
    screenshot = screenshot_path if screenshot_path and screenshot_path.exists() else visual_dir / "full_page.webp"
    screenshot_relative = relative_path(screenshot) if screenshot.exists() else None
    snapshot = VisualSourceSnapshotV1(
        visual_snapshot_id=snapshot_id, source_id=source_id, product_slug=product_slug, source_type=source_type,
        canonical_url=canonical_url, capture_status="captured" if screenshot_relative else "partial",
        capture_provider=provider, full_page_screenshot_path=screenshot_relative, rendered_html_path=html_relative,
        blocks_count=len(block_rows), media_count=len(media_rows), content_hash=content_hash, captured_at=utc_now(),
    )
    visual_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(snapshot_path, asdict(snapshot))
    write_jsonl(visual_dir / "visual_blocks.jsonl", block_rows)
    write_jsonl(visual_dir / "media_manifest.jsonl", media_rows)
    return {"status": "written", "snapshot": asdict(snapshot), "blocks": len(block_rows), "media": len(media_rows)}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def source_visual_paths(source_id: str, product_slug: str = "") -> tuple[Path | None, Path | None, Path | None]:
    directory = artifact_directory(source_id, product_slug)
    if directory is None:
        return None, None, None
    visual = directory / "visual"
    return visual / "visual_snapshot.json", visual / "visual_blocks.jsonl", visual / "media_manifest.jsonl"


def artifact_id(relative: str) -> str:
    return base64.urlsafe_b64encode(relative.encode("utf-8")).decode("ascii").rstrip("=")


def artifact_relative(artifact: str) -> str | None:
    try:
        value = base64.urlsafe_b64decode(artifact + "=" * (-len(artifact) % 4)).decode("utf-8")
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            return None
        return value
    except (ValueError, UnicodeDecodeError):
        return None


def redact_json_payload(value: Any) -> Any:
    """Redact secret-shaped values without corrupting the JSON document."""
    secret = re.compile(r"(bearer\s+|sk-[A-Za-z0-9_-]{8,}|fc-[A-Za-z0-9_-]{8,})", re.I)
    if isinstance(value, dict):
        return {str(key): redact_json_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_json_payload(item) for item in value]
    if isinstance(value, str):
        return secret.sub("[REDACTED]", value)
    return value
