#!/usr/bin/env python3
"""Build or generate one controlled ProductProfileV1."""
from __future__ import annotations
import argparse
from pathlib import Path
from product_profile import build_profile_input, generate_from_transmission_payload, generate_or_load_profile

try:
    from dotenv import load_dotenv
except ImportError:  # dry-run remains usable in a minimal Python environment
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-slug", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-openai", action="store_true")
    parser.add_argument("--no-openai", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-images", type=int, default=8)
    parser.add_argument("--payload-path", type=Path)
    parser.add_argument("--owned-lock-run-id", default="")
    parser.add_argument("--expected-payload-hash", default="")
    args = parser.parse_args()
    if load_dotenv is not None:
        load_dotenv(ROOT / "fieldnote-api" / ".env", override=False)
    if args.dry_run:
        data = build_profile_input(args.product_slug, max_images=args.max_images)
        print(f"product_slug={args.product_slug}")
        print(f"canonical_input_hash={data['canonical_input_hash']}")
        for key, value in data["input_summary"].items(): print(f"{key}={value}")
        print("openai_requests_attempted=0")
        return 0
    if args.payload_path:
        if args.dry_run or args.no_openai or not args.expected_payload_hash:
            raise SystemExit("Tryb transmisyjny wymaga --allow-openai i --expected-payload-hash, bez --dry-run/--no-openai.")
        profile, cached, warnings = generate_from_transmission_payload(args.payload_path, expected_hash=args.expected_payload_hash, allow_openai=args.allow_openai)
        print(f"validation_warnings={len(warnings)}")
    else:
        profile, cached = generate_or_load_profile(args.product_slug, allow_openai=args.allow_openai, no_openai=args.no_openai, force=args.force, max_images=args.max_images, owned_lock_run_id=args.owned_lock_run_id or None)
    print(f"profile_status={profile['profile_status']}")
    print(f"cached={cached}")
    print(f"openai_requests_attempted={profile['generation'].get('openai_requests_attempted_this_run', 0)}")
    return 0 if profile["profile_status"] == "generated" and (cached or profile["generation"].get("profile_quality_valid")) else 2

if __name__ == "__main__": raise SystemExit(main())
