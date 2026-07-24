#!/usr/bin/env python3
"""Import canonical Lionelo stroller specifications from the WÓZKI workbook.

This importer deliberately writes independent internal specification snapshots.
It never changes the product catalog or research artifacts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from catalog_registry import product_slug_for

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "catalog" / "products.json"
OUTPUT_DIR = ROOT / "data" / "internal_specs"
SOURCE_SHEET = "WÓZKI"
STROLLER_GROUPS = {
    "light_stroller": 10,
    "standard_stroller": 7,
    "stroller_2in1": 8,
    "stroller_3in1": 9,
}
NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

# These are stable keys for the relevant, non-marketing WÓZKI worksheet columns.
ATTRIBUTE_KEYS = {
    "Typ produktu": "product_type",
    "Konfiguracja wózka": "stroller_configuration",
    "Zapięcie pasów": "harness_buckle",
    "Pasy bezpieczeństwa": "safety_harness",
    "Hamulec": "brake",
    "Blokada kół do jazdy na wprost": "straight_wheel_lock",
    "Normy i certyfikaty": "safety_standards",
    "Rodzaj kół": "wheel_type",
    "Materiał kół": "wheel_material",
    "Koła przód (cm)": "front_wheel_diameter",
    "Koła tył (cm)": "rear_wheel_diameter",
    "Amortyzacja": "suspension",
    "Przednie koła obrotowe": "swivel_front_wheels",
    "Regulacja rączki dla rodzica": "parent_handle_adjustment",
    "Składanie jedną ręką": "one_hand_fold",
    "Możliwość przenoszenia dziecka w gondoli": "carrycot_child_carrying",
    "Maksymalne obciążenie kosza (kg)": "basket_max_load",
    "Maksymalna waga dziecka w spacerówce (kg)": "max_child_weight_stroller",
    "Maksymalna waga dziecka w gondoli (kg)": "max_child_weight_carrycot",
    "Wiek dziecka": "child_age_range",
    "Możliwość montażu siedziska przód-tył": "reversible_seat",
    "Regulacja oparcia": "backrest_adjustment",
    "Regulacja podnóżka": "footrest_adjustment",
    "Wentylacja gondoli": "carrycot_ventilation",
    "Filtr UPF50+": "upf50_filter",
    "Odpinana barierka": "removable_bumper_bar",
    "Konstrukcja stelaża": "frame_construction",
    "Materiał budki": "canopy_material",
    "Materiał gondoli": "carrycot_material",
    "Szerokość (cm)": "product_width",
    "Długość (cm)": "product_length",
    "Wysokość (cm)": "product_height",
    "Szerokość po złożeniu (cm)": "folded_width",
    "Długość po złożeniu (cm)": "folded_length",
    "Wysokość po złożeniu (cm)": "folded_height",
    "Długość gondoli (cm)": "carrycot_length",
    "Wysokość gondoli (cm)": "carrycot_height",
    "Szerokość gondoli (cm)": "carrycot_width",
    "Długość wewnętrzna gondoli (cm)": "carrycot_inner_length",
    "Szerokość wewnętrzna gondoli (cm)": "carrycot_inner_width",
    "Wysokość siedziska od ziemi (cm)": "seat_height",
    "Szerokość siedziska (cm)": "seat_width",
    "Wysokość oparcia (cm)": "backrest_height",
    "Szerokość oparcia (cm)": "backrest_width",
    "Wysokość podnóżka (cm)": "footrest_height",
    "Szerokość podnóżka (cm)": "footrest_width",
    "Waga stelaża (kg)": "frame_weight",
    "Waga stelaża z kołami (kg)": "frame_with_wheels_weight",
    "Waga spacerówki (kg)": "stroller_weight",
    "Waga spacerówki z gondolą (kg)": "stroller_with_carrycot_weight",
    "Waga gondoli (kg)": "carrycot_weight",
    "Waga siedziska (kg)": "seat_weight",
    "Waga fotelika (kg)": "car_seat_weight",
    "Zestaw": "included_items",
}
ALLOWED_SECTIONS = {"Parametry / techniczne", "Funkcjonalność", "Specyfikacja ogólna", "Zestaw"}


def normalize_identity(value: object) -> str:
    transliteration = str.maketrans("ąćęłńóśźż", "acelnoszz")
    return "".join(
        char for char in str(value or "").casefold().translate(transliteration) if char.isalnum()
    )


def normalized_configuration(value: object) -> str:
    normalized = normalize_identity(value)
    # Catalog uses an empty configuration for a single stroller, while WÓZKI
    # uses the descriptive type "Spacerówka". Both identify the same product.
    return "" if normalized == "spacerowka" else normalized


def column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha())
    result = 0
    for character in letters:
        result = result * 26 + ord(character.upper()) - ord("A") + 1
    return result - 1


def read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(item.itertext()) for item in root.findall(f"{NS_MAIN}si")]


def worksheet_path(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rel_id = None
    for sheet in workbook.findall(f"{NS_MAIN}sheets/{NS_MAIN}sheet"):
        if sheet.get("name") == sheet_name:
            rel_id = sheet.get(f"{NS_REL}id")
            break
    if not rel_id:
        raise ValueError(f"Brak zakładki {sheet_name!r} w skoroszycie.")
    relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for relation in relations.findall(f"{NS_PACKAGE_REL}Relationship"):
        if relation.get("Id") == rel_id:
            target = relation.get("Target", "")
            return target.lstrip("/") if target.startswith("xl/") else f"xl/{target}"
    raise ValueError(f"Brak relacji dla zakładki {sheet_name!r}.")


def read_xlsx_rows(workbook_path: Path, sheet_name: str = SOURCE_SHEET) -> list[list[str]]:
    """Read worksheet values without a runtime dependency on openpyxl."""
    with zipfile.ZipFile(workbook_path) as archive:
        shared_strings = read_shared_strings(archive)
        worksheet = ET.fromstring(archive.read(worksheet_path(archive, sheet_name)))
    rows: list[list[str]] = []
    for row in worksheet.findall(f"{NS_MAIN}sheetData/{NS_MAIN}row"):
        cells: dict[int, str] = {}
        for cell in row.findall(f"{NS_MAIN}c"):
            index = column_index(cell.get("r", "A1"))
            cell_type = cell.get("t")
            if cell_type == "inlineStr":
                value = "".join(cell.find(f"{NS_MAIN}is").itertext()) if cell.find(f"{NS_MAIN}is") is not None else ""
            else:
                value_node = cell.find(f"{NS_MAIN}v")
                value = value_node.text if value_node is not None and value_node.text is not None else ""
                if cell_type == "s" and value:
                    value = shared_strings[int(value)]
            cells[index] = value.strip()
        width = max(cells, default=-1) + 1
        rows.append([cells.get(index, "") for index in range(width)])
    return rows


def value_at(row: list[str], index: int) -> str:
    return row[index].strip() if index < len(row) and row[index] else ""


def unit_for(label: str) -> str:
    match = re.search(r"\((kg|cm)\)", label, flags=re.IGNORECASE)
    return match.group(1).casefold() if match else ""


def normalize_value(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return "unknown"
    if value.casefold() == "n/d":
        return "not_applicable"
    if value.casefold() == "tak":
        return "yes"
    if value.casefold() == "nie":
        return "no"
    if re.fullmatch(r"[+-]?\d+,\d+", value):
        return value.replace(",", ".")
    return value


def load_catalog_products(catalog_path: Path) -> list[dict[str, Any]]:
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    products = data.get("products", data) if isinstance(data, dict) else data
    return [
        product for product in products
        if normalize_identity(product.get("brand")) == "lionelo"
        and product.get("benchmark_group") in STROLLER_GROUPS
    ]


def catalog_product_slug(product: dict[str, Any]) -> str:
    return str(product.get("slug") or product_slug_for(
        str(product["brand"]), str(product["model"]), str(product.get("configuration", ""))
    ))


def allowed_columns(sections: list[str], labels: list[str]) -> list[tuple[int, str, str]]:
    columns: list[tuple[int, str, str]] = []
    for index, label in enumerate(labels):
        section = value_at(sections, index)
        if section not in ALLOWED_SECTIONS or label not in ATTRIBUTE_KEYS:
            continue
        columns.append((index, label, ATTRIBUTE_KEYS[label]))
    return columns


def snapshot_for_product(
    product: dict[str, Any], source_rows: list[tuple[int, list[str]]], columns: list[tuple[int, str, str]], generated_at: str,
) -> dict[str, Any]:
    attributes: list[dict[str, str]] = []
    conflicts: list[dict[str, Any]] = []
    for index, label, key in columns:
        values: dict[str, list[int]] = defaultdict(list)
        for excel_row, row in source_rows:
            values[value_at(row, index)].append(excel_row)
        normalized_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
        for raw_value, source_row_numbers in values.items():
            normalized_groups[(normalize_value(raw_value), raw_value)].extend(source_row_numbers)
        distinct = list(normalized_groups.items())
        unit = unit_for(label)
        if len(distinct) == 1:
            (value, raw_value), _rows = distinct[0]
        else:
            value, raw_value = "conflicting", ""
            conflicts.append({
                "key": key,
                "label": label,
                "source_column": label,
                "values": [
                    {"value": normalized, "raw_value": raw, "source_rows": sorted(row_numbers)}
                    for (normalized, raw), row_numbers in distinct
                ],
            })
        attributes.append({
            "key": key,
            "label": label,
            "value": value,
            "raw_value": raw_value,
            "unit": unit,
            "source_column": label,
        })
    return {
        "schema_version": "internal_spec_v1",
        "product_id": product["product_id"],
        "product_slug": catalog_product_slug(product),
        "brand": product["brand"],
        "model": product["model"],
        "configuration": product.get("configuration", ""),
        "benchmark_group": product["benchmark_group"],
        "source_type": "internal_spec",
        "source_sheet": SOURCE_SHEET,
        "source_rows": sorted(excel_row for excel_row, _row in source_rows),
        "generated_at": generated_at,
        "attributes": attributes,
        "conflicts": conflicts,
    }


def build_snapshots(products: list[dict[str, Any]], rows: list[list[str]], generated_at: str) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str]]]:
    if len(rows) < 6:
        raise ValueError("Zakładka WÓZKI nie zawiera wymaganych wierszy nagłówkowych.")
    sections, labels = rows[1], rows[2]
    model_index = labels.index("model")
    configuration_index = labels.index("Konfiguracja wózka")
    columns = allowed_columns(sections, labels)
    if not columns:
        raise ValueError("Nie znaleziono dozwolonych kolumn technicznych w zakładce WÓZKI.")

    catalog_by_identity = {
        (normalize_identity(product["model"]), normalized_configuration(product.get("configuration", ""))): product
        for product in products
    }
    matched_rows: dict[tuple[str, str], list[tuple[int, list[str]]]] = defaultdict(list)
    unmatched: list[tuple[str, str]] = []
    for excel_row, row in enumerate(rows[5:], start=6):
        model = value_at(row, model_index)
        if not model:
            continue
        identity = (normalize_identity(model), normalized_configuration(value_at(row, configuration_index)))
        if identity in catalog_by_identity:
            matched_rows[identity].append((excel_row, row))
        else:
            unmatched.append((model, value_at(row, configuration_index)))

    missing = sorted(set(catalog_by_identity) - set(matched_rows))
    if missing:
        names = [f"{catalog_by_identity[key]['model']} {catalog_by_identity[key].get('configuration', '')}".strip() for key in missing]
        raise ValueError(f"Brak wierszy WÓZKI dla produktów katalogowych: {', '.join(names)}")

    snapshots = {
        catalog_product_slug(product): snapshot_for_product(product, matched_rows[identity], columns, generated_at)
        for identity, product in catalog_by_identity.items()
    }
    return snapshots, unmatched


def validate_snapshots(snapshots: dict[str, dict[str, Any]], products: list[dict[str, Any]]) -> None:
    expected_slugs = {catalog_product_slug(product) for product in products}
    if set(snapshots) != expected_slugs or len(snapshots) != 34:
        raise ValueError("Importer musi utworzyć dokładnie 34 snapshoty dla katalogowych wózków Lionelo.")
    groups = Counter(snapshot["benchmark_group"] for snapshot in snapshots.values())
    if dict(groups) != STROLLER_GROUPS:
        raise ValueError(f"Nieprawidłowy rozkład grup benchmarkowych: {dict(groups)}")
    for slug, snapshot in snapshots.items():
        if not snapshot["attributes"]:
            raise ValueError(f"Snapshot {slug} nie zawiera parametrów technicznych.")
        if snapshot["product_slug"] != slug or snapshot["source_type"] != "internal_spec":
            raise ValueError(f"Snapshot {slug} ma nieprawidłową tożsamość.")


def write_snapshots(snapshots: dict[str, dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for slug, snapshot in snapshots.items():
        path = output_dir / f"{slug}.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)


def default_workbook_path() -> Path:
    candidates = [
        ROOT / "specyfikacja per produkt.xlsx",
        ROOT / "specyfikacja per produkt .xlsx",
        Path.home() / "Downloads" / "specyfikacja per produkt.xlsx",
        Path.home() / "Downloads" / "specyfikacja per produkt .xlsx",
    ]
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="Importuje snapshoty specyfikacji wózków Lionelo.")
    parser.add_argument("--xlsx", type=Path, default=default_workbook_path())
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--generated-at", default=None, help="ISO timestamp used for reproducible output.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.xlsx.exists():
        print(f"Brak pliku XLSX: {args.xlsx}", file=sys.stderr)
        return 2
    try:
        products = load_catalog_products(args.catalog)
        generated_at = args.generated_at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        snapshots, unmatched = build_snapshots(products, read_xlsx_rows(args.xlsx), generated_at)
        validate_snapshots(snapshots, products)
        if not args.dry_run:
            write_snapshots(snapshots, args.output_dir)
    except (ValueError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        print(f"import_status=failed\nerror={error}", file=sys.stderr)
        return 1
    print("import_status=success")
    print(f"snapshots_written={0 if args.dry_run else len(snapshots)}")
    print(f"snapshots_validated={len(snapshots)}")
    print(f"variant_conflicts={sum(len(snapshot['conflicts']) for snapshot in snapshots.values())}")
    print(f"unmatched_source_rows={len(unmatched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
