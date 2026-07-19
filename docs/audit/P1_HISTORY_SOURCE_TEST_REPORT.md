# FIELDNOTE P1.7–P1.9: historia, lifecycle źródeł i bramka offline

## Zakres zakończony

Wdrożono wyłącznie P1.7, P1.8 i P1.9, pracując na istniejących lokalnych
plikach. Nie uruchamiano Allegro search, Firecrawl, Playwright ani OpenAI.

## Wyniki

- `run_manifests_legacy_found`: 16
- `run_manifests_migrated`: 16
- `run_duplicates_removed`: 0 rekordów dodatkowych w kanonicznej historii; 9 różnic legacy zapisano jako konflikty migracji
- `canonical_runs_count`: 16
- `products_with_history`: 7
- `retry_api_connected`: true
- `cancel_api_connected`: true
- `mock_runs_removed`: true
- `source_records_legacy_found`: 41
- `source_records_migrated`: 243
- `source_records_unassigned`: 212
- `source_records_rejected`: 0
- `source_records_duplicates`: 0
- `orfeo_selected_count`: 10
- `orfeo_fetched_count`: 8
- `orfeo_failed_count`: 2
- `source_counters_consistent`: true
- `typescript_errors_before`: 3
- `typescript_errors_after`: 0
- `frontend_tests_added`: 3
- `backend_tests_added`: 10
- `offline_test_gate_added`: true
- `all_tests_passed`: true
- `frontend_build`: passed
- `network_fetches`: 0
- `openai_calls`: 0

## Implementacja

Kanoniczne manifesty `RunManifestV1` są atomowo zapisywane w
`output/runs/<run_id>/manifest.json`. Każdy katalog runu zawiera również
kontekst, zapis wybranych źródeł, streszczenie wyniku oraz log, a
`output/runs/index.json` jest odbudowywany po zapisie. Adapter migracyjny
odczytuje nadal trzy historyczne lokalizacje bez usuwania ich plików.

`SourceRecordV1` jest przechowywany w `output/source_registry_v1.jsonl`.
Rozdziela wybór, pobranie, czyszczenie, przypisanie i użycie źródła. Dzięki
temu pobrana, lecz nieprzypisana oferta pozostaje widoczna i nie jest mylona
z ofertą odrzuconą. Stary registry pozostał bez zmian, z kopią legacy.

Ekran Uruchomienia korzysta z `GET /api/runs`; retry i anulowanie wywołują
rzeczywiste endpointy API. Historia produktu pobiera ten sam kanoniczny model
uruchomień. Endpoint źródeł korzysta z lifecycle V1 i udostępnia osobne
liczniki selected/fetched/failed/cleaned/assigned/unattached/used.

## Walidacja offline

Uruchomiono `scripts/check_fieldnote.sh`. Bramka wykonała:

- kompilację i importy Python,
- 10 testów kontraktów backendu standardowej biblioteki,
- istniejące testy P0 i P1,
- frontendowy typecheck bez `skipLibCheck`,
- 3 testy frontendu,
- build Vite.

## Pozostałe kwestie P1

- `pytest` nie jest zainstalowany w lokalnym venv, dlatego testy kontraktów są
  uruchamiane przez `unittest`; plik testowy pozostaje zgodny z odkrywaniem
  przez pytest po jego przyszłej instalacji.
- Rekordy bez jednoznacznego związku z grupą pozostają `unassigned` z jawnym
  powodem. Ich doprecyzowanie należy do późniejszej migracji provenance, nie
  do P1.

Result: P1_HISTORY_SOURCE_TEST_COMPLETE
