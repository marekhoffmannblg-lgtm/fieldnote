from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from scoring import score_listing


CASES = [
    {
        "brand": "Kinderkraft",
        "model": "NUBI 2",
        "category": "wózki spacerowe",
        "title": "Kinderkraft NUBI 2 wózek spacerowy",
        "expected_status": "accepted",
        "max_status": None,
        "forbidden_reasons": [],
    },
    {
        "brand": "Kinderkraft",
        "model": "NUBI 2",
        "category": "wózki spacerowe",
        "title": "Kinderkraft NUBI wózek spacerowy",
        "expected_status": None,
        "max_status": "review",
        "forbidden_reasons": ["all_significant_model_tokens_present(+20)"],
    },
    {
        "brand": "Lionelo",
        "model": "Annet Plus",
        "category": "wózki spacerowe",
        "title": "Lionelo Annet Plus wózek spacerowy",
        "expected_status": "accepted",
        "max_status": None,
        "forbidden_reasons": [],
    },
    {
        "brand": "Lionelo",
        "model": "Annet Plus",
        "category": "wózki spacerowe",
        "title": "Lionelo Annet wózek spacerowy",
        "expected_status": None,
        "max_status": "review",
        "forbidden_reasons": [],
    },
    {
        "brand": "Kinderkraft",
        "model": "NUBI 2",
        "category": "wózki spacerowe",
        "title": "Kinderkraft NUBI 2 folia przeciwdeszczowa",
        "expected_status": "rejected",
        "max_status": None,
        "forbidden_reasons": [],
    },
]

STATUS_ORDER = {"rejected": 0, "review": 1, "accepted": 2}


def main() -> int:
    has_failures = False

    for case in CASES:
        result = score_listing(
            brand=case["brand"],
            model=case["model"],
            category=case["category"],
            title=case["title"],
        )

        print(f"Product: {case['brand']} {case['model']}")
        print(f"Title:   {case['title']}")
        print(f"Score:   {result.score}")
        print(f"Status:  {result.status}")
        print(f"Reason:  {'; '.join(result.reasons)}")

        if case["expected_status"] and result.status != case["expected_status"]:
            print(f"FAIL: expected status {case['expected_status']}, got {result.status}")
            has_failures = True

        if case["max_status"] and STATUS_ORDER[result.status] > STATUS_ORDER[case["max_status"]]:
            print(f"FAIL: expected max status {case['max_status']}, got {result.status}")
            has_failures = True

        for forbidden_reason in case["forbidden_reasons"]:
            if forbidden_reason in result.reasons:
                print(f"FAIL: forbidden reason present: {forbidden_reason}")
                has_failures = True

        print()

    print("Result: FAIL" if has_failures else "Result: OK")
    return 1 if has_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
