from __future__ import annotations
from typing import Any
def audit(report: Any, expected_lionelo: int) -> dict[str, Any]:
    return {"status": "pass" if report.products >= expected_lionelo and not any(x["kind"] == "evidence" for x in report.rejected) else "review", "products": report.products, "rejected": report.rejected}
