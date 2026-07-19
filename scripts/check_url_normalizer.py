from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from url_normalizer import normalize_allegro_url


TEST_URL = (
    "https://allegro.pl/dss-proxy/clicks"
    "?redirect=aHR0cHM6Ly9hbGxlZ3JvLnBsL29mZXJ0YS9raW5kZXJrcmFmdC10ZXN0LTEyMzQ1Njc4OQ"
)
EXPECTED_URL = "https://allegro.pl/oferta/kinderkraft-test-123456789"
EXPECTED_OFFER_ID = "123456789"


def main() -> int:
    result = normalize_allegro_url(TEST_URL)

    print(f"normalized_url: {result.normalized_url}")
    print(f"offer_id: {result.offer_id}")

    if result.normalized_url != EXPECTED_URL:
        print(f"FAIL: expected normalized_url {EXPECTED_URL}")
        return 1

    if result.offer_id != EXPECTED_OFFER_ID:
        print(f"FAIL: expected offer_id {EXPECTED_OFFER_ID}")
        return 1

    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
