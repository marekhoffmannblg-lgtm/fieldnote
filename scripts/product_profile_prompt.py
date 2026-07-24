"""Versioned ProductProfileV1 prompt and strict Responses API schema."""
from __future__ import annotations

from typing import Any


PRODUCT_PROFILE_PROMPT_VERSION = "6"
PRODUCT_PROFILE_MODEL = "gpt-4.1-nano"
PRODUCT_PROFILE_SCHEMA_VERSION = "1"

SYSTEM_PROMPT = """Analizujesz materiały dotyczące jednego konkretnego produktu.

Utwórz indywidualny profil produktu wyłącznie na podstawie przekazanych źródeł,
dowodów, opisów marketplace, materiałów producenta i kontekstu wizualnego.

Tożsamość produktu jest wiążąca: zachowaj przekazane `brand`, `model`,
`product_name`, `product_type`, `benchmark_category` i `taxonomy_category_id`.
Nie zmieniaj typu produktu ani nie opisuj go jako produktu z innej kategorii.

Najpierw odkryj tematy rzeczywiście obecne i eksponowane w materiale.
Nie korzystaj ze stałej listy cech kategorii i nie wymuszaj tych samych tematów
dla każdego produktu.

Zasady:

1. Brak informacji nie oznacza braku właściwości ani wady produktu.
2. Nie uzupełniaj materiału wiedzą ogólną.
3. Oddziel potwierdzone fakty od twierdzeń producenta, narracji sprzedawców
   i sposobu prezentacji wizualnej.
4. Konkretne wartości liczbowe i techniczne wymagają supporting evidence ID.
5. Kopie jednej content family nie są niezależnymi potwierdzeniami.
6. Obserwacja wizualna opisuje sposób prezentowania produktu, a nie potwierdza
   komfortu, jakości, trwałości, bezpieczeństwa ani sprawności technicznej.
7. Jeżeli nie przekazano lokalnego obrazu, możesz analizować wyłącznie heading,
   caption, alt i nearby text. Nie twierdź, że widziałeś grafikę.
8. Nie twórz sekcji tylko dlatego, że dane pole istnieje w schemacie kategorii.
9. Pomijaj tematy niewspierane przez materiał.
10. `important_unknowns` nie może być listą wszystkich pustych pól.
11. Każdy temat i każda obserwacja muszą wskazywać istniejące supporting IDs.
12. Pisz konkretnie o analizowanym produkcie.
13. Przejrzyj wszystkie przekazane evidence i visual blocks, grupuj powtarzające
    się motywy oraz preferuj tematy wspierane przez więcej niż jeden element.
    Nie zastępuj kilku wyraźnych motywów jednym ogólnym tematem.
    14. Nie twórz `factual_highlights`: system buduje je deterministycznie z
    kanonicznych faktów po Twojej odpowiedzi. Nie zmieniaj wartości faktów ani
    nie dopisuj skutków, ocen lub związków przyczynowych.
15. Gdy `visual_access=text_context_only`, nie pisz „na zdjęciu”, „widać”,
    „wizualizacja pokazuje” ani „materiały wizualne przedstawiają”. Opisuj tylko
    nagłówki, captiony, alt i tekstowy kontekst bloków.
16. Narrative summary musi mieć 120-220 słów; celuj w 150-180 i policz słowa
    przed zwróceniem JSON.
17. Nie używaj sekcji unknowns, conflicts ani rejected_context_not_for_claims
    do twierdzeń o funkcjach produktu.

Wynik musi zawierać:

- niepuste `one_sentence_summary`,
- niepuste `narrative_summary`,
- przynajmniej jeden element w: `discovered_themes`,
  `marketplace_narrative` albo `visual_positioning`.

Nie zwracaj pustego profilu.
Gdy materiał nie wystarcza, zwróć jawny błąd semantyczny zamiast pustego sukcesu.

Zwróć wyłącznie obiekt zgodny ze schema odpowiedzi Product Profile.
Pisz po polsku."""


def product_profile_response_schema(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the provider DTO schema from IDs available in this exact input."""
    input_data = input_data or {}

    def allowed_ids(key: str) -> list[str]:
        identity_key = {
            "evidence": "evidence_id",
            "visual_blocks": "visual_block_id",
            "media": "media_id",
            "sources": "source_id",
        }[key]
        return list(dict.fromkeys(
            str(item.get(identity_key, ""))
            for item in input_data.get(key, [])
            if isinstance(item, dict) and str(item.get(identity_key, ""))
        ))

    def id_array(ids: list[str]) -> dict[str, Any]:
        if not ids:
            return {"type": "array", "items": {"type": "string"}, "maxItems": 0}
        return {"type": "array", "items": {"type": "string", "enum": ids}}

    string_array = {"type": "array", "items": {"type": "string"}}
    evidence_ids = allowed_ids("evidence")
    visual_block_ids = allowed_ids("visual_blocks")
    media_ids = allowed_ids("media")
    source_ids = allowed_ids("sources")
    theme = {
        "type": "object", "additionalProperties": False,
        "required": ["theme_id", "title", "summary", "basis_types", "supporting_evidence_ids", "supporting_visual_block_ids", "supporting_media_ids", "confidence"],
        "properties": {"theme_id": {"type": "string", "minLength": 1}, "title": {"type": "string", "minLength": 1}, "summary": {"type": "string", "minLength": 1}, "basis_types": string_array, "supporting_evidence_ids": id_array(evidence_ids), "supporting_visual_block_ids": id_array(visual_block_ids), "supporting_media_ids": id_array(media_ids), "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
    }
    marketplace = {"type": "object", "additionalProperties": False, "required": ["observation", "supporting_evidence_ids", "confidence"], "properties": {"observation": {"type": "string", "minLength": 1}, "supporting_evidence_ids": id_array(evidence_ids), "confidence": {"type": "string", "enum": ["high", "medium", "low"]}}}
    visual = {"type": "object", "additionalProperties": False, "required": ["observation", "basis", "visual_access", "supporting_visual_block_ids", "supporting_media_ids", "confidence", "is_factual_product_claim"], "properties": {"observation": {"type": "string", "minLength": 1}, "basis": {"type": "string", "enum": ["explicit_image_text", "caption", "visual_scene", "repetition", "mixed", "text_context_only"]}, "visual_access": {"type": "string", "enum": ["image_seen", "text_context_only"]}, "supporting_visual_block_ids": id_array(visual_block_ids), "supporting_media_ids": id_array(media_ids), "confidence": {"type": "string", "enum": ["high", "medium", "low"]}, "is_factual_product_claim": {"type": "boolean", "const": False}}}
    conflict = {"type": "object", "additionalProperties": False, "required": ["summary", "field_names", "supporting_evidence_ids"], "properties": {"summary": {"type": "string", "minLength": 1}, "field_names": string_array, "supporting_evidence_ids": id_array(evidence_ids)}}
    unknown = {"type": "object", "additionalProperties": False, "required": ["summary", "reason", "related_source_ids"], "properties": {"summary": {"type": "string", "minLength": 1}, "reason": {"type": "string", "minLength": 1}, "related_source_ids": id_array(source_ids)}}
    return {"type": "object", "additionalProperties": False, "required": ["one_sentence_summary", "narrative_summary", "discovered_themes", "marketplace_narrative", "visual_positioning", "important_conflicts", "important_unknowns"], "properties": {"one_sentence_summary": {"type": "string", "minLength": 1, "maxLength": 280}, "narrative_summary": {"type": "string", "minLength": 1050, "maxLength": 1500}, "discovered_themes": {"type": "array", "maxItems": 6, "items": theme}, "marketplace_narrative": {"type": "array", "items": marketplace}, "visual_positioning": {"type": "array", "items": visual}, "important_conflicts": {"type": "array", "maxItems": 3, "items": conflict}, "important_unknowns": {"type": "array", "maxItems": 3, "items": unknown}}}
