# Market Intelligence + Benchmark Pipeline

## Cel

System tworzy benchmark modeli wózków na podstawie ofert Allegro. Pipeline nie scrapuje Allegro bezpośrednio: targeted search i pojedyncze karty są pobierane przez Firecrawl, a następnie lokalnie oczyszczane, rejestrowane, grupowane i interpretowane.

Streamlit jest lokalnym interfejsem do przeglądu katalogu modeli, evidence, coverage, porównań, researchu i retry błędnych pobrań.

## Aktualna architektura

1. `fetch_targeted_model_offers.py` znajduje oferty Allegro dla marki i modelu.
2. `run_model_research_pipeline.py --apply` dołącza nowe oferty do kolejki i uruchamia dalsze etapy.
3. `fetch_firecrawl_offer_pages.py` pobiera pojedyncze karty do `input/firecrawl_offer_pages/`.
4. `clean_offer_pages_technical.py` buduje oczyszczone sekcje oferty.
5. `build_source_registry.py` tworzy rejestr źródeł.
6. `build_model_groups.py` tworzy kanoniczne grupy po marce i modelu.
7. `extract_model_facts_cascade.py` analizuje tylko pola nadal otwarte, niepewne lub konfliktowe.
8. `build_model_benchmark.py` zapisuje benchmark modelowy.
9. `report_model_coverage.py` oblicza coverage i rekomenduje dodatkowy research.

`output/market_offers.csv` pozostaje historycznym outputem parsera listingów. Nie jest głównym źródłem aktualnego katalogu Streamlit ani kanonicznego pipeline’u benchmarkowego.

## Główne artefakty danych

| Artefakt | Rola |
| --- | --- |
| `output/firecrawl_offer_queue.csv` | kolejka pojedynczych kart ofert oraz statusy pobrań i retry. |
| `input/firecrawl_offer_pages/<offer_id>/` | surowe odpowiedzi Firecrawl oraz oczyszczone artefakty jednej oferty. |
| `output/source_registry.jsonl` | aktualny rejestr źródeł; implementacja używa JSON Lines, nie `output/source_registry.json`. |
| `output/model_groups/<brand_slug>__<model_slug>/` | kanoniczny folder grupy, `group.json`, opcjonalny `model_state.json` i prompty. |
| `output/model_benchmark.csv` | jeden wiersz na model z zagregowanymi wartościami benchmarku. |
| `output/model_coverage.csv` | coverage, braki, priorytet oraz rekomendacja dalszego researchu. |

`output/research_runs/` nie jest obecnie generowany przez pipeline. Ostatni log procesu jest przechowywany w stanie sesji Streamlit, a nie jako trwały artefakt pipeline’u.

## Kontrakty danych

### `group_key`

Stabilny identyfikator grupy: `normalized_brand|normalized_model`, np. `kinderkraft|trig 3`. Aplikacja pokazuje jeden rekord na unikalny `group_key` i traktuje duplikaty jako błąd danych.

### `source_id`

Globalny identyfikator źródła obejmujący marketplace, np. `allegro:16566160258`. Jest zachowywany w evidence oraz w source registry.

### `offer_id`

Identyfikator pojedynczej oferty Allegro. Służy do deduplikacji kolejki, katalogu kart Firecrawl oraz ofert pochodzących z linków trackingowych i produktowych.

### Kanoniczny folder grupy

Każda grupa powinna mieć folder:

```text
output/model_groups/<brand_slug>__<model_slug>/
```

Przykład: `output/model_groups/kinderkraft__trig-3/`. Starsze duplikaty są przenoszone do `output/model_groups_legacy_backup/` przez builder grup.

### `accepted` i `already_known`

W targeted search `accepted` oznacza wyłącznie poprawne dopasowanie marki i modelu. `already_known` jest niezależne: oferta może być jednocześnie `accepted=true` i `already_known=true`, ale nie trafi wtedy do `new_offers.csv`.

### Retry Firecrawl

Kolejka zachowuje `retry_count`, `last_attempt_at` i `last_error_at`. Retry obejmuje wyłącznie rekordy `error` z licznikiem mniejszym niż 3. Rekordy `fetched` nie są ponownie pobierane.

### `pipeline_status`

- `preview` - tylko targeted search, bez zmian w benchmarku.
- `success` - brak błędów żądanych pobrań.
- `partial` - jednocześnie pobrane i błędne oferty.
- `failed` - wszystkie żądane pobrania nieudane lub błąd globalny.

## Tryby uruchomienia

- Preview: pipeline bez `--apply`; uruchamia tylko targeted search.
- Pełny research: `--apply`; wykonuje etapy od searchu do coverage.
- Resume: `--resume`; korzysta z zapisanego listingu i istniejącego stanu.
- Bez AI: `--skip-ai`; pomija tylko AI cascade.
- Retry: `--apply --retry-errors`; nie uruchamia targeted search ani merge i ponawia istniejące błędy kolejki.
- Fixture: `--fixture-scenario` i `--fixture-root`; całkowicie izolowany, bez API, sieci i zapisu do produkcyjnego `output/`.

## Granice aktualnego scope’u

- aktywny adapter marketplace: Allegro;
- aktywny schemat benchmarku: wózki;
- Firecrawl API jest wdrożone dla kart ofert;
- AI cascade jest wdrożone, ale może być pominięte przez `--skip-ai`;
- Streamlit jest lokalnym narzędziem operacyjnym, nie panelem produkcyjnym;
- nie ma bezpośredniego scrapera Allegro ani Playwrighta w kanonicznym pipeline.

## Dokumenty powiązane

- [README](../README.md) - szybki start i najważniejsze komendy.
- [OPERATIONS.md](OPERATIONS.md) - procedury uruchomienia, retry, demo i diagnostyka.
- [MULTI_MARKETPLACE_ARCHITECTURE.md](MULTI_MARKETPLACE_ARCHITECTURE.md) - kierunek rozbudowy adapterów marketplace.
