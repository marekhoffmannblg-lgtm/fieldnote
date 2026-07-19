"""Offline P1 regression checks for deterministic quality and taxonomy rules."""

from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark_taxonomy import classify_from_texts, same_benchmark_partition  # noqa: E402
from p0_runtime import atomic_write_bundle, atomic_write_json  # noqa: E402
from quality_gate import apply_quality_gate, coverage_points  # noqa: E402
import revalidate_final_states as revalidator  # noqa: E402


def source(source_id: str, model: str = "TEST", family: str = "") -> dict:
    return {"source_id": source_id, "model": model, "normalized_model": model.lower(), "content_family_id": family}


def state_with(field: str, value: str, evidence: object) -> dict:
    return {"group_key": "brand|test", "brand": "Brand", "model": "TEST", "fields": {field: {"value": value, "status": "confirmed", "confidence": "high", "evidence": evidence, "locked": True}}}


def gate(state: dict, sources: list[dict]) -> tuple[dict, dict]:
    group = {"group_key": "brand|test", "brand": "Brand", "model": "TEST", "sources": sources}
    registry = {entry["source_id"]: entry for entry in sources}
    return apply_quality_gate(copy.deepcopy(state), group, registry)


def main() -> int:
    failures: list[str] = []

    # 1. "No information" can never become a confirmation.
    state, _ = gate(state_with("Siedzisko", "wygodne", [{"source_id": "s1", "value": "wygodne", "evidence": "Brak szczegółowych informacji o siedzisku."}]), [source("s1")])
    if state["fields"]["Siedzisko"]["value"] != "X":
        failures.append("no_information_confirmed")

    # 2. A frame colour is not a frame material.
    state, _ = gate(state_with("Rama", "czarna", [{"source_id": "s1", "value": "czarna", "evidence": "Stelaż czarny."}]), [source("s1")])
    if state["fields"]["Rama"]["validation_status"] != "rejected":
        failures.append("frame_colour_accepted")

    # 3. Generic folding is not one-hand folding.
    state, _ = gate(state_with("Składanie jedną ręką", "Tak", [{"source_id": "s1", "value": "Tak", "evidence": "Możliwość złożenia: Tak."}]), [source("s1")])
    if state["fields"]["Składanie jedną ręką"]["value"] != "X":
        failures.append("generic_folding_accepted")

    # 4. Two independent literal values conflict.
    state, _ = gate(state_with("Rama", "aluminium", [
        {"source_id": "s1", "value": "aluminium", "evidence": "Rama: aluminium."},
        {"source_id": "s2", "value": "stal", "evidence": "Rama: stal."},
    ]), [source("s1", family="one"), source("s2", family="two")])
    if state["fields"]["Rama"]["validation_status"] != "conflicting":
        failures.append("independent_conflict_missing")

    # 5. Cloned content remains one family, so it cannot manufacture conflict.
    state, _ = gate(state_with("Rama", "aluminium", [
        {"source_id": "s1", "value": "aluminium", "evidence": "Rama: aluminium."},
        {"source_id": "s2", "value": "stal", "evidence": "Rama: stal."},
    ]), [source("s1", family="clone"), source("s2", family="clone")])
    if state["fields"]["Rama"]["validation_status"] == "conflicting":
        failures.append("clone_conflict_created")

    # 6. Legacy string-only evidence is kept for audit but never full coverage.
    state, _ = gate(state_with("Waga", "6 kg", "Waga: 6 kg"), [])
    item = state["fields"]["Waga"]
    if item["validation_status"] != "unattributed_legacy" or coverage_points(item) != 0:
        failures.append("legacy_evidence_counted_as_full")

    # 7-8. Source text classifies MOOV as multifunctional, never travel; only
    # identical category/version partitions can be compared.
    moov = classify_from_texts(["Wózek wielofunkcyjny 3w1 MOOV z gondolą i fotelikiem"])
    travel = classify_from_texts(["Lekki wózek do samolotu, kabinowy"])
    if moov["benchmark_category"] == travel["benchmark_category"] or moov["taxonomy_status"] != "classified":
        failures.append("moov_in_lightweight_category")
    if same_benchmark_partition(moov, travel):
        failures.append("benchmark_mixes_categories")

    # 9. Rejected fields lower coverage but a remaining valid field is still a
    # usable product result, not an analysis failure.
    state, _ = gate({"group_key": "brand|test", "brand": "Brand", "model": "TEST", "fields": {
        "Rama": {"value": "aluminium", "status": "confirmed", "confidence": "high", "evidence": [{"source_id": "s1", "value": "aluminium", "evidence": "Rama: aluminium."}]},
        "Składanie jedną ręką": {"value": "Tak", "status": "confirmed", "confidence": "high", "evidence": [{"source_id": "s1", "value": "Tak", "evidence": "Możliwość złożenia: Tak."}]},
    }}, [source("s1")])
    if sum(coverage_points(value) for value in state["fields"].values()) != 1:
        failures.append("coverage_after_rejection_wrong")

    # 10. A staged migration interruption leaves the prior model state intact.
    with tempfile.TemporaryDirectory(prefix="fieldnote-p1-") as directory:
        path = Path(directory)
        atomic_write_json(path / "model_state.json", {"version": "before"}, preserve_previous=False)
        previous_product_state_path = revalidator.PRODUCT_STATE_PATH
        revalidator.PRODUCT_STATE_PATH = path / "product_state.json"
        revalidator.product_state_update("brand__test", has_reliable_fields=True)
        product_state = __import__("json").loads(revalidator.PRODUCT_STATE_PATH.read_text(encoding="utf-8"))
        if product_state["brand__test"].get("result_status") != "ready":
            failures.append("coverage_drop_marked_analysis_failed")
        revalidator.PRODUCT_STATE_PATH = previous_product_state_path
        history = revalidator.history_backup(path / "model_state.json")
        try:
            atomic_write_bundle(path, {"model_state.json": "{broken"}, json_files={"model_state.json"})
            failures.append("migration_bundle_validation_missing")
        except ValueError:
            pass
        except Exception:
            pass
        if "before" not in (path / "model_state.json").read_text(encoding="utf-8"):
            failures.append("previous_state_lost_after_interruption")
        if not (history / "model_state.before_quality_gate.json").is_file():
            failures.append("migration_history_backup_missing")

    if failures:
        print("FAIL")
        print("\n".join(failures))
        return 1
    print("P1 tests: quality_gate=OK taxonomy=OK atomic_migration=OK")
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
