# Product Benchmark Pipeline

Lokalny system market intelligence i benchmarku produktów dla Allegro. Obecny schemat benchmarku dotyczy wózków. System wyszukuje oferty dla marki i modelu, pobiera karty przez Firecrawl, oczyszcza dane, grupuje źródła, buduje benchmark na poziomie modelu i pokazuje jego coverage w aplikacji Streamlit.

Nie jest to scraper Allegro ani produkcyjna aplikacja webowa. Dostęp do danych ofert odbywa się przez Firecrawl, a AI jest używane wyłącznie w kontrolowanej kaskadzie ekstrakcji faktów z pobranych kart.

## Główne elementy

- `scripts/fetch_targeted_model_offers.py` - targeted search Allegro dla marki i modelu.
- `scripts/fetch_firecrawl_offer_pages.py` - pobieranie pojedynczych kart ofert przez Firecrawl.
- `scripts/clean_offer_pages_technical.py` - cleaner kart: usuwa UI Allegro i rozdziela sekcje produktu, obrazy oraz dane sprzedawcy.
- `scripts/build_source_registry.py` - rejestr pobranych źródeł.
- `scripts/build_model_groups.py` - kanoniczne grupy modeli.
- `scripts/extract_model_facts_cascade.py` - kaskadowa ekstrakcja AI tylko dla nadal otwartych pól.
- `scripts/build_model_benchmark.py` - benchmark na poziomie modelu.
- `scripts/report_model_coverage.py` - coverage oraz rekomendacja dalszego researchu.
- `app.py` - lokalny interfejs Streamlit do katalogu modeli, evidence, porównań, researchu i retry błędów Firecrawl.

## Kanoniczny pipeline

Jedynym zalecanym entrypointem pełnej pętli jest:

```bash
python3 scripts/run_model_research_pipeline.py \
  --marketplace allegro \
  --brand Kinderkraft \
  --model NEBO \
  --apply \
  --resume
```

Z pominiętym `--apply` to samo polecenie działa wyłącznie w trybie preview. W trybie pełnym pipeline wykonuje kolejno: targeted search, merge nowych ofert, pobranie kart Firecrawl, cleaner, source registry, model groups, AI cascade, benchmark i coverage.

### Preview i pełny research

| Tryb | Działanie |
| --- | --- |
| bez `--apply` | `preview`: tylko targeted search. Nie zmienia kolejki, registry, grup, benchmarku ani coverage. |
| `--apply` | pełny research: może dodać nowe oferty do kolejki, pobrać karty i przebudować artefakty pipeline’u. |
| `--resume` | korzysta z istniejącego listingu i stanu modelu, jeśli są dostępne. |
| `--skip-ai` | pomija AI cascade; pozostałe etapy pełnego researchu działają. |
| `--retry-errors` | wymaga `--apply`; pomija targeted search i merge, ponawia tylko istniejące rekordy kolejki ze statusem `error`. |

## Uruchomienie

### 1. Lokalna aplikacja

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Samo przeglądanie istniejącego katalogu i benchmarku nie wymaga kluczy API.

### 2. Preview modelu

```bash
python3 scripts/run_model_research_pipeline.py \
  --marketplace allegro \
  --brand Kinderkraft \
  --model NEBO \
  --resume
```

Preview kończy się `pipeline_status=preview`. Jeżeli nie istnieje wcześniejszy listing, targeted search wymaga `FIRECRAWL_API_KEY`.

### 3. Pełny research

```bash
export FIRECRAWL_API_KEY="..."
export OPENAI_API_KEY="..."

python3 scripts/run_model_research_pipeline.py \
  --marketplace allegro \
  --brand Kinderkraft \
  --model NEBO \
  --apply \
  --resume
```

Jeżeli AI ma zostać pominięte, użyj `--skip-ai` i nie ustawiaj `OPENAI_API_KEY`.

### 4. Retry błędnych pobrań

```bash
export FIRECRAWL_API_KEY="..."

python3 scripts/run_model_research_pipeline.py \
  --marketplace allegro \
  --brand Kinderkraft \
  --model NEBO \
  --apply \
  --retry-errors \
  --skip-ai
```

Fetcher ponawia rekordy `error` z `retry_count < 3`. W aplikacji Streamlit można ponowić wszystkie błędne oferty albo jedną wybraną ofertę. Retry nie dodaje nowych ofert do kolejki i nie uruchamia automatycznie AI.

### 5. Tryb demo bez API

```bash
BENCHMARK_DEMO_MODE=1 streamlit run app.py
```

W Pomocy wybierz lokalny scenariusz: sukces, częściowy sukces, błąd pipeline, brak wyników lub pusty katalog. Można też uruchomić fixture runner bez sieci:

```bash
python3 scripts/run_model_research_pipeline.py \
  --fixture-scenario success \
  --fixture-root fixtures/demo/success \
  --marketplace allegro \
  --brand Demo \
  --model Sprint \
  --apply \
  --skip-ai
```

`--fixture-root` nie może znajdować się w produkcyjnym `output/`.

## Zmienne środowiskowe

- `FIRECRAWL_API_KEY` - wymagany tylko do live targeted search i pobierania kart Firecrawl.
- `OPENAI_API_KEY` - wymagany tylko do AI cascade, gdy nie użyto `--skip-ai`.
- `BENCHMARK_DATA_ROOT` - opcjonalny katalog danych tylko do odczytu dla aplikacji. Bez tej zmiennej aplikacja używa katalogu projektu.
- `BENCHMARK_DEMO_MODE=1` - pokazuje lokalne scenariusze demonstracyjne w widoku Pomoc.

Nie zapisuj kluczy API w plikach projektu ani w dokumentacji.

## Statusy pipeline’u

- `preview` - zakończony podgląd targeted search; dane benchmarku nie zostały zmienione.
- `success` - wszystkie żądane pobrania zakończyły się bez błędów lub nie było nowych ofert do pobrania.
- `partial` - część pobrań się udała, a część zakończyła błędem; dalsze deterministyczne etapy mogą zostać wykonane dla pobranych kart.
- `failed` - pobranie nie powiodło się w całości albo wystąpił błąd globalny; pipeline zatrzymuje się przed cleanerem i AI.

## Statusy modeli w UI

- `ready` - istnieją `model_state.json` i wpis coverage.
- `analyzed_no_coverage` - istnieje stan modelu, ale brakuje coverage.
- `waiting_for_analysis` - grupa ma źródła, ale nie ma jeszcze `model_state.json`.
- `no_sources` - grupa istnieje, lecz nie zawiera źródeł.
- `error` - JSON jest uszkodzony lub dane grupy są niespójne.

## Dane i zakres

Aktualnie aktywny adapter marketplace to Allegro. Schemat benchmarku obejmuje pola wózków, między innymi ramę, koła, udźwig, wagę, wymiary po złożeniu, amortyzację, budkę, hamulec i akcesoria.

Szczegółową architekturę i kontrakty danych opisuje [docs/APP_SPEC.md](docs/APP_SPEC.md). Instrukcje operacyjne oraz diagnostyka znajdują się w [docs/OPERATIONS.md](docs/OPERATIONS.md).
