from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FirecrawlDocument:
    source_file: str
    page_url: str
    markdown: str
    raw: dict[str, Any]


def _get_page_url(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata")
    metadata_url = metadata.get("url") if isinstance(metadata, dict) else ""

    for candidate in (
        payload.get("url"),
        payload.get("sourceURL"),
        payload.get("page_url"),
        metadata_url,
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _iter_payload_objects(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def load_firecrawl_documents(input_dir: Path) -> list[FirecrawlDocument]:
    if not input_dir.exists():
        return []

    documents: list[FirecrawlDocument] = []
    for json_path in sorted(input_dir.glob("*.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        for item in _iter_payload_objects(payload):
            markdown = item.get("markdown")
            if not isinstance(markdown, str) or not markdown.strip():
                continue

            documents.append(
                FirecrawlDocument(
                    source_file=json_path.name,
                    page_url=_get_page_url(item),
                    markdown=markdown,
                    raw=item,
                )
            )

    return documents
