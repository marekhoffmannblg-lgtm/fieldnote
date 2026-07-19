# 01 — Kinderkraft NEBO: pojedynczy live run

Wykonaj pierwszy rzeczywisty, kontrolowany live run pipeline'u producenta dla:

- brand: `Kinderkraft`
- model: `NEBO`
- maksymalnie jedno oficjalne źródło

Nie przebudowuj architektury i nie twórz nowego runnera.

## 1. Uruchomienie

Użyj kanonicznego runnera:

```bash
python scripts/check_manufacturer_pipeline_live.py \
  --allow-network \
  --allow-openai \
  --brand Kinderkraft \
  --model NEBO \
  --max-sources 1 \
  --force-refresh
```

Jeżeli projekt wymaga aktywacji istniejącego `.venv`, użyj go. Nie twórz nowego środowiska.

## 2. Limity kosztowe

Dla całego etapu:

- Firecrawl: maksymalnie 1 request attempted,
- OpenAI: maksymalnie 1 request attempted,
- oficjalne URL-e: maksymalnie 1,
- brak Allegro search,
- brak dodatkowych produktów.

OpenAI uruchamiaj wyłącznie dla nierozstrzygniętych kandydatów po ekstrakcji deterministycznej. Jeżeli nie ma kandydatów wymagających modelu, `openai_requests_attempted=0` jest poprawne, ale zapisz `openai_skipped_reason=no_unresolved_candidates`.

## 3. Wymagany przebieg

Zweryfikuj kolejno:

1. discovery oficjalnej karty produktu,
2. domenę `kinderkraft.pl` lub inną skonfigurowaną oficjalną domenę Kinderkraft,
3. exact model match dla `NEBO`,
4. Firecrawl fetch,
5. raw snapshot,
6. manufacturer cleaner,
7. clean snapshot,
8. `NormalizedDocument`,
9. fakty deterministyczne,
10. opcjonalną ekstrakcję OpenAI,
11. quality gate,
12. `EvidenceItemV1`,
13. `SourceRecordV2`,
14. `ProductSourceLinkV1`,
15. agregację per pole,
16. widok API produktu i źródeł.

## 4. Reguły jakości

- Inny model na stronie blokuje ekstrakcję.
- Rekomendowane produkty nie mogą wejść do clean snapshotu.
- Akcesoria opcjonalne nie mogą wejść do zestawu standardowego.
- Producent ma authority dla danych technicznych, nie dla ceny, sprzedawcy i dostępności.
- Każdy zaakceptowany evidence musi mieć `source_id` i excerpt.
- Raw i clean snapshot są artefaktami tego samego źródła.
- Nie twórz nowego benchmarku ani osobnego finalnego produktu dla producenta.

## 5. Obsługa błędu

Jeżeli run zakończy się błędem:

1. Podaj `failure_stage`, `failure_code`, `failure_reason`.
2. Napraw tylko bieżącą warstwę: runner, provider, discovery, cleaner, normalizer, extraction, quality gate albo write.
3. Nie zmieniaj kontraktów P0–P2.
4. Uruchom testy offline dotyczące poprawionej warstwy.
5. Powtórz live run tylko raz.
6. Po drugiej nieudanej próbie zatrzymaj cały pakiet.

## 6. Testy po sukcesie

Uruchom:

```bash
scripts/check_fieldnote.sh
```

Sprawdź:

- `GET /api/products/kinderkraft__nebo`
- `GET /api/products/kinderkraft__nebo/sources`
- `GET /api/products/kinderkraft__nebo/evidence`

## 7. Status

Zaktualizuj wyłącznie `docs/audit/IMPLEMENTATION_STATUS.md`.

Na końcu wypisz:

```text
kinderkraft_nebo_live=PASS/FAIL
failure_stage=
failure_code=
failure_reason=
firecrawl_requests_attempted=
firecrawl_requests_succeeded=
openai_requests_attempted=
openai_requests_succeeded=
openai_skipped_reason=
manufacturer_source_id=
product_source_link_created=true/false
raw_snapshot_saved=true/false
clean_snapshot_saved=true/false
identity_match=true/false
deterministic_facts=
ai_facts=
quality_rejections=
offline_tests_passed=true/false
next_item=CYBEX_ORFEO_SINGLE_LIVE_RUN
Result: KINDERKRAFT_NEBO_LIVE_PASS lub KINDERKRAFT_NEBO_LIVE_FAIL
```
