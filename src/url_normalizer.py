from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse


TRACKING_PARAMS = {
    "bi_s",
    "bi_m",
    "bi_c",
    "bi_t",
    "placement",
    "sig",
    "emission_id",
    "emission_unit_id",
    "ts",
}

REDIRECT_KEYS = ("redirect", "redirect_url", "url")
OFFER_ID_RE = re.compile(r"-(\d{6,})($|[/?#])")
DIRECT_OFFER_ID_RE = re.compile(r"/oferta/(\d{6,})($|[/?#])")
DIRECT_PRODUCT_ID_RE = re.compile(r"[?&]offerId=(\d{6,})($|[&#])")


@dataclass(frozen=True)
class NormalizedUrlResult:
    original_url: str
    normalized_url: str
    offer_id: str


def detect_allegro_url_type(url: str) -> str:
    parsed = urlparse(url)
    if "/oferta/" in parsed.path:
        return "offer"
    if "/produkt/" in parsed.path:
        return "product"
    return "other"


def _extract_offer_id_from_pairs(pairs: Iterable[tuple[str, str]]) -> str:
    for key, value in pairs:
        lowered = key.lower()
        if lowered == "offerid" and value.isdigit():
            return value
        if lowered == "rep" and value.isdigit():
            return value
        if lowered == "emission_element_id" and value.isdigit() and len(value) >= 6:
            return value
    return ""


def extract_offer_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    offer_id = _extract_offer_id_from_pairs(pairs)
    if offer_id:
        return offer_id

    direct_offer_match = DIRECT_OFFER_ID_RE.search(parsed.path)
    if direct_offer_match:
        return direct_offer_match.group(1)

    path_match = OFFER_ID_RE.search(parsed.path)
    if path_match:
        return path_match.group(1)

    product_match = DIRECT_PRODUCT_ID_RE.search(f"?{parsed.query}")
    if product_match:
        return product_match.group(1)

    return ""


def _decode_possible_base64_url(value: str) -> str:
    decoded = unquote(value)
    if decoded.startswith(("http://", "https://")):
        return decoded

    try:
        padding = "=" * (-len(decoded) % 4)
        decoded_bytes = base64.urlsafe_b64decode(decoded + padding)
        decoded_text = decoded_bytes.decode("utf-8").strip()
    except Exception:
        return decoded

    if decoded_text.startswith(("http://", "https://")):
        return decoded_text
    return decoded


def _unwrap_redirect(url: str, base_url: str = "") -> str:
    resolved = urljoin(base_url, url) if base_url else url
    seen: set[str] = set()

    while resolved and resolved not in seen:
        seen.add(resolved)
        parsed = urlparse(resolved)
        if not (parsed.path.startswith("/events/clicks") or parsed.path.startswith("/dss-proxy/clicks")):
            return resolved

        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        redirect_value = ""
        for key, value in pairs:
            if key in REDIRECT_KEYS and value:
                redirect_value = value
                break

        if not redirect_value:
            return resolved

        resolved = _decode_possible_base64_url(redirect_value)

    return resolved


def normalize_allegro_url(url: str, base_url: str = "") -> NormalizedUrlResult:
    if not url.strip():
        return NormalizedUrlResult(original_url=url, normalized_url="", offer_id="")

    resolved_url = _unwrap_redirect(url.strip(), base_url=base_url)
    parsed = urlparse(urljoin(base_url, resolved_url) if base_url else resolved_url)

    filtered_pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key in TRACKING_PARAMS:
            continue
        filtered_pairs.append((key, value))

    offer_id = extract_offer_id_from_url(urlunparse(parsed._replace(query=urlencode(filtered_pairs))))
    query = urlencode(filtered_pairs)
    normalized_url = urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc,
            parsed.path,
            "",
            query,
            "",
        )
    )

    return NormalizedUrlResult(
        original_url=url,
        normalized_url=normalized_url,
        offer_id=offer_id,
    )
