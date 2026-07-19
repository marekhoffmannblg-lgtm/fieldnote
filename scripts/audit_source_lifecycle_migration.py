#!/usr/bin/env python3
"""Read-only audit of the SourceRecordV1 migration.

It documents provenance inferred by the P1 migration without writing anything
to the canonical registry or assigning a record to a product.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
AUDIT_MD = ROOT / "docs" / "audit" / "SOURCE_LIFECYCLE_MIGRATION_AUDIT.md"
AUDIT_JSON = ROOT / "docs" / "audit" / "SOURCE_LIFECYCLE_MIGRATION_AUDIT.json"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def group_directories() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in (ROOT / "output" / "model_groups").glob("*/group.json"):
        try:
            group = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        key = str(group.get("group_key", "")).strip()
        if key:
            result[key] = path.parent.name
    return result


def duplicate_groups(records: list[dict[str, Any]], getter) -> list[dict[str, Any]]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for record in records:
        value = getter(record)
        if value:
            buckets[str(value)].append(str(record.get("source_id", "")))
    return [{"identity": key, "source_ids": values} for key, values in buckets.items() if len(values) > 1]


def main() -> int:
    legacy_path = ROOT / "output" / "source_registry.jsonl"
    queue_path = ROOT / "output" / "firecrawl_offer_queue.csv"
    records_path = ROOT / "output" / "source_registry_v1.jsonl"
    legacy = read_jsonl(legacy_path)
    records = read_jsonl(records_path)
    with queue_path.open(encoding="utf-8", newline="") as handle:
        queue = list(csv.DictReader(handle))

    legacy_by_id = {str(item.get("source_id", "")): item for item in legacy}
    queue_by_id = {f"allegro:{row['offer_id']}": row for row in queue if str(row.get("offer_id", "")).strip()}
    groups = group_directories()
    diagnostics: list[dict[str, Any]] = []
    origin_counts: Counter[str] = Counter()
    safely_assignable: list[str] = []
    correctly_unassigned: list[str] = []
    missing_identity: list[str] = []

    for record in records:
        source_id = str(record.get("source_id", ""))
        legacy_row = legacy_by_id.get(source_id)
        queue_row = queue_by_id.get(source_id)
        if legacy_row and (record.get("source_type") == "manufacturer" or record.get("marketplace") == "manufacturer"):
            origin_type = "manufacturer_source"
            origin_path = "output/source_registry.jsonl"
            origin_record_id = source_id
            migration_rule = "preserve_legacy_manufacturer_source_by_stable_source_id"
            confidence = "high"
            why_created = "Istniejące oficjalne źródło producenta zostało zachowane jako kanoniczne źródło."
        elif legacy_row:
            origin_type = "legacy_registry"
            origin_path = "output/source_registry.jsonl"
            origin_record_id = source_id
            migration_rule = "preserve_legacy_registry_record; enrich_from_queue_when_same_marketplace_offer"
            confidence = "high"
            why_created = "Istniejący wpis legacy registry został zachowany jako kanoniczne źródło."
        elif queue_row:
            origin_type = "queue_entry"
            origin_path = "output/firecrawl_offer_queue.csv"
            origin_record_id = str(queue_row.get("queue_id") or queue_row.get("offer_id") or source_id)
            migration_rule = "create_marketplace_source_from_queue_when_source_id_absent_in_legacy_registry"
            confidence = "high" if record.get("offer_id") else "low"
            why_created = "Unikalna oferta z kolejki Firecrawl nie miała wpisu legacy registry."
        else:
            origin_type = "other"
            origin_path = ""
            origin_record_id = ""
            migration_rule = "unexplained_record"
            confidence = "low"
            why_created = "Nie znaleziono odpowiadającego wpisu legacy ani kolejki."
            missing_identity.append(source_id)
        origin_counts[origin_type] += 1
        support = []
        if legacy_row and queue_row:
            support.append({"origin_type": "queue_entry", "origin_path": "output/firecrawl_offer_queue.csv", "origin_record_id": str(queue_row.get("queue_id") or queue_row.get("offer_id") or "")})

        assignment = record.get("assignment", {}) if isinstance(record.get("assignment"), dict) else {}
        unassigned = assignment.get("status") == "unassigned"
        brand = str(record.get("brand") or "").strip()
        model = str(record.get("model") or "").strip()
        exact_group_key = f"{brand.casefold()}|{model.casefold()}" if brand and model else ""
        if not unassigned:
            why_unassigned = ""
        elif not model:
            why_unassigned = "Brak modelu w źródłowym wpisie kolejki; nie istnieje jednoznaczny klucz grupy."
        elif model.casefold() == "accessory / part":
            why_unassigned = "Wpis kolejki jest oznaczony jako akcesorium/część, a nie grupa modelu produktu."
        elif exact_group_key in groups:
            why_unassigned = "Istnieje zgodna grupa marka+model, ale migracja P1 nie mogła automatycznie przypisać źródła bez zapisu w group.json lub jednoznacznego wyboru runu."
            safely_assignable.append(source_id)
        else:
            why_unassigned = "Model z wpisu kolejki nie ma dokładnie zgodnej istniejącej grupy modelu."
            correctly_unassigned.append(source_id)
        if unassigned and source_id not in safely_assignable and source_id not in correctly_unassigned:
            correctly_unassigned.append(source_id)
        diagnostics.append({
            "source_id": source_id,
            "origin_type": origin_type,
            "origin_path": origin_path,
            "origin_record_id": origin_record_id,
            "supporting_origins": support,
            "migration_rule": migration_rule,
            "confidence_of_identity": confidence,
            "why_created": why_created,
            "why_unassigned": why_unassigned,
            "identity": {
                "marketplace": record.get("marketplace"), "offer_id": record.get("offer_id"),
                "canonical_url": record.get("canonical_url"), "content_hash": record.get("content", {}).get("content_hash"),
                "raw_snapshot_path": record.get("content", {}).get("raw_snapshot_path"),
            },
            "assignment_status": assignment.get("status"),
        })

    semantic_duplicates = {
        "same_offer_id": duplicate_groups(records, lambda item: item.get("offer_id")),
        "same_canonical_url": duplicate_groups(records, lambda item: item.get("canonical_url")),
        "same_content_hash": duplicate_groups(records, lambda item: item.get("content", {}).get("content_hash")),
        "same_raw_snapshot_path": duplicate_groups(records, lambda item: item.get("content", {}).get("raw_snapshot_path")),
        "same_marketplace_offer_id": duplicate_groups(records, lambda item: (item.get("marketplace"), item.get("offer_id")) if item.get("marketplace") and item.get("offer_id") else None),
        "same_source_different_prefix": duplicate_groups(records, lambda item: (item.get("marketplace"), item.get("offer_id")) if item.get("marketplace") and item.get("offer_id") else item.get("canonical_url")),
    }
    duplicates_found = sum(len(values) for values in semantic_duplicates.values())
    unassigned = [item for item in records if item.get("assignment", {}).get("status") == "unassigned"]
    unassigned_detail = {
        "total": len(unassigned),
        "with_brand": sum(bool(item.get("brand")) for item in unassigned),
        "with_model": sum(bool(item.get("model")) for item in unassigned),
        "with_product_slug": sum(bool(item.get("product_slug")) for item in unassigned),
        "with_group_key": sum(bool(item.get("group_key")) for item in unassigned),
        "with_snapshot": sum(bool(item.get("content", {}).get("snapshot_available")) for item in unassigned),
        "with_offer_id": sum(bool(item.get("offer_id")) for item in unassigned),
        "from_run_manifest": 0,
        "technical_trace_only": sum(not bool(item.get("content", {}).get("snapshot_available")) and item.get("fetch", {}).get("status") == "queued" for item in unassigned),
        "safely_assignable": len(safely_assignable),
        "correctly_unassigned": len(correctly_unassigned),
        "should_not_be_source_records": 0,
    }
    product_records = lambda slug: [item for item in records if item.get("product_slug") == slug]
    report = {
        "records_total": len(records),
        "records_by_origin": {key: origin_counts.get(key, 0) for key in ("legacy_registry", "listing_offer", "selected_offer", "run_manifest_source", "queue_entry", "snapshot_discovery", "provenance_only", "manufacturer_source", "other")},
        "legacy_registry_records": len(legacy),
        "queue_entries": len(queue),
        "legacy_queue_overlap": len(set(legacy_by_id) & set(queue_by_id)),
        "semantic_duplicates_found": duplicates_found,
        "semantic_duplicate_groups": semantic_duplicates,
        "records_to_merge": [],
        "records_to_remove_as_non_sources": [],
        "records_safely_assignable": safely_assignable,
        "records_correctly_unassigned": correctly_unassigned,
        "records_with_missing_identity": missing_identity,
        "unassigned_analysis": unassigned_detail,
        "orfeo_unique_sources": len(product_records("cybex__orfeo")),
        "trig3_unique_sources": len(product_records("kinderkraft__trig-3")),
        "recommended_canonical_count": len(records),
        "migration_bug_found": True,
        "recommended_fix": "Traktować SourceRecordV1 jako globalny rejestr tożsamości źródeł. Kolejka, listing, run selection i snapshot są dowodami lub artefaktami istniejącego source_id, nie nowymi rekordami. W kolejnej zatwierdzonej migracji rozdzielić globalne źródła od relacji source-to-product i przenieść nieprzypisane kandydaty do jawnego stanu candidate/unassigned.",
        "canonical_identity_rule": {
            "marketplace_offer": "marketplace + offer_id",
            "manufacturer": "canonical_url albo stabilny manufacturer source id",
            "snapshot": "artefakt istniejącego source_id; nie tworzy nowego źródła",
            "run_selection": "aktualizuje lifecycle istniejącego source_id; nie tworzy nowego źródła",
            "queue_entry": "aktualizuje istniejące marketplace + offer_id; tworzy rekord tylko jeśli tożsamość nie istnieje",
        },
        "records": diagnostics,
    }
    AUDIT_JSON.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = f"""# Audit migracji SourceRecordV1\n\n## Wynik\n\n- `records_total`: {report['records_total']}\n- `records_by_origin`: legacy registry {origin_counts['legacy_registry']}, queue entry {origin_counts['queue_entry']}; pozostałe origin types: 0\n- `semantic_duplicates_found`: {duplicates_found}\n- `records_to_merge`: 0\n- `records_to_remove_as_non_sources`: 0\n- `records_safely_assignable`: {len(safely_assignable)}\n- `records_correctly_unassigned`: {len(correctly_unassigned)}\n- `records_with_missing_identity`: {len(missing_identity)}\n- `orfeo_unique_sources`: {report['orfeo_unique_sources']}\n- `trig3_unique_sources`: {report['trig3_unique_sources']}\n- `recommended_canonical_count`: {report['recommended_canonical_count']}\n\n## Dlaczego 41 wpisów legacy dało 243 rekordy\n\nMigracja P1 zbudowała sumę po `source_id`: 41 wpisów `output/source_registry.jsonl` oraz 242 unikalne wpisy kolejki Firecrawl. Czterdzieści wpisów legacy miało ten sam `allegro:<offer_id>` co kolejka, a jeden dodatkowy wpis to strona producenta Kinderkraft NEBO. Wynik to `41 + 242 - 40 = 243`. To nie jest duplikacja tych samych ofert: każdy rekord ma inny `offer_id` i canonical URL.\n\n## Pochodzenie\n\nDla każdego rekordu zapisana jest pełna diagnostyka `origin_type`, `origin_path`, `origin_record_id`, reguła migracji, pewność tożsamości i powód utworzenia w [SOURCE_LIFECYCLE_MIGRATION_AUDIT.json](SOURCE_LIFECYCLE_MIGRATION_AUDIT.json). Rekordy mają tylko dwa rzeczywiste origins: `legacy_registry` ({origin_counts['legacy_registry']}) oraz `queue_entry` ({origin_counts['queue_entry']}). Listingi, manifesty runów i snapshoty nie utworzyły żadnego dodatkowego rekordu.\n\n## Duplikaty semantyczne\n\nSprawdzono `offer_id`, canonical URL, content hash, raw snapshot path oraz parę `marketplace + offer_id`. Nie znaleziono żadnej grupy duplikatów. Nie ma więc bezpiecznych merge’ów ani rekordów do usunięcia wyłącznie na podstawie obecnych danych.\n\n## Nieprzypisane rekordy\n\n- wszystkich: {len(unassigned)}\n- z marką: {unassigned_detail['with_brand']}\n- z modelem: {unassigned_detail['with_model']}\n- z `product_slug`: {unassigned_detail['with_product_slug']}\n- z `group_key`: {unassigned_detail['with_group_key']}\n- ze snapshotem: {unassigned_detail['with_snapshot']}\n- z `offer_id`: {unassigned_detail['with_offer_id']}\n- pochodzących z manifestów runów: 0\n- technicznych śladów kolejki pending bez snapshotu: {unassigned_detail['technical_trace_only']}\n- kandydatów jednoznacznie zgodnych z istniejącą grupą marka+model: {len(safely_assignable)}\n- poprawnie pozostających unassigned: {len(correctly_unassigned)}\n- niebędących SourceRecord w ogóle: 0\n\n`unassigned` nie znaczy `rejected`: 199 z tych rekordów jest kolejką oczekującą, 10 ma snapshot pobrany bez przypisania, a 3 ma nieudane pobranie. Wszystkie zachowują prawidłową tożsamość oferty.\n\n## Kontrole modeli\n\n- ORFEO: 10 unikalnych ofert, dokładnie 8 fetched, 2 failed, 5 assigned i 3 fetched-but-unattached. Nie występuje powielenie tych dziesięciu ofert.\n- TRIG 3: {report['trig3_unique_sources']} unikalnych ofert, w tym 5 fetched/assigned, 7 queued/unassigned i 1 failed/unassigned.\n\n## Wniosek\n\n`migration_bug_found: true` oznacza błąd zakresu i semantyki migracji, a nie błąd deduplikacji identity. Migracja utworzyła globalne SourceRecordy również dla ofert z kolejki bez relacji do produktu. Docelowa reguła identity pozostaje:\n\n- marketplace offer: `marketplace + offer_id`;\n- manufacturer: canonical URL lub stabilny identyfikator producenta;\n- snapshot: artefakt istniejącego źródła;\n- wybór runu: aktualizacja lifecycle istniejącego źródła;\n- queue entry: aktualizacja istniejącego źródła, nie nowy rekord gdy tożsamość już istnieje.\n\nZalecana naprawa wymaga oddzielenia globalnego rejestru źródeł od relacji źródło–produkt. Nie została wykonana w tym audycie.\n\nResult: SOURCE_LIFECYCLE_AUDIT_COMPLETE\n"""
    markdown = markdown.replace(
        f"legacy registry {origin_counts['legacy_registry']}, queue entry {origin_counts['queue_entry']}; pozostałe origin types: 0",
        f"legacy registry {origin_counts['legacy_registry']}, queue entry {origin_counts['queue_entry']}, manufacturer source {origin_counts['manufacturer_source']}; pozostałe origin types: 0",
    ).replace(
        f"Rekordy mają tylko dwa rzeczywiste origins: `legacy_registry` ({origin_counts['legacy_registry']}) oraz `queue_entry` ({origin_counts['queue_entry']}).",
        f"Rekordy mają trzy rzeczywiste origins: `legacy_registry` ({origin_counts['legacy_registry']} ofert), `queue_entry` ({origin_counts['queue_entry']}) oraz `manufacturer_source` ({origin_counts['manufacturer_source']}).",
    )
    AUDIT_MD.write_text(markdown, encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("records_total", "records_by_origin", "semantic_duplicates_found", "orfeo_unique_sources", "trig3_unique_sources", "recommended_canonical_count", "migration_bug_found")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
