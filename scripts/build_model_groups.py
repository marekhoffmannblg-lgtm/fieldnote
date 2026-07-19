from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

from catalog_registry import product_for_group_key
from p0_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "output" / "source_registry.jsonl"
PAGES = ROOT / "input" / "firecrawl_offer_pages"
OUT = ROOT / "output" / "model_groups"
LEGACY_BACKUP = ROOT / "output" / "model_groups_legacy_backup"


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def model_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def canonical_directory(group: dict) -> Path:
    brand = str(group.get("brand", "")).strip()
    model = str(group.get("model", "")).strip()
    if (not brand or not model) and "|" in str(group.get("group_key", "")):
        normalized_brand, normalized_model = str(group["group_key"]).split("|", 1)
        brand = brand or normalized_brand
        model = model or normalized_model
    if not brand or not model:
        raise ValueError(f"Nie można wyznaczyć folderu kanonicznego dla group_key={group.get('group_key', '')}")
    return OUT / f"{model_slug(brand)}__{model_slug(model)}"


def state_rank(path: Path) -> tuple[int, int, int, int, float]:
    state = read_json(path)
    fields = state.get("fields", {}) if isinstance(state.get("fields", {}), dict) else {}
    confirmed = sum(
        isinstance(item, dict) and str(item.get("value", "X")) != "X"
        for item in fields.values()
    )
    evidence_count = 0
    for item in fields.values():
        if not isinstance(item, dict):
            continue
        evidence = item.get("evidence")
        if isinstance(evidence, list):
            evidence_count += len([value for value in evidence if value])
        elif evidence:
            evidence_count += 1
    processed = len(state.get("processed_source_ids", [])) if isinstance(state.get("processed_source_ids"), list) else 0
    populated = sum(
        isinstance(item, dict)
        and (str(item.get("value", "X")) != "X" or item.get("status") not in {"", "open", None})
        for item in fields.values()
    )
    mtime = path.stat().st_mtime if path.exists() else 0.0
    return confirmed, evidence_count, processed, populated, mtime


def unique_backup_path(name: str) -> Path:
    LEGACY_BACKUP.mkdir(parents=True, exist_ok=True)
    candidate = LEGACY_BACKUP / name
    suffix = 1
    while candidate.exists():
        candidate = LEGACY_BACKUP / f"{name}_{suffix}"
        suffix += 1
    return candidate


def copy_missing_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(item, target)
            continue
        if target.read_bytes() == item.read_bytes():
            continue
        counter = 1
        while True:
            alternate = target.with_name(f"{target.stem}__legacy_{counter}{target.suffix}")
            if not alternate.exists():
                shutil.copy2(item, alternate)
                break
            counter += 1


def merge_legacy_folder(legacy: Path, canonical: Path) -> None:
    canonical.mkdir(parents=True, exist_ok=True)
    legacy_state = legacy / "model_state.json"
    canonical_state = canonical / "model_state.json"
    if legacy_state.exists() and (
        not canonical_state.exists() or state_rank(legacy_state) > state_rank(canonical_state)
    ):
        if canonical_state.exists():
            shutil.copy2(canonical_state, legacy / "canonical_model_state_backup.json")
        shutil.copy2(legacy_state, canonical_state)
    copy_missing_tree(legacy / "prompts", canonical / "prompts")
    copy_missing_tree(legacy / "steps", canonical / "steps")
    if not (canonical / "group.json").exists() and (legacy / "group.json").exists():
        shutil.copy2(legacy / "group.json", canonical / "group.json")
    shutil.move(str(legacy), str(unique_backup_path(legacy.name)))


def resolve_existing_group_folders(group_key: str = "") -> int:
    if not OUT.exists():
        return 0
    entries: dict[str, list[tuple[Path, dict]]] = {}
    for directory in sorted(path for path in OUT.iterdir() if path.is_dir()):
        group_path = directory / "group.json"
        if not group_path.exists():
            continue
        group = read_json(group_path)
        key = str(group.get("group_key", "")).strip()
        if key and (not group_key or key == group_key):
            entries.setdefault(key, []).append((directory, group))

    resolved = 0
    for key, folders in entries.items():
        canonical = canonical_directory(folders[0][1])
        if canonical.exists() and (canonical / "group.json").exists():
            canonical_group = read_json(canonical / "group.json")
            if canonical_group.get("group_key") not in {"", key}:
                raise RuntimeError(
                    f"Folder kanoniczny {canonical.name} należy do innego group_key: "
                    f"{canonical_group.get('group_key')}"
                )
        for directory, _group in folders:
            if directory == canonical:
                continue
            merge_legacy_folder(directory, canonical)
            resolved += 1
    return resolved


def validate_unique_canonical_groups(group_key: str = "") -> int:
    seen: dict[str, Path] = {}
    canonical_count = 0
    for directory in sorted(path for path in OUT.iterdir() if path.is_dir()):
        group_path = directory / "group.json"
        if not group_path.exists():
            continue
        group = read_json(group_path)
        key = str(group.get("group_key", "")).strip()
        if group_key and key != group_key:
            continue
        expected = canonical_directory(group)
        if directory != expected:
            raise RuntimeError(f"Niekanoniczny folder grupy: {directory.name} dla {key}")
        if key in seen:
            raise RuntimeError(f"Powielony group_key: {key} ({seen[key].name}, {directory.name})")
        seen[key] = directory
        canonical_count += 1
    return canonical_count


def content_text(row: dict) -> str:
    """Return source text for quality/similarity without requiring Allegro sections."""
    path_value = str(row.get("content_path", "") or row.get("offer_sections_path", "")).strip()
    if not path_value:
        return ""
    path = ROOT / path_value
    if path.suffix.lower() == ".json":
        data = read_json(path)
        sections = data.get("sections", {}) if isinstance(data.get("sections", {}), dict) else {}
        return "\n".join(str(value) for value in sections.values() if value)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def source_quality(row: dict, text: str) -> tuple[int, list[str]]:
    if row.get("marketplace") == "manufacturer":
        reasons = ["primary_manufacturer_source"]
        if text.strip():
            reasons.append("technical_clean_present")
        return int(row.get("quality_score", 100) or 100), reasons
    sections_file = ROOT / str(row.get("offer_sections_path", ""))
    data = read_json(sections_file)
    sections = data.get("sections", {}) if isinstance(data.get("sections", {}), dict) else {}
    score = sum(
        points
        for name, points in (("technical_details", 30), ("description", 25), ("parameters", 20), ("reviews", 10))
        if sections.get(name)
    )
    directory = sections_file.parent
    seller = read_json(directory / "seller_info.json")
    reasons = [name + "_present" for name in ("technical_details", "description", "parameters", "reviews") if sections.get(name)]
    if seller.get("seller_name") or seller.get("seller_rating"):
        score += 10
        reasons.append("seller_info")
    return int(row.get("quality_score", score) or score), reasons


def assign_content_families(sources: list[dict]) -> None:
    """Mark duplicated vendor/shop copy, but keep both sources for auditability."""
    families: dict[str, list[dict]] = {}
    for source in sources:
        content_hash = str(source.get("content_hash", "")).strip()
        if content_hash:
            families.setdefault(f"hash:{content_hash}", []).append(source)
    normalized_texts: list[tuple[dict, set[str]]] = []
    for source in sources:
        text = str(source.pop("_content_text", ""))
        tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
        if tokens:
            normalized_texts.append((source, tokens))
    for index, (source, tokens) in enumerate(normalized_texts):
        for other, other_tokens in normalized_texts[index + 1:]:
            overlap = len(tokens & other_tokens)
            baseline = min(len(tokens), len(other_tokens))
            if baseline >= 20 and overlap / baseline >= 0.88:
                key = "similar:" + hashlib.sha256("|".join(sorted((source["source_id"], other["source_id"]))).encode()).hexdigest()[:16]
                families.setdefault(key, []).extend([source, other])
    for family, members in families.items():
        unique_members = {member.get("source_id", ""): member for member in members}.values()
        if len(list(unique_members)) < 2:
            continue
        family_id = "content_family:" + hashlib.sha256(family.encode()).hexdigest()[:12]
        for member in members:
            member["content_family_id"] = family_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-offers-per-model", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--group-key", help="Przebudowuje wyłącznie wskazaną grupę bez dotykania innych folderów.")
    args = parser.parse_args()
    if not REGISTRY.exists():
        print("Brak output/source_registry.jsonl. Uruchom najpierw: python3 scripts/build_source_registry.py")
        return 1
    try:
        duplicate_groups_resolved = resolve_existing_group_folders(args.group_key or "")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Błąd porządkowania grup: {exc}")
        return 1
    queue = [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    groups: dict[str, dict] = {}
    for row in queue:
        if not row.get("eligible_for_grouping", False):
            continue
        brand = str(row.get("brand", "")).strip()
        model = str(row.get("model", "")).strip()
        if not brand or not model or model.lower() in {"accessory / part", "accessory", "part"}:
            continue
        key = str(row.get("group_key", "")).strip() or f"{row.get('normalized_brand', brand.lower())}|{row.get('normalized_model', model.lower())}"
        text = content_text(row)
        if not text:
            continue
        score, reasons = source_quality(row, text)
        sections_path = str(row.get("offer_sections_path", ""))
        sections_file = ROOT / sections_path if sections_path else Path()
        directory = sections_file.parent if sections_path else ROOT / str(row.get("manufacturer_source_path", ""))
        group = groups.setdefault(
            key,
            {
                "group_key": key,
                "brand": brand,
                "model": model,
                "product_id": row.get("product_id", ""),
                "category": row.get("category", ""),
                "benchmark_category": row.get("benchmark_category", ""),
                "subcategory": row.get("subcategory", ""),
                "taxonomy_version": row.get("taxonomy_version", ""),
                "taxonomy_status": row.get("taxonomy_status", "review_required"),
                "offers": [],
            },
        )
        group["offers"].append({
            "offer_id": row.get("external_offer_id", ""),
            "source_url": row.get("source_url", ""),
            "canonical_url": row.get("canonical_url", row.get("source_url", "")),
            "source_id": row.get("source_id", ""),
            "product_id": row.get("product_id", ""),
            "group_key": key,
            "marketplace": row.get("marketplace", ""),
            "source_type": row.get("source_type", ""),
            "authority_level": row.get("authority_level", ""),
            "domain": row.get("domain", ""),
            "content_hash": row.get("content_hash", ""),
            "content_family_id": row.get("content_family_id", ""),
            "offer_sections_path": sections_path,
            "seller_info_path": str(row.get("seller_info_path", "")),
            "product_images_path": str(row.get("product_images_path", "")),
            "product_facts_ai_path": row.get("product_facts_ai_path", ""),
            "content_path": row.get("content_path", ""),
            "manufacturer_source_path": row.get("manufacturer_source_path", ""),
            "quality_score": score,
            "quality_reasons": reasons,
            "_content_text": text,
        })
    if args.group_key:
        groups = {key: group for key, group in groups.items() if key == args.group_key}
        if not groups:
            print(f"Brak źródeł do grupy: {args.group_key}")
            return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for group in groups.values():
        catalog_product = product_for_group_key(str(group.get("group_key", "")))
        if catalog_product:
            for key in ("category", "subcategory", "benchmark_category", "taxonomy_version", "taxonomy_status", "taxonomy_reason"):
                if key in catalog_product:
                    group[key] = catalog_product[key]
        assign_content_families(group["offers"])
        group["offers"].sort(key=lambda item: item["quality_score"], reverse=True)
        group["offers"] = group["offers"][: args.max_offers_per_model]
        group["normalized_brand"] = group["group_key"].split("|", 1)[0]
        group["normalized_model"] = group["group_key"].split("|", 1)[1]
        group["marketplaces"] = sorted({item.get("marketplace", "") for item in group["offers"]})
        group["sources_count"] = len(group["offers"])
        group["sources_by_marketplace"] = {market: sum(item.get("marketplace") == market for item in group["offers"]) for market in group["marketplaces"]}
        group["sources"] = group.pop("offers")
        directory = canonical_directory(group)
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write_json(directory / "group.json", group)
    try:
        canonical_folders = validate_unique_canonical_groups(args.group_key or "")
    except (RuntimeError, ValueError) as exc:
        print(f"Błąd walidacji grup: {exc}")
        return 1
    print(f"groups={len(groups)}")
    print(f"groups_updated={len(groups)}")
    print(f"duplicate_groups_resolved={duplicate_groups_resolved}")
    print(f"canonical_folders={canonical_folders}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
