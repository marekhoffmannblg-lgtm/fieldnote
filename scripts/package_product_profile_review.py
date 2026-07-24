#!/usr/bin/env python3
"""Create a read-only review bundle without rewriting historical diagnostics."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from p0_runtime import atomic_write_json, atomic_write_text
from product_profile import (
    ROOT,
    diagnostic_path,
    profile_path,
    read_json,
    transmission_profile_input,
    validate_profile_against_input,
    validate_final_profile_sections_schema,
)
from product_profile_prompt import (
    PRODUCT_PROFILE_MODEL,
    PRODUCT_PROFILE_PROMPT_VERSION,
    PRODUCT_PROFILE_SCHEMA_VERSION,
)


PRE = ROOT / "output" / "product_profile_review" / "kinderkraft_nebo_preflight"
TARGET = ROOT / "output" / "product_profile_review" / "kinderkraft_nebo"
REVIEW_PACKAGE_FILES = (
    "README.md",
    "historical_profile.json",
    "canonical_input_current.json",
    "provider_response_diagnostic_original.json",
    "current_validation_results.json",
    "compatibility.json",
    "selected_evidence.json",
    "selected_visual_blocks.json",
    "selected_media_manifest.json",
)
SECRET = re.compile(r"(?i)(openai|firecrawl)[_-]?api[_-]?key\s*[:=]|bearer\s+[a-z0-9._-]+|cookie\s*[:=]")
ABSOLUTE = re.compile(r"/(Users|private|tmp)/")


def safe_read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _diagnostic_or_unavailable(product_slug: str) -> dict[str, Any]:
    diagnostic = read_json(diagnostic_path(product_slug), {})
    if isinstance(diagnostic, dict) and diagnostic:
        return diagnostic
    return {"provider_status": "unavailable", "parser_error": "diagnostic_unavailable"}


def _validation_result(profile: dict[str, Any], canonical: dict[str, Any]) -> dict[str, Any]:
    model_sections = {
        key: profile.get(key)
        for key in (
            "one_sentence_summary", "narrative_summary", "discovered_themes",
            "marketplace_narrative", "visual_positioning", "important_conflicts",
            "important_unknowns",
        )
    }
    schema_errors = validate_final_profile_sections_schema(model_sections)
    semantic_errors = validate_profile_against_input(profile, canonical)
    return {
        "profile_schema_valid": not schema_errors,
        "schema_errors": schema_errors,
        "semantic_valid": not semantic_errors,
        "semantic_errors": semantic_errors,
        "profile_status": str(profile.get("profile_status", "")),
        "provider_diagnostic_available": diagnostic_path(str(canonical.get("product_slug", ""))).exists(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-slug", default="kinderkraft__nebo")
    args = parser.parse_args()
    if args.product_slug != "kinderkraft__nebo":
        raise SystemExit("Paczka kontrolna jest ograniczona do kinderkraft__nebo.")

    input_payload = safe_read(PRE / "profile_input_payload.json")
    transmission_manifest = safe_read(PRE / "transmission_manifest.json")
    payload_hash = str(transmission_manifest.get("payload_hash", "")) if isinstance(transmission_manifest, dict) else ""
    if not payload_hash:
        raise SystemExit("Brak payload_hash w transmission_manifest.json.")
    profile = read_json(profile_path(args.product_slug), {})
    if not isinstance(profile, dict) or not profile:
        raise SystemExit("Brak wyniku profilu do spakowania.")

    canonical = transmission_profile_input(input_payload, payload_hash)
    original_diagnostic = _diagnostic_or_unavailable(args.product_slug)
    generation = profile.get("generation", {}) if isinstance(profile.get("generation"), dict) else {}
    compatibility = {
        "historical_prompt_version": str(original_diagnostic.get("prompt_version", "")),
        "current_prompt_version": PRODUCT_PROFILE_PROMPT_VERSION,
        "prompt_version_matches_current": str(original_diagnostic.get("prompt_version", "")) == PRODUCT_PROFILE_PROMPT_VERSION,
        "historical_schema_version": str(original_diagnostic.get("schema_version", "")),
        "current_schema_version": PRODUCT_PROFILE_SCHEMA_VERSION,
        "schema_version_matches_current": str(original_diagnostic.get("schema_version", "")) == PRODUCT_PROFILE_SCHEMA_VERSION,
        "historical_canonical_input_hash": str(original_diagnostic.get("canonical_input_hash", original_diagnostic.get("input_hash", ""))),
        "current_canonical_input_hash": str(canonical["canonical_input_hash"]),
        "canonical_input_hash_identical": str(original_diagnostic.get("canonical_input_hash", original_diagnostic.get("input_hash", ""))) == str(canonical["canonical_input_hash"]),
        "historical_transmission_payload_hash": str(original_diagnostic.get("transmission_payload_hash", "")),
        "current_transmission_payload_hash": payload_hash,
        "transmission_payload_hash_identical": str(original_diagnostic.get("transmission_payload_hash", "")) == payload_hash,
        "historical_model_name": str(original_diagnostic.get("model_name", "")),
        "current_model_name": PRODUCT_PROFILE_MODEL,
        "profile_is_current": str(generation.get("canonical_input_hash", "")) == str(canonical["canonical_input_hash"])
        and str(generation.get("prompt_version", "")) == PRODUCT_PROFILE_PROMPT_VERSION
        and str(generation.get("schema_version", "")) == PRODUCT_PROFILE_SCHEMA_VERSION,
        "profile_status": str(profile.get("profile_status", "")),
    }

    TARGET.mkdir(parents=True, exist_ok=True)
    atomic_write_json(TARGET / "historical_profile.json", profile, preserve_previous=False)
    atomic_write_json(TARGET / "canonical_input_current.json", canonical, preserve_previous=False)
    # The historical provider diagnostic is copied verbatim: no compatibility
    # fields or hashes are inserted into it.
    atomic_write_json(TARGET / "provider_response_diagnostic_original.json", original_diagnostic, preserve_previous=False)
    atomic_write_json(TARGET / "current_validation_results.json", _validation_result(profile, canonical), preserve_previous=False)
    atomic_write_json(TARGET / "compatibility.json", compatibility, preserve_previous=False)
    for name in ("selected_evidence.json", "selected_visual_blocks.json", "selected_media_manifest.json"):
        atomic_write_json(TARGET / name, safe_read(PRE / name), preserve_previous=False)

    readme = f"""# Kinderkraft NEBO AI Product Profile review

This package separates historical artifacts from the current runtime contract.

- `provider_response_diagnostic_original.json` is an immutable copy of the saved provider diagnostic.
- `canonical_input_current.json` is the current canonical ProductProfileInput.
- `historical_profile.json` is the saved profile; it is not regenerated by this script.
- `current_validation_results.json` uses the real schema and semantic validators.
- `compatibility.json` compares the historical request metadata with the current runtime.

Transmission payload hash: `{payload_hash}`.
"""
    atomic_write_text(TARGET / "README.md", readme, preserve_previous=False)
    for path in TARGET.iterdir():
        if path.is_file() and (SECRET.search(path.read_text(encoding="utf-8")) or ABSOLUTE.search(path.read_text(encoding="utf-8"))):
            raise SystemExit(f"Unsafe data found in review package: {path.name}")
    print(f"review_folder={TARGET}")
    print("zip_command=ditto -c -k --sequesterRsrc --keepParent output/product_profile_review/kinderkraft_nebo output/KINDERKRAFT_NEBO_AI_PROFILE_REVIEW.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
