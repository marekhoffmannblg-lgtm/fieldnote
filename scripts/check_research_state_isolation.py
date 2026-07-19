"""Regression checks for local preview identity and Butterfly 2 classification.

The test only uses already cached listings and a small in-memory HTML fixture.
It never calls Firecrawl or OpenAI.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fetch_targeted_model_offers import extract_offers


def load_api_module():
    spec = importlib.util.spec_from_file_location("fieldnote_api", ROOT / "fieldnote-api" / "app.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Nie można wczytać fieldnote-api/app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    failures: list[str] = []
    fixture = """
    <article><a href="https://allegro.pl/oferta/bugaboo-butterfly-2-123456789">Bugaboo Butterfly 2 wózek spacerowy</a></article>
    <article><a href="https://allegro.pl/oferta/bugaboo-butterfly-123456790">Bugaboo Butterfly wózek spacerowy</a></article>
    <article><a href="https://allegro.pl/oferta/torba-do-bugaboo-butterfly-2-123456791">Torba do Bugaboo Butterfly 2</a></article>
    <article><a href="https://allegro.pl/oferta/moskitiera-do-bugaboo-butterfly-2-123456792">Moskitiera do Butterfly 2 Bugaboo</a></article>
    <article><a href="https://allegro.pl/oferta/palak-butterfly-2-123456793">Pałąk do Bugaboo Butterfly 2</a></article>
    <article><a href="https://allegro.pl/oferta/adapter-butterfly-2-123456794">Adapter do Bugaboo Butterfly 2</a></article>
    <article><a href="https://allegro.pl/oferta/spiworek-butterfly-2-123456795">Śpiworek do Bugaboo Butterfly 2</a></article>
    """
    accepted, rejected = extract_offers(fixture, "Bugaboo", "Butterfly 2")
    by_id = {item["offer_id"]: item for item in [*accepted, *rejected]}
    if len(accepted) != 1 or not by_id["123456789"].get("accepted"):
        failures.append("butterfly_2_exact_not_accepted")
    if by_id["123456790"].get("match_status") != "uncertain" or by_id["123456790"].get("rejection_reason") != "previous_generation":
        failures.append("butterfly_without_2_not_uncertain")
    for offer_id in ("123456791", "123456792", "123456793", "123456794", "123456795"):
        item = by_id.get(offer_id, {})
        if item.get("product_type") != "accessory" or item.get("match_status") != "rejected":
            failures.append("accessory_misclassified")
            break

    api = load_api_module()
    api.PREVIEW_CACHE.clear()
    orfeo = api.research_preview(api.PreviewRequest(brand="CYBEX", model="ORFEO"))
    butterfly = api.research_preview(
        api.PreviewRequest(brand="Bugaboo", model="Butterfly 2", previous_product_slug="cybex__orfeo")
    )
    butterfly_cached = api.research_preview(
        api.PreviewRequest(brand="Bugaboo", model="Butterfly 2", previous_product_slug="cybex__orfeo")
    )
    if orfeo["preview_cache_key"] == butterfly["preview_cache_key"]:
        failures.append("preview_cache_key_not_isolated")
    if butterfly.get("requested_brand") != "Bugaboo" or butterfly.get("requested_model") != "Butterfly 2":
        failures.append("preview_response_identity_mismatch")
    if butterfly.get("preview_diagnostics", {}).get("previous_product_slug") != "cybex__orfeo":
        failures.append("previous_product_diagnostic_missing")
    if not butterfly_cached.get("preview_diagnostics", {}).get("cache_hit"):
        failures.append("preview_cache_hit_missing")
    if "orfeo" in str(butterfly.get("offers", [])).lower():
        failures.append("orfeo_state_leaked_into_butterfly_preview")

    app_text = (ROOT / "fieldnote-frontend" / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
    for marker in ("clearProductResearchState", '"/research"', "Otrzymano wynik dla innego produktu", "preview_cache_key"):
        if marker not in app_text:
            failures.append("frontend_preview_guard_missing")
            break
    if "Akcesoria kompatybilne z ORFEO" in app_text:
        failures.append("hardcoded_orfeo_ui_text")

    if failures:
        print("FAIL")
        print("\n".join(sorted(set(failures))))
        return 1
    print(f"butterfly_exact_count={len(accepted)}")
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
