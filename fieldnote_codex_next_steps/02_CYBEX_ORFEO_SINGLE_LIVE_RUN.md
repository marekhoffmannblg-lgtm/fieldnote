# 02 — CYBEX ORFEO: pojedynczy live run

Wykonaj ten etap wyłącznie po `KINDERKRAFT_NEBO_LIVE_PASS`.

Uruchom rzeczywisty, kontrolowany live run dla:

- brand: `CYBEX`
- model: `ORFEO`
- maksymalnie jedno oficjalne źródło

## 1. Uruchomienie

```bash
python scripts/check_manufacturer_pipeline_live.py \
  --allow-network \
  --allow-openai \
  --brand CYBEX \
  --model ORFEO \
  --max-sources 1 \
  --force-refresh
```

## 2. Limity

Dla całego etapu:

- Firecrawl: maksymalnie 1 request attempted,
- OpenAI: maksymalnie 1 request attempted,
- oficjalne URL-e: maksymalnie 1,
- brak ponownego live fetchu NEBO,
- brak Allegro search,
- brak innych modeli.

OpenAI uruchamiaj tylko dla nierozstrzygniętych kandydatów. Brak potrzeby użycia OpenAI nie jest błędem, jeżeli przyczyna jest jawnie zapisana.

## 3. Wymagane kontrole

1. Oficjalna domena CYBEX.
2. Bezpośrednia karta ORFEO, nie kategoria ani inny wariant modelu.
3. Exact model match.
4. Firecrawl fetch i stabilny final URL.
5. Raw i clean snapshot.
6. Usunięcie rekomendowanych modeli oraz treści nawigacyjnej.
7. `NormalizedDocument`.
8. Fakty deterministyczne.
9. Opcjonalna ekstrakcja OpenAI.
10. Quality gate i evidence.
11. Wspólny `SourceRecordV2` oraz `ProductSourceLinkV1`.
12. Brak osobnego pipeline'u finalnego produktu.
13. Brak podwójnego niezależnego potwierdzenia, jeżeli opis Allegro kopiuje treść producenta.

## 4. Ochrona istniejących danych ORFEO

Po live runie zachowaj istniejące liczniki marketplace:

- selected=10,
- fetched=8,
- failed=2,
- assigned=5,
- unattached=3.

Źródło producenta ma być raportowane osobno i nie może zmienić historycznych liczników ofert Allegro.

Cena, sprzedawca i dostępność nie mogą zostać nadpisane danymi producenta.

## 5. Obsługa błędu

Tak jak w etapie NEBO:

- podaj dokładny stage/code/reason,
- napraw tylko warstwę awarii,
- maksymalnie jedna poprawka i jeden retry,
- po drugim FAIL zatrzymaj pakiet.

## 6. Testy po sukcesie

Uruchom:

```bash
scripts/check_fieldnote.sh
```

Sprawdź:

- `GET /api/products/cybex__orfeo`
- `GET /api/products/cybex__orfeo/sources`
- `GET /api/products/cybex__orfeo/evidence`
- `GET /api/products/cybex__orfeo/benchmark`

## 7. Status

Zaktualizuj wyłącznie `docs/audit/IMPLEMENTATION_STATUS.md`.

Na końcu wypisz:

```text
cybex_orfeo_live=PASS/FAIL
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
orfeo_marketplace_selected=10
orfeo_marketplace_fetched=8
orfeo_marketplace_failed=2
orfeo_marketplace_assigned=5
orfeo_marketplace_unattached=3
offline_tests_passed=true/false
next_item=MANUFACTURER_PRODUCTION_HARDENING
Result: CYBEX_ORFEO_LIVE_PASS lub CYBEX_ORFEO_LIVE_FAIL
```
