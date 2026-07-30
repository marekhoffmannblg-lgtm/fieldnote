from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from firecrawl_client import FirecrawlClient, FirecrawlError


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from firecrawl_offer_export import is_firecrawl_ready_url
from prepare_firecrawl_offer_queue import QUEUE_COLUMNS


QUEUE_PATH = ROOT_DIR / "output" / "firecrawl_offer_queue.csv"
OFFER_PAGES_ROOT = ROOT_DIR / "input" / "firecrawl_offer_pages"
MAX_RETRIES = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pobiera pojedyncze karty aukcji Allegro z kolejki Firecrawl.")
    parser.add_argument("--limit", type=int, default=5, help="Maksymalna liczba rekordów pending do pobrania (domyślnie: 5).")
    parser.add_argument("--force", action="store_true", help="Pozwala nadpisać istniejące pliki w katalogu oferty.")
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help=f"Ponawia rekordy error z retry_count mniejszym niż {MAX_RETRIES}.",
    )
    parser.add_argument("--no-visuals", action="store_true", help="Nie żądaj screenshotu i listy mediów podczas nowego fetchu.")
    parser.add_argument("--visuals-from-cache", action="store_true", help="Zbuduj kontekst wizualny wyłącznie z istniejącego HTML.")
    parser.add_argument("--refresh-visuals", action="store_true", help="Przebuduj lokalny kontekst wizualny mimo cache HTML.")
    parser.add_argument(
        "--offer-id",
        action="append",
        default=[],
        help="Opcjonalny identyfikator oferty do pobrania lub ponowienia; można podać wielokrotnie.",
    )
    return parser.parse_args()


def read_queue(queue_path: Path = QUEUE_PATH) -> list[dict[str, str]]:
    with queue_path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_queue(rows: list[dict[str, str]], queue_path: Path = QUEUE_PATH) -> None:
    with queue_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in QUEUE_COLUMNS})


def require_api_key() -> str:
    api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Brak FIRECRAWL_API_KEY. Ustaw zmienną środowiskową przed uruchomieniem fetchera.")
    return api_key


def scrape_offer(url: str, api_key: str, *, capture_visuals: bool = True) -> dict[str, object]:
    formats = ["markdown", "html", "rawHtml", "links"]
    if capture_visuals:
        formats.extend(["images", "screenshot"])
    response = FirecrawlClient(api_key=api_key, timeout=120, max_retries=2).scrape(url, formats=formats)
    return {"success": response.ok, "data": response.data, "usage": asdict(response.usage), "request_id": response.request_id}


def _links_text(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(str(item) for item in value.values())
    return str(value or "")


def save_response(output_dir: Path, response: dict[str, object]) -> None:
    data = response.get("data", response)
    if not isinstance(data, dict):
        raise ValueError("Nieprawidłowa odpowiedź Firecrawl: brak obiektu data.")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "markdown.md").write_text(str(data.get("markdown", "")), encoding="utf-8")
    (output_dir / "html.html").write_text(str(data.get("html", "")), encoding="utf-8")
    raw_html = data.get("rawHtml", data.get("raw_html", ""))
    if raw_html:
        (output_dir / "raw_html.html").write_text(str(raw_html), encoding="utf-8")
    (output_dir / "links.txt").write_text(_links_text(data.get("links", "")), encoding="utf-8")
    (output_dir / "metadata.json").write_text(json.dumps(data.get("metadata", {}), ensure_ascii=False, indent=2), encoding="utf-8")
    if "images" in data:
        (output_dir / "firecrawl_images.json").write_text(json.dumps(data.get("images"), ensure_ascii=False, indent=2), encoding="utf-8")
    screenshot = data.get("screenshot")
    if isinstance(screenshot, str) and screenshot.startswith("data:image/"):
        header, encoded = screenshot.split(",", 1)
        extension = ".webp" if "webp" in header else ".png"
        visual_dir = output_dir / "visual"
        visual_dir.mkdir(parents=True, exist_ok=True)
        try:
            (visual_dir / f"full_page{extension}").write_bytes(base64.b64decode(encoded))
        except ValueError:
            pass
    (output_dir / "raw_response.json").write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class FetchRunResult:
    fetch_status: str = "success"
    offers_requested: int = 0
    offers_fetched: int = 0
    offers_failed: int = 0
    offers_skipped: int = 0
    global_error: str = ""


def fetch_status_for(result: FetchRunResult) -> str:
    if result.global_error:
        return "failed"
    if result.offers_failed == 0:
        return "success"
    if result.offers_fetched > 0:
        return "partial"
    return "failed"


def print_result(result: FetchRunResult) -> None:
    for key, value in asdict(result).items():
        if key != "global_error":
            print(f"{key}={value}")
    if result.global_error:
        print(f"error={result.global_error}")


def requested_indices(
    rows: list[dict[str, str]],
    limit: int,
    offer_ids: set[str] | None,
    retry_errors: bool,
) -> list[int]:
    statuses = {"error"} if retry_errors else {"pending"}
    candidates = [
        index
        for index, row in enumerate(rows)
        if row.get("status", "") in statuses and (not offer_ids or row.get("offer_id", "") in offer_ids)
    ]
    return candidates[:limit]


def retry_count(row: dict[str, str]) -> int:
    try:
        return max(0, int(str(row.get("retry_count", "0") or "0")))
    except ValueError:
        return 0


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_error(row: dict[str, str], message: str) -> None:
    row["status"] = "error"
    row["error_message"] = message
    row["last_error_at"] = timestamp()


def fetch_pending_rows(
    limit: int,
    force: bool,
    queue_path: Path = QUEUE_PATH,
    offer_ids: set[str] | None = None,
    retry_errors: bool = False,
    root_dir: Path = ROOT_DIR,
    offer_pages_root: Path = OFFER_PAGES_ROOT,
    capture_visuals: bool = True,
    visuals_from_cache: bool = False,
    refresh_visuals: bool = False,
) -> FetchRunResult:
    if limit < 1:
        raise ValueError("--limit musi być większy od zera.")
    rows = read_queue(queue_path)
    indices = requested_indices(rows, limit, offer_ids, retry_errors)
    result = FetchRunResult(offers_requested=len(indices))
    work_indices: list[int] = []
    for index in indices:
        row = rows[index]
        if retry_errors and retry_count(row) >= MAX_RETRIES:
            result.offers_skipped += 1
            continue
        work_indices.append(index)
    if visuals_from_cache:
        from visual_snapshots import extract_visual_context
        for index in indices:
            row = rows[index]
            try:
                extract_visual_context(f"allegro:{row.get('offer_id', '')}", refresh=refresh_visuals)
            except (OSError, ValueError, FileNotFoundError):
                pass
        result.fetch_status = fetch_status_for(result)
        return result
    if not work_indices:
        result.fetch_status = fetch_status_for(result)
        return result
    try:
        api_key = require_api_key()
    except RuntimeError as exc:
        result.global_error = str(exc)
        result.fetch_status = fetch_status_for(result)
        return result

    for index in work_indices:
        row = rows[index]
        row.setdefault("retry_count", "0")
        row["last_attempt_at"] = timestamp()
        if retry_errors:
            row["retry_count"] = str(retry_count(row) + 1)

        output_dir = (root_dir / row["output_dir"]).resolve()
        try:
            output_dir.relative_to(offer_pages_root.resolve())
        except ValueError:
            record_error(row, "Nieprawidłowy output_dir: ścieżka musi należeć do input/firecrawl_offer_pages/.")
            result.offers_failed += 1
            continue
        if not is_firecrawl_ready_url(row.get("normalized_url", "")):
            record_error(row, "Nieprawidłowy normalized_url: oczekiwano linku allegro.pl /oferta/ lub /produkt/.")
            result.offers_failed += 1
            continue
        if output_dir.exists() and any(output_dir.iterdir()) and not force and not retry_errors:
            record_error(row, "Katalog oferty już zawiera pliki. Użyj --force, aby nadpisać.")
            result.offers_failed += 1
            continue

        try:
            response = scrape_offer(row["normalized_url"], api_key, capture_visuals=capture_visuals)
            if response.get("success") is False:
                raise ValueError(str(response.get("error", "Firecrawl zwrócił success=false.")))
            save_response(output_dir, response)
            if capture_visuals:
                try:
                    from visual_snapshots import extract_visual_context
                    extract_visual_context(f"allegro:{row.get('offer_id', '')}", directory=output_dir, provider="firecrawl")
                except (OSError, ValueError, FileNotFoundError):
                    # Visual capture is intentionally non-blocking for the
                    # text pipeline; the response itself remains fetched.
                    pass
            row["status"] = "fetched"
            row["fetched_at"] = timestamp()
            row["error_message"] = ""
            result.offers_fetched += 1
        except (FirecrawlError, HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
            record_error(row, str(exc))
            result.offers_failed += 1

    write_queue(rows, queue_path)
    result.fetch_status = fetch_status_for(result)
    return result


def main() -> int:
    args = parse_args()
    if not QUEUE_PATH.exists():
        print("Brak output/firecrawl_offer_queue.csv. Najpierw przygotuj kolejkę.")
        print("fetch_status=failed")
        print("offers_requested=0")
        print("offers_fetched=0")
        print("offers_failed=0")
        print("offers_skipped=0")
        return 1
    try:
        result = fetch_pending_rows(
            args.limit,
            args.force,
            offer_ids=set(args.offer_id) or None,
            retry_errors=args.retry_errors,
            capture_visuals=not args.no_visuals,
            visuals_from_cache=args.visuals_from_cache,
            refresh_visuals=args.refresh_visuals,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"Błąd: {exc}")
        print("fetch_status=failed")
        print("offers_requested=0")
        print("offers_fetched=0")
        print("offers_failed=0")
        print("offers_skipped=0")
        return 1
    print_result(result)
    return 0 if result.fetch_status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
