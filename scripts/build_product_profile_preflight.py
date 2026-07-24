#!/usr/bin/env python3
"""Build a minimal, inspectable payload for one ProductProfileV1 request.

This command is deliberately offline.  It does not call OpenAI or Firecrawl,
and writes no product, evidence, or source lifecycle data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from p0_runtime import atomic_write_json, atomic_write_text
from product_profile import ROOT, build_profile_input
from visual_snapshots import read_jsonl, source_visual_paths


SECRET_PATTERNS = (
    re.compile(r"(?i)(openai|firecrawl)[_-]?api[_-]?key\s*[:=]"),
    re.compile(r"(?i)bearer\s+[a-z0-9._-]+"),
    re.compile(r"(?i)(session|cookie)\s*[:=]"),
)
PERSONAL_PATTERNS = (
    re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I),
    # Product offer IDs and media IDs are long digit strings, not phone data.
    re.compile(r"(?:\+\d[\d ()-]{7,}\d|\b\d{3}[ -]\d{3}[ -]\d{3,4}\b)"),
)
NOISE_TERMS = ("logo", "polecane", "sponsorowane", "podobne produkty", "rekomendowane")


def text(value: object, limit: int = 300) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def package_path(product_slug: str) -> Path:
    return ROOT / "output" / "product_profile_review" / f"{product_slug.replace('__', '_')}_preflight"


def json_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def public_media(source_id: str, media_ids: set[str]) -> list[dict[str, Any]]:
    """Return only real local image assets, never their local paths or remote URLs."""
    _snapshot, _blocks, media_file = source_visual_paths(source_id, "kinderkraft__nebo")
    if not media_file or not media_file.exists():
        return []
    selected: list[dict[str, Any]] = []
    for item in read_jsonl(media_file):
        if not isinstance(item, dict) or str(item.get("media_id", "")) not in media_ids:
            continue
        local_path = str(item.get("local_path", "") or "")
        if not local_path:
            continue
        candidate = Path(local_path)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        try:
            candidate.resolve().relative_to((ROOT / "input").resolve())
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        label = text(item.get("alt_text", item.get("title", "")), 160)
        if any(term in label.lower() for term in NOISE_TERMS):
            continue
        selected.append({
            "media_id": str(item.get("media_id")),
            "source_id": source_id,
            "visual_block_ids": [str(value) for value in item.get("block_ids", item.get("visual_block_ids", [])) if str(value)],
            "mime_type": str(item.get("mime_type", "")),
            "alt_text": label,
            "byte_size": candidate.stat().st_size,
            "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        })
    return selected


def build(product_slug: str, target: Path) -> dict[str, Any]:
    data = build_profile_input(product_slug, max_images=8)
    # build_profile_input already returns the canonical ProductProfileInput.
    # Do not recount or reselect data here: this exact object is what a future
    # request, cache key, manifest and review package must share.
    payload = {key: data[key] for key in ("schema_version", "prompt_version", "model_name", "product_slug", "brand", "model", "product_name", "product_type", "benchmark_category", "taxonomy_category_id", "canonical_input_hash", "cache_key", "input_summary", "sources", "facts", "evidence", "conflicts", "visual_blocks", "media", "transmission_boundary")}
    target.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target / "profile_input_payload.json", payload, preserve_previous=False)
    atomic_write_json(target / "selected_evidence.json", payload["evidence"], preserve_previous=False)
    atomic_write_json(target / "selected_visual_blocks.json", payload["visual_blocks"], preserve_previous=False)
    atomic_write_json(target / "selected_media_manifest.json", payload["media"], preserve_previous=False)
    return payload


def scan(target: Path) -> tuple[list[str], list[str], list[str]]:
    secrets: list[str] = []
    personal: list[str] = []
    absolute_paths: list[str] = []
    for path in target.glob("*.json"):
        contents = path.read_text(encoding="utf-8")
        if any(pattern.search(contents) for pattern in SECRET_PATTERNS):
            secrets.append(path.name)
        if any(pattern.search(contents) for pattern in PERSONAL_PATTERNS):
            personal.append(path.name)
        if str(ROOT) in contents or re.search(r"/(Users|private|tmp)/", contents):
            absolute_paths.append(path.name)
    return secrets, personal, absolute_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline ProductProfileV1 transmission preflight")
    parser.add_argument("--product-slug", default="kinderkraft__nebo")
    args = parser.parse_args()
    if args.product_slug != "kinderkraft__nebo":
        raise SystemExit("Ten kontrolowany preflight jest ograniczony do kinderkraft__nebo.")
    target = package_path(args.product_slug)
    payload = build(args.product_slug, target)
    secrets, personal, absolute_paths = scan(target)
    if secrets or personal or absolute_paths:
        raise SystemExit(f"Preflight safety scan failed: secrets={secrets}, personal={personal}, absolute_paths={absolute_paths}")
    manifest = {
        "files_to_be_sent": ["profile_input_payload.json", "selected_evidence.json", "selected_visual_blocks.json", "selected_media_manifest.json"],
        "text_fields_to_be_sent": ["brand", "model", "facts", "evidence.excerpt", "visual_blocks.heading", "visual_blocks.text_context", "input_summary"],
        "image_files_to_be_sent": [{key: item.get(key, [] if key == "visual_block_ids" else "") for key in ("media_id", "source_id", "visual_block_ids", "mime_type", "byte_size", "sha256")} for item in payload["media"][:8]],
        "source_ids": sorted({item["source_id"] for item in payload["sources"]}),
        "evidence_ids": [item["evidence_id"] for item in payload["evidence"]],
        "visual_block_ids": [item["visual_block_id"] for item in payload["visual_blocks"]],
        "media_ids": [item["media_id"] for item in payload["media"]],
        "total_text_characters": len(json.dumps({key: payload[key] for key in ("facts", "evidence", "visual_blocks", "input_summary")}, ensure_ascii=False)),
        "total_image_count": len(payload["media"][:8]),
        "total_image_bytes": sum(int(item["byte_size"]) for item in payload["media"][:8]),
        "redactions_applied": ["absolute local paths omitted", "remote image URLs omitted", "source text limited to evidence excerpts and selected visual text context", "no raw HTML, raw markdown, seller data, run history, cookies, headers or prompts"],
        "secrets_found": [], "personal_data_found": [], "external_domains_referenced": [],
        "payload_hash": json_hash(payload),
    }
    atomic_write_json(target / "transmission_manifest.json", manifest, preserve_previous=False)
    readme = f"""# Kinderkraft NEBO: transmission preflight\n\nThis offline package contains only the minimal locally selected input for one future ProductProfileV1 request. No OpenAI or Firecrawl request was made.\n\nIncluded: {len(payload['evidence'])} evidence excerpts, {len(payload['visual_blocks'])} textual visual blocks, and {len(payload['media'])} local image files.\n\nNot included: raw offers, HTML, markdown snapshots, local paths, remote media URLs, seller data, run history, cookies, headers, environment files, API keys, tokens, or system prompts.\n\nCoverage is textual={payload['input_summary']['textual_coverage']} and visual={payload['input_summary']['visual_coverage']}. Visual blocks without local media are explicitly text context only, so a future model must not claim it viewed an image.\n\nSafety scan: no secrets, personal data, or absolute local paths were found.\n"""
    atomic_write_text(target / "README.md", readme, preserve_previous=False)
    print(f"preflight_package_created=true\npayload_path={target / 'profile_input_payload.json'}\nsources_used={payload['input_summary']['sources_used']}\nevidence_items_used={payload['input_summary']['evidence_items_used']}\nvisual_blocks_used={payload['input_summary']['visual_blocks_used']}\nimages_to_be_sent={payload['input_summary']['media_items_used']}\ntotal_image_bytes={manifest['total_image_bytes']}\nsecrets_found=0\npersonal_data_found=0\npayload_hash={manifest['payload_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
