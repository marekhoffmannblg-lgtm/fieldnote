from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
FETCHER_PATH = ROOT_DIR / "scripts" / "fetch_firecrawl_offer_pages.py"


def main() -> int:
    source = FETCHER_PATH.read_text(encoding="utf-8") if FETCHER_PATH.exists() else ""
    failures: list[str] = []
    required_fragments = (
        "FIRECRAWL_API_KEY",
        "--limit",
        "firecrawl_offer_queue.csv",
        "firecrawl_offer_pages",
    )
    if not FETCHER_PATH.exists():
        failures.append("fetcher_missing")
    for fragment in required_fragments:
        if fragment not in source:
            failures.append(f"missing_fragment:{fragment}")

    environment = dict(os.environ)
    environment.pop("FIRECRAWL_API_KEY", None)
    result = subprocess.run(
        [sys.executable, str(FETCHER_PATH), "--limit", "1"],
        cwd=ROOT_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 or "Brak FIRECRAWL_API_KEY" not in result.stdout:
        failures.append("missing_api_key_does_not_stop")

    if failures:
        print("FAIL")
        for failure in failures:
            print(failure)
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
