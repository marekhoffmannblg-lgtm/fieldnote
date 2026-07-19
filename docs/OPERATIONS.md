# Operations Guide

## Uruchomienie aplikacji

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Bez kluczy API można przeglądać istniejące dane, katalog modeli, coverage i evidence.

## Klucze API

Ustawiaj klucze wyłącznie w zmiennych środowiskowych procesu:

```bash
export FIRECRAWL_API_KEY="..."
export OPENAI_API_KEY="..."
```

`FIRECRAWL_API_KEY` jest potrzebny do live targeted search i pobierania kart. `OPENAI_API_KEY` jest potrzebny tylko, gdy pełny research nie używa `--skip-ai`.

## Preview

```bash
python3 scripts/run_model_research_pipeline.py \
  --marketplace allegro \
  --brand Kinderkraft \
  --model NEBO \
  --resume
```

Preview uruchamia tylko targeted search i zwraca `pipeline_status=preview`. Nie dodaje ofert do kolejki ani nie zmienia benchmarku.

## Pełny research

```bash
python3 scripts/run_model_research_pipeline.py \
  --marketplace allegro \
  --brand Kinderkraft \
  --model NEBO \
  --apply \
  --resume
```

Po `--apply` pipeline może zmodyfikować kolejkę, karty ofert, source registry, grupy modeli, benchmark i coverage. Jeśli AI ma zostać pominięte, dodaj `--skip-ai`.

## Retry błędnych pobrań

W aplikacji przejdź do Research i użyj tabeli błędów kolejki. Możesz wybrać retry wszystkich błędów albo pojedynczej oferty.

CLI działa następująco:

```bash
python3 scripts/run_model_research_pipeline.py \
  --marketplace allegro \
  --brand Kinderkraft \
  --model NEBO \
  --apply \
  --retry-errors \
  --skip-ai
```

Retry omija targeted search i merge. Rekord może mieć maksymalnie trzy retry; po osiągnięciu limitu jest pomijany. Po udanym retry aplikacja uruchamia cleaner, source registry i model groups, ale nie AI.

## Interpretacja coverage

- `coverage_percent` - udział pól z potwierdzonymi danymi w aktualnym stanie modelu.
- `fields_confirmed` - pola potwierdzone przez źródła.
- `fields_open` - pola nadal wymagające researchu lub doprecyzowania.
- `fields_x` - brak potwierdzenia w pobranych źródłach; nie oznacza braku cechy produktu.
- `targeted_search_recommended` - system wskazuje, że warto pozyskać dalsze źródła.

## Fixture i demo

Tryb demo UI nie wymaga kluczy ani internetu:

```bash
BENCHMARK_DEMO_MODE=1 streamlit run app.py
```

Do izolowanego odczytu danych użyj własnego katalogu:

```bash
BENCHMARK_DATA_ROOT=fixtures/demo/success streamlit run app.py
```

Fixture runner:

```bash
python3 scripts/run_model_research_pipeline.py \
  --fixture-scenario partial \
  --fixture-root fixtures/demo/partial \
  --marketplace allegro \
  --brand Demo \
  --model Partial \
  --apply \
  --skip-ai
```

Dozwolone scenariusze runnera to: `success`, `partial`, `failed`, `empty_results`. Pusty katalog jest fixture UI: `fixtures/demo/empty_catalog/`.

## Typowe problemy

| Objaw | Znaczenie i działanie |
| --- | --- |
| `Brak FIRECRAWL_API_KEY` | Ustaw klucz albo użyj `--resume` z istniejącym listingiem w preview. |
| `Brak OPENAI_API_KEY` | Ustaw klucz albo w pełnym researchu dodaj `--skip-ai`. |
| `pipeline_status=partial` | Część kart pobrała się poprawnie. Sprawdź tabelę błędów kolejki i użyj retry. |
| `pipeline_status=failed` | Pobranie nie udało się w całości albo wystąpił błąd globalny. Otwórz sekcję techniczną logu, usuń przyczynę i wykonaj retry. |
| `retry_count >= 3` | Limit automatycznych retry osiągnięty. Rekord jest pomijany do czasu ręcznej decyzji. |
| `waiting_for_analysis` | Grupa ma źródła, ale nie ma `model_state.json`; użyj akcji „Uruchom analizę modelu” w katalogu. |
| `error` dla modelu | Otwórz szczegóły problemu w katalogu; zwykle chodzi o uszkodzony JSON lub duplikat `group_key`. |
| pusty katalog | Sprawdź `BENCHMARK_DATA_ROOT` albo uruchom pipeline dla pierwszego modelu. |
