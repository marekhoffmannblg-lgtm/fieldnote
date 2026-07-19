#!/usr/bin/env python3
"""Local regression checks for FIELDNOTE's product-source catalogue.

This test uses only persisted pipeline artifacts. It never calls Firecrawl,
OpenAI or the network.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
API_PATH = ROOT / "fieldnote-api" / "app.py"


def load_api():
    spec = importlib.util.spec_from_file_location("fieldnote_product_sources_api", API_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Nie udało się załadować FIELDNOTE API.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    api = load_api()

    # Produkt z aktywnymi aukcjami oraz evidence przypisanym do source_id.
    tik = api.product_sources("kinderkraft__tik")
    assert tik["total"] > 0, "active_sources_missing"
    assert any(item["source_status"] == "active" for item in tik["sources"]), "active_auction_missing"
    assert any(item["fields_count"] > 0 for item in tik["sources"]), "evidence_source_missing"

    # Źródło bez evidence nadal pozostaje widoczne jako uzupełniające.
    assert any(item["fields_count"] == 0 for item in tik["sources"]), "source_without_evidence_missing"

    # Pełne rozliczenie dziesięciu ofert wybranych dla CYBEX ORFEO. Dane są
    # odczytywane z istniejącej kolejki i lokalnego listingu, bez Firecrawl.
    orfeo = api.product_sources("cybex__orfeo")
    expected = {
        "selected_count": 10,
        "fetched_count": 8,
        "failed_count": 2,
        "attached_count": 5,
        "unattached_count": 3,
    }
    for key, value in expected.items():
        assert orfeo[key] == value, f"orfeo_{key}={orfeo[key]}"
    selected = [item for item in orfeo["sources"] if item["selected"]]
    accountable_roles = {"primary", "supplementary", "fetched_but_unattached", "failed", "duplicate", "rejected"}
    assert len(selected) == orfeo["accounted_selected_count"] == 10, "selected_offers_not_accounted"
    assert all(item["role"] in accountable_roles for item in selected), "invalid_selected_role"
    assert sum(item["fetched"] for item in selected) == 8, "fetched_cards_count_mismatch"
    assert sum(item["role"] == "failed" for item in selected) == 2, "failed_cards_count_mismatch"
    assert orfeo["prices_recovered"] > 0 and all(item["price"] for item in selected), "prices_not_recovered"
    assert all(item["seller"]["name"].lower() != "gwarancji" for item in orfeo["sources"]), "invalid_seller_visible"

    # Gotowość analizy korzysta wyłącznie z istniejących snapshotów; nie
    # uruchamia wyszukiwania ani pobierania w tym teście.
    status = api.product_analysis_status("cybex__orfeo")
    assert status["can_analyze_saved_data"] is True, "saved_analysis_not_available"
    assert status["uses_network_by_default"] is False, "saved_analysis_uses_network"
    pending_status = api.product_analysis_status("kinderkraft__apino")
    assert pending_status["status"] in {"refresh_recommended", "analysis_failed", "analysis_running", "ready"}, "lifecycle_product_status_missing"

    # Final artifacts take priority over a later failed refresh. NEBO and TRIG 3
    # remain openable benchmarks despite historical maintenance failures.
    assert api.product_analysis_status("kinderkraft__nebo")["status"] == "ready", "nebo_final_result_overridden"
    assert api.product_analysis_status("kinderkraft__trig-3")["status"] == "ready", "trig_final_result_overridden"
    audit_path = ROOT / "output" / "migrations" / "existing_products_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert len(audit.get("products", [])) == 14, "migration_audit_incomplete"
    for record in audit["products"]:
        assert record.get("reason"), "migration_reason_missing"
        if record.get("final_product_exists") and record.get("benchmark_exists") and record.get("coverage_exists"):
            assert record.get("final_status") == "ready", "valid_final_result_not_ready"

    # Powtarzające się potwierdzenie nie jest drugim nowym polem. Pierwszy
    # dowód wprowadza wartość, następny wyłącznie ją potwierdza.
    repeated = api.source_contribution_index({
        "fields": {
            "Składanie jedną ręką": {
                "value": "tak",
                "evidence": [
                    {"source_id": "allegro:first", "value": "tak", "evidence": "Składanie jedną ręką: tak"},
                    {"source_id": "allegro:second", "value": "tak", "evidence": "Możliwe składanie jedną ręką"},
                ],
            }
        }
    })
    assert len(repeated["allegro:first"]["unique_fields_contributed"]) == 1, "first_source_not_unique"
    assert len(repeated["allegro:second"]["confirmed_fields"]) == 1, "repeat_not_confirmation"
    assert not repeated["allegro:second"]["unique_fields_contributed"], "repeat_counted_as_new"

    # Źródło bez evidence ma nadal jawny, zerowy wkład zamiast pustego/awaryjnego widoku.
    zero_contribution = next(item for item in orfeo["sources"] if item["role"] == "fetched_but_unattached")
    assert not zero_contribution["contribution"]["final_fields_used"], "zero_contribution_has_final_fields"
    benchmark = api.product_benchmark("cybex__orfeo")
    assert benchmark["product_slug"] == "cybex__orfeo" and "models" in benchmark, "benchmark_payload_invalid"

    # Symulacja znikniętej aukcji: kolejka zgłasza error, ale lokalny snapshot
    # jest nadal dostępny i źródło dalej zawiera evidence.
    snapshot_path = "input/firecrawl_offer_pages/14067359270/technical_clean.md"
    synthetic_source = {
        "source_id": "allegro:99999999999",
        "external_offer_id": "99999999999",
        "marketplace": "allegro",
        "source_type": "marketplace_offer",
        "source_url": "https://allegro.pl/oferta/test-99999999999",
        "content_path": snapshot_path,
        "quality_score": 70,
    }
    synthetic_state = {
        "fields": {
            "Koła": {
                "value": "EVA",
                "evidence": [{
                    "source_id": "allegro:99999999999",
                    "value": "EVA",
                    "evidence": "Koła: EVA",
                }],
            }
        }
    }
    unavailable = api.build_product_sources_payload(
        "synthetic__test",
        {"group_key": "synthetic|test", "brand": "Synthetic", "model": "Test", "sources": [synthetic_source]},
        synthetic_state,
        {"allegro:99999999999": synthetic_source},
        {"99999999999": {"offer_id": "99999999999", "brand": "Synthetic", "detected_model": "Test", "status": "error"}},
        {},
    )
    item = unavailable["sources"][0]
    assert unavailable["unavailable_count"] == 1, "unavailable_source_not_counted"
    assert item["source_status"] == "unavailable", "unavailable_url_not_preserved"
    assert item["snapshot_available"] is True, "snapshot_lost_after_url_error"
    assert item["fields_count"] == 1, "evidence_lost_after_url_error"

    # Pusty group.json musi zwrócić poprawny pusty stan zamiast wyjątku.
    empty = api.build_product_sources_payload("empty__model", {"group_key": "empty|model", "sources": []}, {}, {}, {}, {})
    assert empty["total"] == 0 and empty["sources"] == [], "empty_sources_state_invalid"

    # Snapshot realnego źródła jest dostępny przez bezpieczny, przypisany route.
    source_with_snapshot = next(item for item in tik["sources"] if item["snapshot_available"])
    snapshot = api.product_source_snapshot("kinderkraft__tik", source_with_snapshot["source_id"])
    assert snapshot["content"].strip(), "snapshot_content_empty"

    print(f"primary_sources_count={tik['primary_count']}")
    print(f"supplementary_sources_count={tik['supplementary_count']}")
    print(f"orfeo_selected_count={orfeo['selected_count']}")
    print(f"orfeo_prices_recovered={orfeo['prices_recovered']}")
    print(f"orfeo_saved_analysis={status['can_analyze_saved_data']}")
    print("status_precedence_fixed=True")
    print("repeated_confirmations_aggregated=True")
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
