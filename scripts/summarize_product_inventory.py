#!/usr/bin/env python3
"""Offline frequency summary used before classifying the Lionelo inventory."""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    print(f"products={len(rows)}")
    for column in ("source_tab", "type", "collection_l2", "collection_l3", "configuration"):
        print(f"\n[{column}]")
        for value, count in Counter((row.get(column) or "").strip() for row in rows).most_common():
            print(f"{count}\t{value or '(empty)'}")
    combinations = Counter(tuple((row.get(key) or "").strip() for key in ("source_tab", "type", "collection_l2", "collection_l3", "configuration")) for row in rows)
    print(f"\ncombinations={len(combinations)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
