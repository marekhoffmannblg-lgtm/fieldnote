#!/usr/bin/env python3
"""Offline runtime checks for FIELDNOTE Product Profile.

Each check uses temporary data and a mock provider. It never enables network
providers and writes diagnostic logs only through the shell wrapper.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "fieldnote-api")]

import product_profile  # noqa: E402
from p0_runtime import FileLock, LockUnavailableError  # noqa: E402


def _payload() -> dict:
    return product_profile._canonical_input({
        "product_slug": "test__model", "brand": "Test", "model": "Model",
        "category": "Wózki dziecięce", "benchmark_category": "Lekkie spacerówki podróżne",
        "sources": [{"source_id": "manufacturer:test:1", "marketplace": "manufacturer", "content_family_id": "family:1"}],
        "facts": [{"field_name": "Waga", "value": "6 kg", "supporting_evidence_ids": ["evidence:1"], "field_status": "valid", "claim_kind": "objective"}],
        "evidence": [{"field_name": "Waga", "value": "6 kg", "evidence_id": "evidence:1", "source_id": "manufacturer:test:1", "content_family_id": "family:1", "excerpt": "Waga: 6 kg"}],
        "visual_blocks": [{"source_id": "manufacturer:test:1", "heading": "Składanie", "text_context": "Kompaktowe składanie.", "media_ids": []}],
        "media": [], "conflicts": [],
    })


def _provider(data: dict) -> tuple[dict, dict]:
    block = data["visual_blocks"][0]
    result = {
        "one_sentence_summary": "Test Model ma potwierdzoną wagę w źródle producenta.",
        "narrative_summary": " ".join(["Opis opiera się wyłącznie na zapisanym źródle i przekazanym dowodzie."] * 18),
        "discovered_themes": [{"theme_id": "theme:1", "title": "Składanie", "summary": "Źródło opisuje kompaktowe składanie.", "basis_types": ["text_context"], "supporting_source_ids": [block["source_id"]], "supporting_evidence_ids": [], "supporting_visual_block_ids": [block["visual_block_id"]], "supporting_media_ids": [], "confidence": "medium"}],
        "marketplace_narrative": [], "visual_positioning": [], "important_conflicts": [], "important_unknowns": [],
    }
    return product_profile._profile_from_model_result(data, result), {"request_id": "mock"}


def check_imports() -> None:
    import app  # noqa: F401
    import build_product_profile_preflight  # noqa: F401
    import contracts  # noqa: F401
    for name in ("build_profile_input", "generate_or_load_profile", "validate_profile_against_input"):
        assert hasattr(product_profile, name), name


def check_locks() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "profiles"; lock_dir = root.parent / "run_locks"; lock_dir.mkdir(parents=True)
        owner = FileLock(lock_dir / "product-test__model.lock", {"run_id": "run-owner", "product_slug": "test__model", "scope": "product"})
        owner.acquire()
        try:
            assert product_profile._owned_run_lock("test__model", "run-owner", root)
            assert not product_profile._owned_run_lock("test__model", "run-other", root)
            try:
                product_profile._generation_lock("test__model", root).acquire()
            except LockUnavailableError:
                pass
            else:
                raise AssertionError("foreign profile lock was not rejected")
        finally:
            owner.release()


def check_pipeline() -> None:
    pipeline = ROOT / "scripts" / "run_model_research_pipeline.py"
    completed = subprocess.run([sys.executable, str(pipeline), "--help"], cwd=ROOT, capture_output=True, text=True, check=True)
    assert "--skip-product-profile" in completed.stdout
    import app
    assert callable(app.commit_cached_manufacturer_source)
    assert callable(app.generate_profile_for_owned_run)


def check_images() -> None:
    data = _payload()
    with tempfile.TemporaryDirectory(dir=ROOT / "input") as raw:
        image = Path(raw) / "image.png"; image.write_bytes(b"\x89PNG\r\n\x1a\nminimal")
        item = {"media_id": "media:1", "source_id": "manufacturer:test:1", "mime_type": "image/png", "byte_size": image.stat().st_size, "sha256": __import__("hashlib").sha256(image.read_bytes()).hexdigest()}
        data["media"] = [item]; data["visual_blocks"][0]["media_ids"] = ["media:1"]
        body, effective, sent = product_profile.build_openai_request(data, media_files=[(item, image)])
        assert sent == ["media:1"] and effective["input_summary"]["media_items_used"] == 1
        assert any(part.get("type") == "input_image" for part in body["input"][1]["content"])
        image.write_bytes(b"\x89PNG\r\n\x1a\nchanged")
        try:
            product_profile.build_openai_request(data, media_files=[(item, image)])
        except product_profile.ProviderProfileError as exc:
            assert exc.code == "approved_media_changed"
        else:
            raise AssertionError("changed approved image was accepted")


def check_relations() -> None:
    data = _payload(); profile, _ = _provider(data)
    profile["discovered_themes"][0]["supporting_evidence_ids"] = ["unknown"]
    assert "semantic_validation_error:theme_evidence_id" in product_profile.validate_profile_against_input(profile, data)


def check_api() -> None:
    from fastapi.testclient import TestClient
    import app
    with TestClient(app.app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert set(response.json()) == {"openai_configured", "firecrawl_configured"}


def check_factual() -> None:
    data = _payload()
    assert product_profile.deterministic_factual_highlights(data)[0]["statement"] == "Waga: 6 kg"
    data["facts"][0]["field_status"] = "conflicting"
    assert not product_profile.deterministic_factual_highlights(data)


CHECKS = {"imports": check_imports, "pipeline": check_pipeline, "locks": check_locks, "images": check_images, "relations": check_relations, "api": check_api, "factual": check_factual}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=[*CHECKS, "full"])
    args = parser.parse_args()
    names = list(CHECKS) if args.command == "full" else [args.command]
    failures = []
    for name in names:
        try:
            CHECKS[name](); print(f"{name}=PASS")
        except Exception as exc:
            failures.append(name); print(f"{name}=FAIL: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
