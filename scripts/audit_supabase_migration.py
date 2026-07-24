from __future__ import annotations
import json
from pathlib import Path
from typing import Any
def expected_lionelo_ids(root: Path | None = None) -> set[str]:
    directory = (root or Path(__file__).resolve().parents[1]) / "data" / "internal_specs"
    return {str(json.loads(path.read_text(encoding="utf-8")).get("product_id")) for path in directory.glob("lionelo__*.json")}
def audit(report: Any, expected_lionelo: set[str] | None = None) -> dict[str, Any]:
    lionelo_ids = set(getattr(report, "lionelo_ids", set()))
    expected = expected_lionelo if expected_lionelo is not None else expected_lionelo_ids()
    return {"status": "pass" if lionelo_ids == expected else "review", "lionelo_count": len(lionelo_ids), "rejected": report.rejected}
