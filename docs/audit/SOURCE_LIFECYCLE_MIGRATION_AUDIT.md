# Audit migracji SourceRecordV1

## Wynik

- `records_total`: 243
- `records_by_origin`: legacy registry 40, queue entry 202, manufacturer source 1; pozostałe origin types: 0
- `semantic_duplicates_found`: 0
- `records_to_merge`: 0
- `records_to_remove_as_non_sources`: 0
- `records_safely_assignable`: 78
- `records_correctly_unassigned`: 134
- `records_with_missing_identity`: 0
- `orfeo_unique_sources`: 10
- `trig3_unique_sources`: 13
- `recommended_canonical_count`: 243

## Dlaczego 41 wpisów legacy dało 243 rekordy

Migracja P1 zbudowała sumę po `source_id`: 41 wpisów `output/source_registry.jsonl` oraz 242 unikalne wpisy kolejki Firecrawl. Czterdzieści wpisów legacy miało ten sam `allegro:<offer_id>` co kolejka, a jeden dodatkowy wpis to strona producenta Kinderkraft NEBO. Wynik to `41 + 242 - 40 = 243`. To nie jest duplikacja tych samych ofert: każdy rekord ma inny `offer_id` i canonical URL.

## Pochodzenie

Dla każdego rekordu zapisana jest pełna diagnostyka `origin_type`, `origin_path`, `origin_record_id`, reguła migracji, pewność tożsamości i powód utworzenia w [SOURCE_LIFECYCLE_MIGRATION_AUDIT.json](SOURCE_LIFECYCLE_MIGRATION_AUDIT.json). Rekordy mają trzy rzeczywiste origins: `legacy_registry` (40 ofert), `queue_entry` (202) oraz `manufacturer_source` (1). Listingi, manifesty runów i snapshoty nie utworzyły żadnego dodatkowego rekordu.

## Duplikaty semantyczne

Sprawdzono `offer_id`, canonical URL, content hash, raw snapshot path oraz parę `marketplace + offer_id`. Nie znaleziono żadnej grupy duplikatów. Nie ma więc bezpiecznych merge’ów ani rekordów do usunięcia wyłącznie na podstawie obecnych danych.

## Nieprzypisane rekordy

- wszystkich: 212
- z marką: 212
- z modelem: 128
- z `product_slug`: 73
- z `group_key`: 121
- ze snapshotem: 10
- z `offer_id`: 212
- pochodzących z manifestów runów: 0
- technicznych śladów kolejki pending bez snapshotu: 199
- kandydatów jednoznacznie zgodnych z istniejącą grupą marka+model: 78
- poprawnie pozostających unassigned: 134
- niebędących SourceRecord w ogóle: 0

`unassigned` nie znaczy `rejected`: 199 z tych rekordów jest kolejką oczekującą, 10 ma snapshot pobrany bez przypisania, a 3 ma nieudane pobranie. Wszystkie zachowują prawidłową tożsamość oferty.

## Kontrole modeli

- ORFEO: 10 unikalnych ofert, dokładnie 8 fetched, 2 failed, 5 assigned i 3 fetched-but-unattached. Nie występuje powielenie tych dziesięciu ofert.
- TRIG 3: 13 unikalnych ofert, w tym 5 fetched/assigned, 7 queued/unassigned i 1 failed/unassigned.

## Wniosek

`migration_bug_found: true` oznacza błąd zakresu i semantyki migracji, a nie błąd deduplikacji identity. Migracja utworzyła globalne SourceRecordy również dla ofert z kolejki bez relacji do produktu. Docelowa reguła identity pozostaje:

- marketplace offer: `marketplace + offer_id`;
- manufacturer: canonical URL lub stabilny identyfikator producenta;
- snapshot: artefakt istniejącego źródła;
- wybór runu: aktualizacja lifecycle istniejącego źródła;
- queue entry: aktualizacja istniejącego źródła, nie nowy rekord gdy tożsamość już istnieje.

Zalecana naprawa wymaga oddzielenia globalnego rejestru źródeł od relacji źródło–produkt. Nie została wykonana w tym audycie.

Result: SOURCE_LIFECYCLE_AUDIT_COMPLETE
