# Zadanie 02 — P1: jakość danych, taksonomia, historia i źródła

**Sugerowany model:** GPT-5.6 Terra, reasoning High.

Rozpocznij dopiero po `Result: P0_COMPLETE`.

Pracuj offline. Nie używaj Firecrawl, OpenAI, Playwrighta ani zewnętrznej sieci. Nie rozpoczynaj P2 ani integracji producentów.

## Cel

Ujednolicić jakość danych, taksonomię benchmarku, historię runów oraz lifecycle źródeł.

## 1. Zweryfikuj P0

Uruchom testy P0. Nie kontynuuj, jeśli locki, timeout, cancel, recovery, atomowe zapisy lub kanoniczny stan produktu nie działają.

## 2. Deterministyczny quality gate

Dodaj lub napraw wspólny quality gate wykonywany przed zatwierdzeniem finalnego pola produktu.

Statusy evidence/wartości:

- `valid`
- `weak`
- `conflicting`
- `rejected`
- `unattributed_legacy`

Quality gate ma co najmniej odrzucać lub oznaczać:

- „brak informacji” jako wartość,
- parametr dotyczący innego modelu lub generacji,
- kolor błędnie użyty jako materiał ramy,
- ogólne „łatwe składanie” jako dowód składania jedną ręką,
- opcjonalne akcesoria jako elementy zestawu,
- marketingowe wnioski bez dokładnego fragmentu źródła,
- dane bez jednoznacznego powiązania z produktem.

Nie usuwaj odrzuconego evidence; zachowaj je w historii z powodem.

Dodaj migrację/revalidację offline z trybami:

- `--dry-run`
- `--apply`
- `--resume`
- `--product-slug`
- `--all`

Każda zmiana finalnego stanu musi mieć backup i zapis atomowy.

## 3. Taksonomia benchmarku

Wprowadź wersjonowaną taksonomię:

- `category`
- `subcategory`
- `benchmark_category`
- `taxonomy_version`
- `taxonomy_status=classified|review_required|unclassified`

Benchmark może porównywać wyłącznie produkty o:

- tej samej `benchmark_category`,
- tej samej `taxonomy_version`,
- statusie `classified`.

Nie stosuj wyjątków zaszytych pod ORFEO, NEBO, TRIG 3 ani inną konkretną markę.

## 4. Kanoniczna historia runów

Wprowadź jeden wersjonowany manifest runu, np. `RunManifestV1`:

- `output/runs/<run_id>/manifest.json`
- `output/runs/index.json`

Manifest zawiera co najmniej:

- run ID,
- product slug,
- immutable input context,
- selected source IDs,
- etapy i ich statusy,
- start/end,
- terminal status,
- error summary,
- ścieżki do logów i artefaktów,
- relację z poprzednim runem przy retry.

Globalna historia i historia produktu mają korzystać z tego samego modelu. Usuń lub odłącz mock history.

Retry i cancel muszą być rzeczywistymi akcjami backendu, nie timerami w UI.

## 5. Globalny katalog źródeł i relacje produkt–źródło

Rozdziel dwa kontrakty.

### SourceRecord

Globalna tożsamość realnego źródła niezależna od produktu.

Identity:

- marketplace: `marketplace + offer_id`,
- manufacturer: canonical URL lub stabilny identyfikator producenta,
- snapshot nie tworzy nowego source ID,
- wpis kolejki aktualizuje źródło, ale nie tworzy automatycznie relacji z produktem.

Globalny rekord przechowuje między innymi:

- source ID i typ,
- marketplace/offer ID lub canonical URL,
- fetch lifecycle,
- cleaning lifecycle,
- snapshot paths,
- content hash,
- metadata/hints,
- first/last seen.

Nie przechowuje jako kanonicznych pól relacji:

- product slug,
- group key,
- selected role,
- used in final product.

### ProductSourceLink

Jawna relacja jednego źródła z jednym produktem.

Unikalność:

`product_slug + source_id`

Przechowuje:

- selection status i run ID,
- assignment status,
- role,
- used/confirmed/conflicting/rejected counts,
- first/last linked,
- powód przypisania lub odrzucenia.

Wpis globalnej kolejki bez dowodu relacji nie może tworzyć linku.

## 6. Migracja source lifecycle

Dodaj bezpieczną migrację z:

- `--dry-run`
- `--apply`
- `--resume`
- `--product-slug`
- `--all`

Migracja:

- zachowuje legacy registry i backupy,
- deduplikuje według identity, nie według tytułu,
- nie promuje snapshotu do osobnego źródła,
- tworzy ProductSourceLink tylko na podstawie dowodu: run context, group data, final provenance albo jednoznaczne legacy assignment,
- nie uznaje braku linku za globalny status `unassigned`.

## 7. API i UI źródeł

`GET /api/products/{product_slug}/sources` ma działać wyłącznie na linkach danego produktu i łączyć je z globalnymi SourceRecord.

Nazwane liczniki:

- selected,
- fetched,
- failed,
- cleaned,
- assigned,
- unattached,
- used,
- rejected,
- duplicate,
- unavailable.

Nie używaj niejednoznacznego `sources_count`.

Dodaj osobny globalny endpoint administracyjny `GET /api/sources`, który nie jest normalnym widokiem produktu.

## 8. Kontrole referencyjne

Sprawdź offline co najmniej:

### CYBEX ORFEO

Oczekiwany lifecycle, jeżeli odpowiada aktualnym danym wejściowym:

- 10 selected,
- 8 fetched,
- 2 failed,
- 5 assigned,
- 3 fetched-but-unattached,
- brak duplikatów tych ofert.

Nie wymuszaj tych liczb, jeśli repozytorium nie zawiera odpowiadających danych. W takim przypadku zgłoś rozbieżność i pokaż dowód.

### Kinderkraft TRIG 3

Nie przypisuj ofert tylko dlatego, że ich tytuł zawiera markę/model. Zachowaj wyłącznie relacje z jednoznacznym dowodem.

## 9. Typecheck i offline gate

Dodaj lub rozbuduj:

`scripts/check_fieldnote.sh`

Ma działać bez sieci i wykonywać:

- backend tests,
- testy P0,
- testy quality gate,
- testy taksonomii,
- testy historii,
- testy source lifecycle,
- frontend typecheck,
- frontend tests, jeśli istnieją,
- frontend build.

## 10. Status

Zaktualizuj tylko:

`docs/audit/IMPLEMENTATION_STATUS.md`

Na końcu wypisz:

```text
p1_quality_gate
p1_taxonomy
p1_run_manifest
p1_real_retry_cancel
p1_source_catalog
p1_product_source_links
p1_product_source_api
p1_global_source_api
legacy_data_preserved
orfeo_counters
trig3_links
backend_tests
frontend_typecheck
frontend_tests
frontend_build
offline_gate
network_fetches=0
openai_calls=0
next_item=P2_PROVENANCE_UI_TESTS_ADAPTER_CONTRACT
Result: P1_COMPLETE
```

Nie oznaczaj sukcesu przy niespójnej migracji, błędnych linkach źródło–produkt lub nieprzechodzącym gate.
