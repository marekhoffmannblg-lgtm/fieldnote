"""Offline regression tests for strict ProductProfileV1 provider integration."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path: sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "fieldnote-api") not in sys.path: sys.path.insert(0, str(ROOT / "fieldnote-api"))

from product_profile import (  # noqa: E402
    ProviderProfileError, _base_profile, _canonical_input, _extract_structured_output,
    _hash, _profile_from_model_result, build_openai_request, build_profile_input,
    cache_valid, deterministic_factual_highlights, generate_from_transmission_payload,
    generate_or_load_profile, process_provider_output, profile_cache_key, stable_visual_block_id,
    validate_profile_against_input, validate_profile_response_schema,
)
from product_profile_prompt import PRODUCT_PROFILE_PROMPT_VERSION, product_profile_response_schema  # noqa: E402
from package_product_profile_review import REVIEW_PACKAGE_FILES  # noqa: E402
from contracts import ProductProfileV1  # noqa: E402
from pydantic import ValidationError  # noqa: E402


def input_payload() -> dict:
    return _canonical_input({
        "product_slug": "test__model", "brand": "Test", "model": "Model", "category": "Wózki dziecięce", "benchmark_category": "Lekkie spacerówki podróżne",
        "sources": [{"source_id": "manufacturer:test:1", "marketplace": "manufacturer", "content_family_id": "family:1"}],
        "facts": [{"field_name": "Waga", "value": "6 kg", "supporting_evidence_ids": ["evidence:1"]}],
        "evidence": [{"field_name": "Waga", "value": "6 kg", "evidence_id": "evidence:1", "source_id": "manufacturer:test:1", "content_family_id": "family:1", "excerpt": "Waga: 6 kg"}],
        "conflicts": [],
        "visual_blocks": [{"source_id": "manufacturer:test:1", "heading": "Składanie", "text_context": "Kompaktowe składanie.", "media_ids": [], "local_media_available": False}],
        "media": [],
    })


def empty_input_payload() -> dict:
    return _canonical_input({
        "product_slug": "empty__model", "brand": "Empty", "model": "Model",
        "category": "Wózki dziecięce", "benchmark_category": "Spacerówki lekkie",
        "sources": [], "facts": [], "evidence": [], "conflicts": [],
        "visual_blocks": [], "media": [],
    })


def valid_response(data: dict) -> dict:
    source_id = data["visual_blocks"][0].get("source_id") or data["sources"][0]["source_id"]
    evidence = data["evidence"][0]
    block_id = data["visual_blocks"][0]["visual_block_id"]
    profile = _base_profile(data, "generated")
    profile.update({
        "one_sentence_summary": "Test Model to produkt opisany przez potwierdzony parametr wagi i materiały producenta.",
        "narrative_summary": " ".join(["Profil opiera się wyłącznie na przekazanym dowodzie i kontekście źródła, bez uzupełniania braków wiedzą ogólną."] * 12),
        "discovered_themes": [{"theme_id": "theme:1", "title": "Kompaktowe składanie", "summary": "Źródło opisuje kompaktowe składanie.", "basis_types": ["text_context"], "supporting_source_ids": [source_id], "supporting_evidence_ids": [], "supporting_visual_block_ids": [block_id], "supporting_media_ids": [], "confidence": "medium"}],
        "marketplace_narrative": [], "visual_positioning": [], "important_conflicts": [], "important_unknowns": [],
    })
    return profile


def valid_provider_response(data: dict) -> dict:
    """Return only the provider-owned DTO, never a pre-built final profile."""
    final = valid_response(data)
    theme = deepcopy(final["discovered_themes"][0])
    theme.pop("supporting_source_ids", None)
    return {
        "one_sentence_summary": final["one_sentence_summary"],
        "narrative_summary": final["narrative_summary"],
        "discovered_themes": [theme],
        "marketplace_narrative": [],
        "visual_positioning": [],
        "important_conflicts": [],
        "important_unknowns": [],
    }


class ProductProfileTests(unittest.TestCase):
    def test_stable_visual_id_is_nonempty(self) -> None:
        self.assertEqual(stable_visual_block_id("source:1", 2, "Nagłówek", "Treść"), stable_visual_block_id("source:1", 2, "Nagłówek", "Treść"))
        self.assertTrue(stable_visual_block_id("source:1", 2, "Nagłówek", "Treść"))

    def test_parser_accepts_valid_structured_output(self) -> None:
        data = input_payload(); raw = valid_provider_response(data)
        parsed, diagnostic = _extract_structured_output({"id": "resp_1", "status": "completed", "output_text": json.dumps(raw)}, data)
        self.assertTrue(diagnostic["parsed_output_present"])
        self.assertNotIn("factual_highlights", parsed)

    def test_factual_highlights_are_deterministic_not_model_owned(self) -> None:
        data = input_payload()
        model_response = valid_provider_response(data)
        profile = _profile_from_model_result(data, model_response)
        self.assertEqual(profile["factual_highlights"], deterministic_factual_highlights(data))
        self.assertEqual(profile["factual_highlights"][0]["statement"], "Waga: 6 kg")

    def test_provider_sections_map_to_public_contract_with_backend_relations(self) -> None:
        """Provider DTO source IDs never become public profile provenance."""
        source_id = "allegro:18405722631"
        family_id = "hash:721a4fa827efcf9f5373443c2b307918ad5a5fcb609d371a80cf3419715fe8be"
        first_evidence_id = "evidence:b63056f4832c01b5742a6a86"
        second_evidence_id = "evidence:cebaa717ee8fad8767339a62"
        data = _canonical_input({
            "product_slug": "kinderkraft__nebo",
            "brand": "Kinderkraft",
            "model": "NEBO",
            "category": "Wózki dziecięce",
            "benchmark_category": "Spacerówki lekkie",
            "sources": [{"source_id": source_id, "marketplace": "allegro", "content_family_id": family_id}],
            "facts": [{"field_name": "Waga", "value": "7,5 kg", "supporting_evidence_ids": [first_evidence_id]}],
            "evidence": [
                {"field_name": "Waga", "value": "7,5 kg", "evidence_id": first_evidence_id, "source_id": source_id, "content_family_id": family_id, "excerpt": "Waga produktu: 7,5 kg."},
                {"field_name": "Składanie", "value": "kompaktowe", "evidence_id": second_evidence_id, "source_id": source_id, "content_family_id": family_id, "excerpt": "Kompaktowe składanie ułatwia transport."},
            ],
            "conflicts": [],
            "visual_blocks": [],
            "media": [],
        })
        theme = {
            "theme_id": "t1",
            "title": "Lekkość i mobilność",
            "summary": "Materiał opisuje niską wagę i kompaktowe składanie.",
            "basis_types": ["objective"],
            "supporting_evidence_ids": [first_evidence_id, second_evidence_id],
            "supporting_visual_block_ids": [],
            "supporting_media_ids": [],
            "confidence": "high",
        }
        marketplace = {
            "observation": "Oferta prezentuje produkt jako lekki i mobilny.",
            "supporting_evidence_ids": [first_evidence_id, second_evidence_id],
            "confidence": "high",
        }
        narrative = " ".join(["Profil opiera się wyłącznie na przekazanych dowodach źródłowych bez dopowiadania brakujących informacji."] * 13)
        provider_result = {
            "one_sentence_summary": "Kinderkraft NEBO jest opisany przez przekazane dowody dotyczące wagi i kompaktowego składania.",
            "narrative_summary": narrative,
            "discovered_themes": [deepcopy(theme)],
            "marketplace_narrative": [deepcopy(marketplace)],
            "visual_positioning": [],
            "important_conflicts": [],
            "important_unknowns": [],
        }
        self.assertEqual(validate_profile_response_schema(provider_result, data), [])
        profile = process_provider_output(data, provider_result)
        ProductProfileV1(**profile)
        self.assertEqual(validate_profile_against_input(profile, data), [])
        self.assertEqual(profile["discovered_themes"][0]["supporting_source_ids"], [source_id])
        self.assertEqual(profile["marketplace_narrative"][0]["supporting_source_ids"], [source_id])
        self.assertEqual(profile["marketplace_narrative"][0]["content_family_ids"], [family_id])
        self.assertEqual(profile["discovered_themes"][0]["supporting_visual_block_ids"], [])
        self.assertEqual(profile["discovered_themes"][0]["supporting_media_ids"], [])

    def test_provider_dynamic_schema_rejects_unknown_evidence_before_mapping(self) -> None:
        data = input_payload()
        raw = valid_provider_response(data)
        raw["discovered_themes"][0]["supporting_evidence_ids"] = ["evidence:d7a634ea963b69f5900bc7de"]
        self.assertTrue(validate_profile_response_schema(raw, data))
        with self.assertRaises(ProviderProfileError) as caught:
            process_provider_output(data, raw)
        self.assertEqual(caught.exception.code, "schema_validation_error")
        self.assertIn("schema_validation_error:discovered_themes", caught.exception.diagnostic["schema_error"])

    def test_empty_and_invalid_provider_results_are_rejected(self) -> None:
        data = input_payload()
        with self.assertRaises(ProviderProfileError) as caught:
            process_provider_output(data, {})
        self.assertEqual(caught.exception.code, "schema_validation_error")
        for payload, code in (({"output_text": ""}, "provider_empty_response"), ({"status": "incomplete", "output_text": ""}, "provider_incomplete_response"), ({"output_text": "not-json"}, "structured_output_parse_error"), ({"output": [{"content": [{"type": "refusal", "refusal": "no"}]}]}, "provider_refusal")):
            with self.assertRaises(ProviderProfileError) as caught: _extract_structured_output(payload, data)
            self.assertEqual(caught.exception.code, code)

    def test_semantic_validation_blocks_empty_and_unsupported_ids(self) -> None:
        data = input_payload(); profile = valid_response(data)
        profile["one_sentence_summary"] = ""
        errors = validate_profile_against_input(profile, data)
        self.assertIn("semantic_validation_error:one_sentence_empty", errors)
        profile = valid_response(data); profile["discovered_themes"][0]["supporting_source_ids"] = ["unknown"]
        self.assertIn("semantic_validation_error:theme_source_id", validate_profile_against_input(profile, data))

    def test_empty_profile_input_skips_provider_in_both_generation_paths(self) -> None:
        payload = empty_input_payload()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "payload.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            calls: list[str] = []

            def provider(_data: dict):
                calls.append("called")
                return valid_provider_response(input_payload()), {}

            profile, cached, errors = generate_from_transmission_payload(
                source,
                expected_hash=_hash(payload),
                allow_openai=True,
                profile_root=root,
                provider_call=provider,
            )
            self.assertFalse(cached)
            self.assertEqual(errors, [])
            self.assertEqual(calls, [])
            self.assertEqual(profile["profile_status"], "not_generated")
            self.assertEqual(profile["generation"]["failure_code"], "insufficient_profile_evidence")
            self.assertEqual(profile["generation"]["openai_requests_attempted_this_run"], 0)
            self.assertFalse(profile["generation"]["profile_quality_valid"])

            with patch("product_profile.build_profile_input", return_value=payload), patch("product_profile._openai_profile") as openai_call:
                local_profile, local_cached = generate_or_load_profile(
                    "empty__model", allow_openai=True, profile_root=root,
                )
            openai_call.assert_not_called()
            self.assertFalse(local_cached)
            self.assertEqual(local_profile["profile_status"], "not_generated")
            self.assertEqual(local_profile["generation"]["openai_requests_attempted_this_run"], 0)

    def test_negative_inference_allows_missing_information_but_rejects_product_negation(self) -> None:
        data = input_payload()
        profile = valid_response(data)
        profile["one_sentence_summary"] = "Koła przednie mają kompaktową konstrukcję opisaną w źródle."
        profile["narrative_summary"] = " ".join(["Nie posiadamy informacji wykraczających poza przekazane źródło."] * 20)
        profile["important_unknowns"] = [{
            "summary": "Brak danych o dodatkowym parametrze.",
            "reason": "Brak informacji w materiale źródłowym.",
            "related_source_ids": [data["sources"][0]["source_id"]],
        }]
        self.assertNotIn("semantic_validation_error:negative_missing_inference", validate_profile_against_input(profile, data))

        profile = valid_response(data)
        profile["one_sentence_summary"] = "Produkt nie ma hamulca."
        self.assertIn("semantic_validation_error:negative_missing_inference", validate_profile_against_input(profile, data))

    def test_narrative_schema_and_semantic_word_limits_remain_strict(self) -> None:
        schema = product_profile_response_schema(input_payload())
        narrative = schema["properties"]["narrative_summary"]
        self.assertEqual(narrative["minLength"], 1050)
        self.assertEqual(narrative["maxLength"], 1500)

        data = input_payload()
        raw = valid_provider_response(data)
        raw["narrative_summary"] = " ".join(["dziesieciowy"] * 110)
        self.assertEqual(validate_profile_response_schema(raw, data), [])
        profile = _profile_from_model_result(data, raw)
        self.assertIn("semantic_validation_error:narrative_length", validate_profile_against_input(profile, data))

    def test_each_supporting_id_type_and_related_sections_is_validated(self) -> None:
        data = input_payload()
        profile = valid_response(data)
        theme = profile["discovered_themes"][0]
        theme["supporting_evidence_ids"] = ["evidence:missing"]
        theme["supporting_visual_block_ids"] = ["visual:missing"]
        theme["supporting_media_ids"] = ["media:missing"]
        profile["marketplace_narrative"] = [{"observation": "Opis oferty.", "supporting_source_ids": [data["sources"][0]["source_id"]], "content_family_ids": ["family:missing"], "confidence": "low"}]
        profile["important_conflicts"] = [{"summary": "Rozbieżność.", "field_names": ["Waga"], "supporting_evidence_ids": ["evidence:missing"], "supporting_source_ids": ["source:missing"]}]
        profile["important_unknowns"] = [{"summary": "Brak danych.", "reason": "Nie podano.", "related_source_ids": ["source:missing"]}]
        errors = validate_profile_against_input(profile, data)
        for code in (
            "semantic_validation_error:theme_evidence_id",
            "semantic_validation_error:theme_visual_block_id",
            "semantic_validation_error:theme_media_id",
            "semantic_validation_error:marketplace_content_family_id",
            "semantic_validation_error:conflict_evidence_id",
            "semantic_validation_error:conflict_source_id",
            "semantic_validation_error:unknown_source_id",
        ):
            self.assertIn(code, errors)

    def test_semantic_validation_rejects_empty_analytic_sections(self) -> None:
        data = input_payload(); profile = valid_response(data)
        for key in ("discovered_themes", "marketplace_narrative", "visual_positioning"):
            profile[key] = []
        self.assertIn("semantic_validation_error:empty_profile", validate_profile_against_input(profile, data))

    def test_cache_key_uses_prompt_and_schema_and_avoids_second_call(self) -> None:
        payload = input_payload(); expected = _hash(payload)
        with tempfile.TemporaryDirectory(dir=ROOT / "input") as raw:
            root = Path(raw); input_file = root / "payload.json"; input_file.write_text(json.dumps(payload), encoding="utf-8")
            calls = []
            def mock(data: dict):
                calls.append(data["cache_key"]); return valid_provider_response(data), {"request_id": "mock", "model_name": "mock", "prompt_version": PRODUCT_PROFILE_PROMPT_VERSION, "schema_version": "1"}
            first, cached, errors = generate_from_transmission_payload(input_file, expected_hash=expected, allow_openai=True, profile_root=root, provider_call=mock)
            second, cached_second, _ = generate_from_transmission_payload(input_file, expected_hash=expected, allow_openai=True, profile_root=root, provider_call=mock)
            self.assertFalse(cached); self.assertFalse(errors); self.assertTrue(cached_second); self.assertEqual(len(calls), 1); self.assertTrue(cache_valid(first, _canonical_input(payload)))
            self.assertEqual(second["generation"]["prompt_version"], PRODUCT_PROFILE_PROMPT_VERSION)
            self.assertEqual(second["generation"]["openai_requests_attempted_this_run"], 0)
            self.assertNotEqual(calls[0], profile_cache_key(payload["canonical_input_hash"], prompt_version="next"))

    def test_media_count_means_sent_local_media_only(self) -> None:
        payload = input_payload(); payload["visual_blocks"][0]["media_ids"] = ["remote"]
        canonical = _canonical_input(payload)
        self.assertEqual(canonical["input_summary"]["media_items_used"], 0)

    def test_multimodal_request_attaches_only_approved_local_image(self) -> None:
        payload = input_payload()
        payload["visual_blocks"][0]["media_ids"] = ["media:1"]
        payload["media"] = [{"media_id": "media:1", "source_id": "manufacturer:test:1", "mime_type": "image/png", "byte_size": 4}]
        data = _canonical_input(payload)
        with tempfile.TemporaryDirectory(dir=ROOT / "input") as raw:
            image = Path(raw) / "product.png"; image.write_bytes(b"\x89PNG\r\n\x1a\nminimal")
            body, effective, sent = build_openai_request(data, media_files=[(data["media"][0], image)])
        user_content = body["input"][1]["content"]
        self.assertEqual(sent, ["media:1"])
        self.assertEqual(sum(item["type"] == "input_image" for item in user_content), 1)
        self.assertEqual(effective["input_summary"]["media_items_used"], 1)
        self.assertIn("media_id=media:1", user_content[1]["text"])
        self.assertIn("data:image/png;base64,", user_content[2]["image_url"])
        schema = body["text"]["format"]["schema"]
        theme_properties = schema["properties"]["discovered_themes"]["items"]["properties"]
        self.assertEqual(theme_properties["supporting_evidence_ids"]["items"]["enum"], ["evidence:1"])
        self.assertEqual(theme_properties["supporting_media_ids"]["items"]["enum"], ["media:1"])

    def test_ai_failure_does_not_touch_product_data(self) -> None:
        payload = input_payload(); expected = _hash(payload)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); file = root / "payload.json"; file.write_text(json.dumps(payload), encoding="utf-8")
            def refusal(_data: dict): raise ProviderProfileError("provider_refusal", "refused")
            profile, _, errors = generate_from_transmission_payload(file, expected_hash=expected, allow_openai=True, profile_root=root, provider_call=refusal)
            self.assertEqual(profile["profile_status"], "failed"); self.assertEqual(errors, ["provider_refusal"])
            diagnostic = json.loads((root / "test__model.provider_response_diagnostic.json").read_text(encoding="utf-8"))
            self.assertEqual(diagnostic["parser_error"], "provider_refusal")
            self.assertNotIn("Authorization", json.dumps(diagnostic))

    def test_semantic_rejection_preserves_accepted_output_and_saves_rejected_output(self) -> None:
        payload = input_payload(); expected = _hash(payload)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root / "payload.json"; source.write_text(json.dumps(payload), encoding="utf-8")
            accepted = {"marker": "accepted"}
            (root / "test__model.provider_structured_output.json").write_text(json.dumps(accepted), encoding="utf-8")
            def invalid(data: dict):
                raw = valid_provider_response(data)
                raw["narrative_summary"] = " ".join(["dziesieciowy"] * 110)
                return raw, {"request_id": "semantic-mock"}
            failed, _, errors = generate_from_transmission_payload(source, expected_hash=expected, allow_openai=True, profile_root=root, provider_call=invalid)
            self.assertEqual(failed["profile_status"], "failed")
            self.assertEqual(errors, ["semantic_validation_error"])
            self.assertEqual(json.loads((root / "test__model.provider_structured_output.json").read_text(encoding="utf-8")), accepted)
            self.assertTrue((root / "test__model.provider_structured_output_rejected.json").exists())
            diagnostic = json.loads((root / "test__model.provider_response_diagnostic.json").read_text(encoding="utf-8"))
            self.assertTrue(diagnostic["rejected_output_saved"])
            self.assertIn("semantic_validation_error:narrative_length", diagnostic["semantic_validation_errors"])

    def test_failed_generation_preserves_last_good_profile(self) -> None:
        payload = input_payload()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); file = root / "payload.json"
            file.write_text(json.dumps(payload), encoding="utf-8")
            def success(data: dict): return valid_provider_response(data), {"request_id": "ok"}
            good, _, errors = generate_from_transmission_payload(file, expected_hash=_hash(payload), allow_openai=True, profile_root=root, provider_call=success)
            self.assertFalse(errors)
            changed = deepcopy(payload); changed["facts"][0]["value"] = "7 kg"
            file.write_text(json.dumps(changed), encoding="utf-8")
            def failed(_data: dict): raise ProviderProfileError("provider_refusal", "refused")
            failed_result, _, errors = generate_from_transmission_payload(file, expected_hash=_hash(changed), allow_openai=True, profile_root=root, provider_call=failed)
            saved = json.loads((root / "test__model.json").read_text(encoding="utf-8"))
            self.assertEqual(errors, ["provider_refusal"])
            self.assertEqual(failed_result["profile_status"], "failed")
            self.assertEqual(saved["generation"]["canonical_input_hash"], good["generation"]["canonical_input_hash"])

    def test_parallel_generation_uses_one_provider_call(self) -> None:
        payload = input_payload(); expected = _hash(payload)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); file = root / "payload.json"; file.write_text(json.dumps(payload), encoding="utf-8")
            calls: list[str] = []; outcomes: list[object] = []
            def slow_success(data: dict):
                calls.append("call"); time.sleep(0.15)
                return valid_provider_response(data), {"request_id": "ok"}
            def invoke() -> None:
                try:
                    outcomes.append(generate_from_transmission_payload(file, expected_hash=expected, allow_openai=True, profile_root=root, provider_call=slow_success))
                except Exception as exc:  # the second attempt is deliberately rejected by the product lock
                    outcomes.append(exc)
            threads = [threading.Thread(target=invoke), threading.Thread(target=invoke)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(outcomes), 2)

    def test_wrong_product_type_is_rejected(self) -> None:
        data = input_payload(); profile = valid_response(data)
        profile["one_sentence_summary"] = "Stolik dziecięcy Test Model ma lekką konstrukcję."
        self.assertIn("semantic_validation_error:product_identity_mismatch", validate_profile_against_input(profile, data))

    def test_factual_interpretation_and_text_only_visual_claim_are_rejected(self) -> None:
        data = input_payload(); profile = valid_response(data)
        profile["factual_highlights"][0]["statement"] = "Aluminium zapewnia wytrzymałość."
        self.assertIn("unsupported_factual_interpretation", validate_profile_against_input(profile, data))
        profile = valid_response(data)
        profile["visual_positioning"] = [{"observation": "Na zdjęciu widać produkt.", "basis": "text_context_only", "visual_access": "text_context_only", "supporting_visual_block_ids": [data["visual_blocks"][0]["visual_block_id"]], "supporting_media_ids": [], "supporting_source_ids": ["manufacturer:test:1"], "confidence": "low", "is_factual_product_claim": False}]
        self.assertIn("semantic_validation_error:visual_seen_claim", validate_profile_against_input(profile, data))
        profile["visual_positioning"][0]["observation"] = "Opis kontekstu tekstowego."
        profile["visual_positioning"][0]["visual_access"] = "image_seen"
        self.assertIn("semantic_validation_error:visual_without_media", validate_profile_against_input(profile, data))

    def test_api_contract_rejects_invalid_nested_profile(self) -> None:
        data = input_payload(); profile = valid_response(data)
        profile["discovered_themes"][0].pop("confidence")
        with self.assertRaises(ValidationError):
            ProductProfileV1(**profile)

    def test_pipeline_has_optional_profile_stage(self) -> None:
        pipeline = (ROOT / "scripts" / "run_model_research_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("product profile generation", pipeline)
        self.assertIn("PRODUCT_PROFILE_AI_ENABLED", pipeline)

    def test_ui_statuses_do_not_present_failed_or_stale_as_ready(self) -> None:
        ui = (ROOT / "fieldnote-frontend" / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn('not_generated: "Nie wygenerowano"', ui)
        self.assertIn('failed: "Błąd"', ui)
        self.assertIn('stale: "Nieaktualny"', ui)
        self.assertIn('profile.profile_status === "failed"', ui)
        self.assertIn('profile.profile_status === "stale"', ui)
        self.assertIn("Wygeneruj profil", ui)

    def test_single_request_runner_guard_is_not_decorative(self) -> None:
        runner = (ROOT / "scripts" / "run_nebo_ai_profile_local.sh").read_text(encoding="utf-8")
        runtime = (ROOT / "scripts" / "product_profile.py").read_text(encoding="utf-8")
        self.assertIn("PRODUCT_PROFILE_MAX_REQUESTS=1", runner)
        self.assertNotIn("--use-cache", runner)
        self.assertIn("max_requests < 1", runtime)

    def test_nebo_bad_profile_is_rejected_and_canonical_input_has_two_families(self) -> None:
        data = build_profile_input("kinderkraft__nebo")
        self.assertEqual(data["input_summary"]["independent_content_families"], 2)
        bad = json.loads((ROOT / "output" / "product_profiles" / "kinderkraft__nebo.json").read_text(encoding="utf-8"))
        bad["one_sentence_summary"] = ""
        self.assertTrue(validate_profile_against_input(bad, data))
        good = valid_response(data)
        self.assertEqual(validate_profile_against_input(good, data), [])

    def test_review_package_contract_includes_provider_diagnostic(self) -> None:
        self.assertIn("provider_response_diagnostic_original.json", REVIEW_PACKAGE_FILES)
        self.assertIn("canonical_input_current.json", REVIEW_PACKAGE_FILES)
        review_code = (ROOT / "scripts" / "package_product_profile_review.py").read_text(encoding="utf-8")
        self.assertIn("copied verbatim", review_code)
        self.assertNotIn('diagnostic["canonical_input_hash"] =', review_code)


if __name__ == "__main__": unittest.main()
