from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ACCESSORY_KEYWORDS = {
    "materac",
    "adapter",
    "folia",
    "moskitiera",
    "torba",
    "wkładka",
    "wkladka",
    "koło",
    "kolo",
    "pałąk",
    "palak",
    "barierka",
    "organizer",
    "uchwyt",
    "część",
    "czesc",
    "części",
    "czesci",
}
GENERIC_QUERY_TOKENS = {"wozek", "wózek", "spacerowy", "spacerowka", "spacerówka", "dzieciecy", "dziecięcy"}
TOKEN_RE = re.compile(r"[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9]+")
PRICE_RE = re.compile(r"(\d[\d\s]*[,.]\d{2}|\d[\d\s]*)\s*zł", re.IGNORECASE)
MODEL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("NUBI 2", ("nubi", "2")),
    ("TRIG 3", ("trig", "3")),
    ("VESTO 2", ("vesto", "2")),
    ("SIESTA 2", ("siesta", "2")),
    ("MOOV 2", ("moov", "2")),
    ("NUBI", ("nubi",)),
    ("TIK", ("tik",)),
    ("TRIG", ("trig",)),
    ("APINO", ("apino",)),
    ("VESTO", ("vesto",)),
    ("NEBO", ("nebo",)),
    ("SIESTA", ("siesta",)),
    ("YOXI", ("yoxi",)),
    ("MOOV", ("moov",)),
    ("ESME", ("esme",)),
    ("NEA", ("nea",)),
    ("HELSI", ("helsi",)),
    ("MITZY", ("mitzy",)),
)


@dataclass(frozen=True)
class SearchQuery:
    raw: str
    brand: str
    model_tokens: tuple[str, ...]
    all_tokens: tuple[str, ...]


def normalize_text(value: str) -> str:
    return " ".join((value or "").lower().split())


def tokenize(value: str) -> list[str]:
    return TOKEN_RE.findall(normalize_text(value))


def parse_query(value: str) -> SearchQuery:
    tokens = [token for token in tokenize(value) if token not in GENERIC_QUERY_TOKENS]
    if not tokens:
        return SearchQuery(raw=value, brand="", model_tokens=(), all_tokens=())
    return SearchQuery(raw=value, brand=tokens[0], model_tokens=tuple(tokens[1:]), all_tokens=tuple(tokens))


def parse_price(value: str) -> float | None:
    match = PRICE_RE.search(value or "")
    if not match:
        return None
    return float(match.group(1).replace(" ", "").replace(",", "."))


def is_sponsored(value: object) -> bool:
    return str(value).lower() == "true"


def has_accessory_terms(row: dict[str, str]) -> list[str]:
    searchable = " ".join(row.get(field, "") for field in ("title", "image_alt_texts", "nearby_text")).lower()
    return sorted(keyword for keyword in ACCESSORY_KEYWORDS if keyword in searchable)


def detect_model(row: dict[str, str]) -> tuple[str, float]:
    """Detect a known market model without letting adjacent listing text override a title."""
    for field, confidence in (("title", 100.0), ("image_alt_texts", 80.0), ("nearby_text", 60.0)):
        tokens = _field_tokens(row, field)
        for model, required_tokens in MODEL_RULES:
            if set(required_tokens).issubset(tokens):
                return model, confidence
    return "", 0.0


def enrich_market_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for row in rows:
        result: dict[str, object] = dict(row)
        accessory_hits = has_accessory_terms(row)
        detected_model, model_score = detect_model(row)
        result["is_accessory"] = bool(accessory_hits)
        result["accessory_reason"] = ", ".join(accessory_hits)
        result["detected_model"] = "Accessory / part" if accessory_hits else detected_model
        result["match_score"] = model_score
        result["price_value"] = parse_price(row.get("price", ""))
        enriched.append(result)
    return enriched


def market_model_summary(rows: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        model = str(row.get("detected_model", ""))
        if model:
            grouped.setdefault(model, []).append(row)

    summary: list[dict[str, object]] = []
    for model, model_rows in grouped.items():
        prices = [float(row["price_value"]) for row in model_rows if row.get("price_value") is not None]
        summary.append(
            {
                "detected_model": model,
                "offers_count": len(model_rows),
                "min_price": min(prices) if prices else None,
                "max_price": max(prices) if prices else None,
                "avg_price": sum(prices) / len(prices) if prices else None,
                "sponsored_count": sum(is_sponsored(row.get("is_sponsored", "")) for row in model_rows),
                "rated_count": sum(bool(row.get("rating")) for row in model_rows),
            }
        )
    return sorted(summary, key=lambda item: (-int(item["offers_count"]), str(item["detected_model"])))


def browse_market_rows(
    rows: Iterable[dict[str, object]],
    *,
    model: str,
    hide_accessories: bool,
    show_sponsored: bool,
    min_price: float | None,
    max_price: float | None,
    sort_by: str,
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for row in rows:
        if model and row.get("detected_model") != model:
            continue
        if hide_accessories and bool(row.get("is_accessory")):
            continue
        if not show_sponsored and is_sponsored(row.get("is_sponsored", "")):
            continue
        price = row.get("price_value")
        if min_price is not None and (price is None or float(price) < min_price):
            continue
        if max_price is not None and (price is None or float(price) > max_price):
            continue
        filtered.append(row)

    if sort_by == "price_asc":
        return sorted(filtered, key=lambda row: (row.get("price_value") is None, row.get("price_value") or 0.0))
    if sort_by == "price_desc":
        return sorted(filtered, key=lambda row: (row.get("price_value") is not None, row.get("price_value") or 0.0), reverse=True)
    if sort_by == "rating":
        return sorted(filtered, key=lambda row: float(str(row.get("rating") or "0").replace(",", ".")), reverse=True)
    if sort_by == "sponsored":
        return sorted(filtered, key=lambda row: is_sponsored(row.get("is_sponsored", "")), reverse=True)
    return sorted(filtered, key=lambda row: float(row.get("match_score") or 0.0), reverse=True)


def _field_tokens(row: dict[str, str], field: str) -> set[str]:
    return set(tokenize(row.get(field, "")))


def score_offer(row: dict[str, str], query: SearchQuery) -> tuple[float, str]:
    if not query.all_tokens:
        return 0.0, "empty_query"

    title_tokens = _field_tokens(row, "title")
    alt_tokens = _field_tokens(row, "image_alt_texts")
    nearby_tokens = _field_tokens(row, "nearby_text")
    url_tokens = _field_tokens(row, "normalized_url")
    score = 0.0
    reasons: list[str] = []

    if query.brand and query.brand in title_tokens:
        score += 28
        reasons.append("brand_in_title(+28)")
    elif query.brand and query.brand in alt_tokens | nearby_tokens | url_tokens:
        score += 12
        reasons.append("brand_in_supporting_text(+12)")

    if query.model_tokens:
        text_model_tokens = [token for token in query.model_tokens if not token.isdigit()]
        numeric_model_tokens = [token for token in query.model_tokens if token.isdigit()]
        supporting_tokens = alt_tokens | nearby_tokens | url_tokens
        text_matches_anywhere = [token for token in text_model_tokens if token in title_tokens | supporting_tokens]

        # A version digit is meaningful only together with a model name, e.g. NUBI 2.
        if text_model_tokens and numeric_model_tokens and not text_matches_anywhere:
            reasons.append("missing_text_model_token; numeric_token_alone_is_weak")
            accessory_hits = has_accessory_terms(row)
            if accessory_hits:
                reasons.append(f"accessory_or_part:{'/'.join(accessory_hits)}(-55)")
            return min(score, 20.0), "; ".join(reasons)

        title_matches = [token for token in query.model_tokens if token in title_tokens]
        if title_matches:
            score += min(36, 12 * len(title_matches))
            reasons.append(f"model_tokens_in_title:{'/'.join(title_matches)}(+{min(36, 12 * len(title_matches))})")
        if len(title_matches) == len(query.model_tokens):
            score += 24
            reasons.append("all_model_tokens_in_title(+24)")
        else:
            support_matches = [token for token in query.model_tokens if token in supporting_tokens]
            if support_matches:
                score += min(15, 5 * len(support_matches))
                reasons.append(f"model_tokens_in_supporting_text:{'/'.join(support_matches)}(+{min(15, 5 * len(support_matches))})")
    elif query.brand in title_tokens:
        score += 20
        reasons.append("brand_only_query(+20)")

    accessory_hits = has_accessory_terms(row)
    if accessory_hits:
        score -= 55
        reasons.append(f"accessory_or_part:{'/'.join(accessory_hits)}(-55)")

    return max(0.0, min(score, 100.0)), "; ".join(reasons) or "no_matching_tokens"


def load_market_offers(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def search_offers(
    rows: Iterable[dict[str, str]],
    query_text: str,
    *,
    min_score: float = 45,
    show_weak_matches: bool = False,
    hide_accessories: bool = True,
    only_with_price: bool = False,
    sponsored_filter: str = "all",
) -> list[dict[str, object]]:
    query = parse_query(query_text)
    results: list[dict[str, object]] = []
    for row in rows:
        score, reason = score_offer(row, query)
        if not show_weak_matches and score < min_score:
            continue
        if hide_accessories and has_accessory_terms(row):
            continue
        if only_with_price and parse_price(row.get("price", "")) is None:
            continue
        sponsored = is_sponsored(row.get("is_sponsored", ""))
        if sponsored_filter == "sponsored" and not sponsored:
            continue
        if sponsored_filter == "not_sponsored" and sponsored:
            continue
        result: dict[str, object] = dict(row)
        result["match_score"] = round(score, 1)
        result["match_reason"] = reason
        result["price_value"] = parse_price(row.get("price", ""))
        results.append(result)
    return sorted(results, key=lambda item: float(item["match_score"]), reverse=True)
