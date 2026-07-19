from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


TOKEN_RE = re.compile(r"[a-z0-9]+")
ACCESSORY_KEYWORDS = (
    "adapter",
    "folia",
    "folia przeciwdeszczowa",
    "moskitiera",
    "spiworek",
    "spiwor",
    "wkadka",
    "wkladka",
    "torba",
    "barierka",
    "palak",
    "pałąk",
    "pokrowiec",
    "daszek",
    "budka",
    "opona",
    "kolo",
    "koło",
    "czesc",
    "część",
    "czesci",
    "części",
)
CATEGORY_KEYWORDS = {
    "wózki spacerowe": ("wozek", "spacerowy", "spacerowka", "buggy"),
}
IGNORED_MODEL_TOKENS = {
    "black",
    "grey",
    "gray",
    "beige",
    "green",
    "blue",
    "pink",
    "red",
    "silver",
    "gold",
    "sand",
}


@dataclass(frozen=True)
class ScoreResult:
    score: int
    reasons: list[str]
    status: str


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_value = re.sub(r"\s+", " ", ascii_value)
    return ascii_value.strip()


def tokenize(value: str) -> list[str]:
    return TOKEN_RE.findall(normalize_text(value))


def get_significant_model_tokens(model: str) -> list[str]:
    return [
        token
        for token in tokenize(model)
        if (token.isdigit() or len(token) > 1) and token not in IGNORED_MODEL_TOKENS
    ]


def classify_score(score: int) -> str:
    if score >= 80:
        return "accepted"
    if score >= 50:
        return "review"
    return "rejected"


def _contains_keyword(text: str, keywords: tuple[str, ...] | list[str]) -> list[str]:
    return [keyword for keyword in keywords if normalize_text(keyword) in text]


def _category_mismatch(expected_category: str, normalized_title: str) -> bool:
    expected = normalize_text(expected_category)
    keywords = CATEGORY_KEYWORDS.get(expected_category) or CATEGORY_KEYWORDS.get(expected)
    if not keywords:
        return False
    return not any(keyword in normalized_title for keyword in keywords)


def score_listing(*, brand: str, model: str, category: str, title: str) -> ScoreResult:
    normalized_title = normalize_text(title)
    normalized_brand = normalize_text(brand)
    normalized_model = normalize_text(model)
    model_tokens = get_significant_model_tokens(model)

    score = 0
    reasons: list[str] = []

    if normalized_brand and normalized_brand in normalized_title:
        score += 40
        reasons.append("brand_in_title(+40)")

    if normalized_model and normalized_model in normalized_title:
        score += 40
        reasons.append("exact_model_in_title(+40)")

    if model_tokens and all(token in normalized_title for token in model_tokens):
        score += 20
        reasons.append("all_significant_model_tokens_present(+20)")

    accessory_hits = _contains_keyword(normalized_title, ACCESSORY_KEYWORDS)
    if accessory_hits:
        score -= 50
        reasons.append(f"accessory_or_part:{'/'.join(sorted(set(accessory_hits)))}(-50)")

    matched_model_tokens = [token for token in model_tokens if token in normalized_title]
    if normalized_brand in normalized_title and matched_model_tokens and len(matched_model_tokens) < len(model_tokens):
        score -= 40
        reasons.append("partial_model_match_possible_other_variant(-40)")

    if _category_mismatch(category, normalized_title):
        score -= 30
        reasons.append("category_mismatch(-30)")

    score = max(0, min(score, 100))
    status = classify_score(score)
    if not reasons:
        reasons.append("no_strong_signals(0)")

    return ScoreResult(score=score, reasons=reasons, status=status)
