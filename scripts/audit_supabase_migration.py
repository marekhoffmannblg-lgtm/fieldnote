from __future__ import annotations
from typing import Any
def audit(report: Any, expected_lionelo: int = 34) -> dict[str, Any]:
    lionelo_ids = set(getattr(report, "lionelo_ids", set()))
    return {"status": "pass" if len(lionelo_ids) == expected_lionelo else "review", "lionelo_count": len(lionelo_ids), "rejected": report.rejected}
