# Implementation Status

## Completed

### Stabilność i dane

- COMPLETE: P0.1–P0.4 — koordynator runów, blokady per produkt i globalne,
  timeout, anulowanie, recovery, atomowe zapisy oraz kanoniczny status produktu.
- COMPLETE: P1.5 — quality gate i rewalidacja finalnych stanów.
- COMPLETE: P1.6 — taksonomia benchmarku.
- COMPLETE: P1.7 — kanoniczna historia uruchomień.
- COMPLETE: P1.8 — globalny `SourceRecordV2` i jawny `ProductSourceLinkV1`.
- COMPLETE: P1.9 — typecheck i offline test gate.
- COMPLETE: P2.10 — `EvidenceItemV1`, provenance, `unattributed_legacy`,
  `invalid_reference`, content families i deterministyczna agregacja.
- COMPLETE: P2.11 — nullable metryki produktów, rozdzielenie coverage od jakości
  dowodów oraz nazwane liczniki lifecycle źródeł.

### Interfejs i kontrakty

- Znormalizowano publiczne modele `ProductV1`, `ProductMetricsV1`,
  `EvidenceItemV1`, `SourceRecordV2`, `ProductSourceLinkV1`,
  `SourceContributionV1`, `RunManifestV1` i `BenchmarkV1`.
- Dodano wersjonowane i paginowane odczyty: `/api/products`,
  `/api/products/{slug}`, `/api/products/{slug}/evidence`, `/api/sources`,
  `/api/products/{slug}/sources` oraz `/api/runs`.
- Frontend korzysta z jednego klienta `src/api/client.ts` oraz wspólnych typów
  `src/api/contracts.ts`; routing przeniesiono do `src/routes/navigation.ts`.
- Wyłączono z produkcyjnej nawigacji legacy mock Integracji z fikcyjnymi
  kluczami i statystykami. Pomoc nie pokazuje fikcyjnego kanału wsparcia.
- Naprawiono stabilną nawigację: desktopowy sidebar nie ma mechanizmu zwijania,
  a na wąskich ekranach widoczna pozostaje kontrolka drawer.
- Dodano favicon FIELDNOTE.

### Uruchamianie, testy i adaptery

- Domyślny `scripts/start_fieldnote_local.sh` uruchamia backend bez
  `--reload`; `scripts/start_fieldnote_local.sh dev` jest jedynym trybem
  autoreloadu.
- Skrypt zatrzymuje wyłącznie procesy, których PID, komenda i katalog roboczy
  potwierdzają przynależność do FIELDNOTE. Obcy proces na porcie blokuje start,
  a nie jest zabijany.
- Dodano limit logów i read-only `scripts/report_repo_artifacts.sh`.
- Rozszerzono `.gitignore` o lokalne sekrety, środowiska, buildy, logi i artefakty.
- Bramka testowa jawnie uruchamia testy jednostkowe, integracyjne, P0/P1/P2,
  fixture E2E, frontend typecheck, testy oraz build.
- Dodano offline-first kontrakt `SourceAdapter` oraz adaptery Allegro,
  manufacturer i fixtures. Adaptery nie zapisują benchmarku, registry ani
  `model_state` i w testach korzystają wyłącznie z lokalnych snapshotów.

## Wyniki danych

- `provenance_records_migrated=69`
- `unattributed_legacy_count=10`
- `invalid_source_references=2`
- `content_families_count=10`
- ORFEO pozostaje rozliczone jako `selected=10`, `fetched=8`, `failed=2`,
  `attached=5`, `unattached=3`.
- Produkt bez analizy, np. APINO, zwraca `coverage=null` i
  `missing_fields_count=null`, więc UI nie pokazuje fałszywego „Braki: 0”.

## Partial

- P4 modularizacja została rozpoczęta ewolucyjnie: istnieją wydzielone
  repositories, services, router helper, modele API, klient i moduł routingu.
  `fieldnote-api/app.py` i `fieldnote-frontend/src/app/App.tsx` nadal zawierają
  część historycznych widoków i endpointów; dalsze rozdzielanie stron należy
  robić małymi zmianami przy zachowaniu bieżących kontraktów.
- Pełne evidence jest dostępne przez lazy endpoint API, lecz istniejące
  statyczne snapshoty produktu nadal zawierają krótkie excerpty dla
  kompatybilności offline.

## Blocked

Brak blokera dla lokalnego MVP i pracy offline. Testy nie wymagają
Firecrawl, OpenAI, Playwrighta ani sieci.

## Deferred Expansion

- Następny marketplace poza Allegro: wymaga konkretnego adaptera produkcyjnego
  i lokalnych fixtures tego źródła.
- Amazon: nie jest gotowy; wymaga adaptera, paginacji, limitów, retry/backoff,
  obsługi wariantów i ograniczeń wielkości odpowiedzi.
- Automatyczne odświeżanie w tle: odroczone do trwałej kolejki.
- Tryb wieloużytkownikowy i wdrożenie poza localhost: odroczone do czasu
  autoryzacji, bazy danych, izolacji danych, secret managera, storage i
  observability.

## Testy i Smoke Testy

Ostatnia pełna bramka `scripts/check_fieldnote.sh`: OK.

- Backend unit: `22/22` OK.
- Backend integration: `4/4` OK.
- Fixture E2E: `5/5` OK.
- Frontend typecheck: OK.
- Frontend tests: `5/5` OK.
- Frontend build: OK.

Lokalny smoke test po restarcie bez autoreloadu: OK.

- `GET /api/health`
- `GET /api/products`
- `GET /api/products/cybex__orfeo`
- `GET /api/products/cybex__orfeo/sources`
- `GET /api/products/cybex__orfeo/history`
- `GET /api/products/cybex__orfeo/benchmark`
- `GET /api/runs`
- `GET /api/sources`
- preview `Kinderkraft NEBO` z lokalnego cached listingu
- odczyt nieprzeanalizowanego produktu `Kinderkraft APINO`

## Readiness nowych źródeł

- `manufacturer_sources_ready=true` — manufacturer adapter działa na zapisanym
  snapshotcie Kinderkraft NEBO.
- `next_marketplace_ready=false` — kontrakt adaptera istnieje, lecz nie ma
  jeszcze drugiego produkcyjnego adaptera marketplace.
- `amazon_ready=false`
- `automatic_refresh_ready=false`
- `multi_user_ready=false`
- `deployment_ready=false`

## Pozostały dług techniczny

1. Stopniowo wydzielić pozostałe strony z `App.tsx` i endpointy z `app.py`.
2. Dodać produkcyjny adapter kolejnego marketplace’u wraz z fixture E2E.
3. Dopiero potem rozważyć automatyczne odświeżanie, wieloużytkownikowość i
   wdrożenie poza localhost.

## FINAL REPAIR CLOSURE

### Verified complete

- P0: koordynator runów, niezmienny kontekst, blokady per produkt i globalne,
  timeout, anulowanie, recovery, atomowe zapisy oraz kanoniczny stan produktu.
- P1: deterministic quality gate, wersjonowana taksonomia, `RunManifestV1`,
  lifecycle globalnych źródeł i jawne `ProductSourceLinkV1`.
- P2: `EvidenceItemV1`, provenance, content families, niezależne potwierdzenia,
  nullable metryki, wkład źródła, kontrakty API, typed client, lazy evidence,
  paginacja i fixture E2E.
- Adaptery działają offline przez wspólny kontrakt wejściowy. Nie zapisują
  bezpośrednio benchmarku ani końcowego stanu produktu.

### Verified partial

- Modularizacja backendu i frontendu jest celowo ewolucyjna. Kontrakty oraz
  wydzielone moduły są używane, ale historyczne pliki `app.py` i `App.tsx`
  nadal wymagają dalszego stopniowego dzielenia.
- Pełne cytaty evidence są ładowane lazy z API; statyczne snapshoty zachowują
  skrócone excerpty dla pracy offline.

### Critical failures

Brak. Pełna bramka offline przeszła, a lokalne endpointy wymagane przez MVP
odpowiadają poprawnie.

### Non-blocking debt

- Dalsze wydzielanie endpointów i widoków z plików historycznych.
- Kolejny produkcyjny adapter marketplace oraz jego fixtures.
- Automatyczne odświeżanie w tle, wieloużytkownikowość i wdrożenie poza
  localhost pozostają poza zakresem lokalnego MVP.

### Test gate i smoke tests

- `scripts/check_fieldnote.sh`: PASS, bez Firecrawl, OpenAI ani requestów
  zewnętrznych.
- Backend: `22/22` testów jednostkowych oraz `4/4` integracyjnych.
- Fixture E2E: `5/5`; frontend: typecheck, `5/5` testów i build: PASS.
- Lokalny start bez autoreloadu: backend i frontend healthy na
  `127.0.0.1:8000` oraz `127.0.0.1:5173`.
- Zweryfikowano lokalnie endpointy zdrowia, produktów, źródeł, historii,
  benchmarku, runów i globalnych źródeł. ORFEO: `selected=10`, `fetched=8`,
  `failed=2`, `assigned=5`, `unattached=3`; APINO zachowuje metryki `null`.

### Manufacturer integration readiness

Pipeline jest gotowy na integrację źródeł producenta przez wspólny kontrakt
adaptera i fixture manufacturer. Produkcyjny fetch stron producentów nie został
jeszcze uruchomiony w tym etapie.

## Manufacturer Sources Same Pipeline

- `ManufacturerAdapter` jest adapterem wejściowym wspólnego kontraktu
  `SourceAdapter`; zachowuje lifecycle `SourceRecord` i `ProductSourceLink`,
  a nie tworzy odrębnego benchmarku ani stanu produktu.
- Dodano offline manufacturer cleaner i `NormalizedDocument`: identity wymaga
  dokładnego modelu w oczyszczonej treści, więc strona innego modelu blokuje
  ekstrakcję przed quality gate.
- Deterministyczne fakty (waga, udźwig, wymiary, identyfikatory JSON-LD) są
  tylko kandydatami wejściowymi do istniejącego quality/evidence/merge.
- Fixture test potwierdza odcięcie rekomendacji, blokadę mismatchu i rozdział
  opcjonalnych akcesoriów od standardowego zestawu.
- Test live nie został wykonany: `firecrawl_requests=0`, `openai_requests=0`.
  Produkcyjny fetch wymaga jawnych flag `--allow-network` oraz
  `--allow-openai` w kolejnym kontrolowanym uruchomieniu.

## MANUFACTURER PIPELINE CLOSURE

### Verified architecture

- Producent i Allegro używają wspólnego kontraktu `SourceAdapter`, lifecycle
  globalnego źródła oraz relacji `ProductSourceLink`.
- Cleaner i normalizacja producenta kończą się na `NormalizedDocument`.
  Dalej dane przechodzą przez wspólne quality gate, `EvidenceItemV1`, agregację
  per pole, metryki, benchmark i UI.
- Adapter producenta nie ma osobnego zapisu finalnego produktu ani benchmarku.
- Identity mismatch blokuje fakty przed ekstrakcją; `source_id` pozostaje
  stabilne, a raw i clean snapshoty są artefaktami tego samego źródła.

### Offline results

- Fixture Kinderkraft NEBO: PASS.
- Fixture CYBEX ORFEO: PASS.
- Pełna bramka `scripts/check_fieldnote.sh`: PASS offline.
- Lokalne preview NEBO zwraca jedno dopasowane oficjalne źródło
  `kinderkraft.pl`; źródła produktu NEBO raportują `manufacturer_count=1`.
- Produkt bez wymaganej karty producenta nadal zwraca poprawny widok źródeł.

### Live results i koszty

- Kinderkraft live: `not_executed`.
- CYBEX live: `not_executed`.
- `firecrawl_requests=0`, `openai_requests=0`.
- Live jest możliwy tylko w osobnym, kontrolowanym uruchomieniu z jawnymi
  flagami zgody, limitem źródeł oraz cache/resume.

### Supported domains i modele

- Oficjalne domeny kontrolowane przez adapter: Kinderkraft i CYBEX.
- Fixture modele: Kinderkraft NEBO oraz CYBEX ORFEO.

### Non-blocking debt i readiness

- Pozostałym zadaniem produktowym jest wybór konkretnego drugiego marketplace
  oraz implementacja jego adaptera i fixtures.
- Amazon pozostaje poza zakresem.
- Architektura jest gotowa na kolejny marketplace przez wspólny kontrakt
  adaptera, bez ponownego otwierania fundamentów P0–P2.

## Manufacturer Live Validation

Walidacja produkcyjna **nie została rozpoczęta**. Kontrola kodu wykazała
blokujący brak: `scripts/fetch_manufacturer_sources.py` pobiera strony
bezpośrednio przez `urllib`, nie przyjmuje `--allow-network` ani
`--allow-openai`, nie korzysta z provideru Firecrawl i kończy się przed wspólną
warstwą ekstrakcji OpenAI. W związku z tym nie da się nim bezpiecznie
potwierdzić limitu jednego requestu Firecrawl i jednego requestu OpenAI na
model ani terminalnego przebiegu wspólnego pipeline'u.

- `kinderkraft_live=not_executed`
- `cybex_live=not_executed`
- `firecrawl_requests=0`
- `openai_requests=0`
- `offline_tests_passed=true`
- `remaining_live_issues=brak kontrolowanego live runnera producenta z flagami
  zgody, limitem requestów oraz przekazaniem do wspólnej ekstrakcji`

## Controlled Manufacturer Live Runner

- `controlled_live_runner_fixed=true`
- `canonical_runner_path=scripts/check_manufacturer_pipeline_live.py`
- Runner ładuje `fieldnote-api/.env` absolutnie względem project root i raportuje
  wyłącznie obecność kluczy, nigdy ich wartości.
- Preflight wymaga jawnie `--allow-network` i `--allow-openai` (chyba że użyto
  `--no-openai`), wymusza `--max-sources 1` i nie może przełączyć się po cichu
  na fixture ani cache jako rzekomy test live.
- Kinderkraft NEBO preflight z obiema flagami: PASS;
  `firecrawl_key_present=true`, `openai_key_present=true`,
  `firecrawl_requests_attempted=0`, `openai_requests_attempted=0`.
- Rozszerzona bramka offline: PASS. Testy runnera obejmują zgodę, konfigurację,
  katalog roboczy, limity i liczniki prób providerów.
- Następny kontrolowany krok: pojedynczy live run Kinderkraft NEBO.

## Kinderkraft NEBO Single Live Run

- `kinderkraft_nebo_live=PASS`
- `firecrawl_requests_attempted=1`, `firecrawl_requests_succeeded=1`
- `openai_requests_attempted=0`, `openai_requests_succeeded=0`
- `openai_skipped_reason=no_unresolved_candidates`
- `manufacturer_source_id=manufacturer:kinderkraft:4c4e9b6f5353861e`
- `raw_snapshot_saved=true`, `clean_snapshot_saved=true`, `identity_match=true`
- `deterministic_facts=3`, `ai_facts=0`, `quality_rejections=0`
- Źródło producenta oraz jego evidence są dostępne w lokalnych endpointach
  produktu NEBO; evidence ma poprawne `source_id` i excerpt.
- `offline_tests_passed=true`
