# Zadanie 01 — P0: stabilność uruchomień i zapisów

**Sugerowany model:** GPT-5.6 Terra, reasoning High.

Pracujesz w repozytorium FIELDNOTE.

Audyt istnieje, ale nie zakładaj, że opisane w raportach poprawki są faktycznie wdrożone. Zweryfikuj kod i dane. W tym zadaniu wdrażasz wyłącznie fundament P0.

Nie używaj sieci, Firecrawl, OpenAI ani Playwrighta. Nie rozpoczynaj P1/P2 ani integracji producentów.

## Cel

Zapewnić bezpieczne, deterministyczne i wznawialne uruchamianie lokalnego pipeline’u.

## 1. Baseline

1. Odczytaj istniejące raporty w `docs/audit/`.
2. Uruchom dostępne testy i zapisz wynik bazowy.
3. Zidentyfikuj aktualne entrypointy backendu, pipeline’u i skryptu startowego.
4. Nie ufaj deklaracjom raportów bez potwierdzenia w kodzie.

## 2. Run coordinator

Dodaj jeden koordynator runów odpowiedzialny za:

- generowanie `run_id`,
- niezmienny kontekst runu,
- statusy terminalne,
- blokadę per produkt,
- blokadę globalną tylko dla operacji agregujących wspólne dane,
- rejestrowanie czasu startu i zakończenia,
- anulowanie,
- timeout,
- recovery po restarcie.

Minimalne statusy:

- `queued`
- `running`
- `cancelling`
- `cancelled`
- `succeeded`
- `failed`
- `timed_out`
- `interrupted`

Nie wolno uruchomić dwóch aktywnych runów tego samego produktu. Równoległe runy różnych produktów mają być dozwolone, o ile nie wykonują chronionej operacji globalnej.

## 3. Immutable run context

Każdy run zapisuje niezmienny kontekst zawierający co najmniej:

- `run_id`,
- produkt i `product_slug`,
- wejściowe parametry research,
- wybrane source IDs,
- wersję schematu,
- flagi wykonania,
- timestamp utworzenia.

Pipeline nie może w trakcie działania czytać zmiennych ustawień użytkownika zamiast zapisanego kontekstu runu.

## 4. Timeout, cancel i recovery

1. Każdy subprocess musi mieć timeout.
2. Timeout ma kończyć run statusem `timed_out` i zachowywać log błędu.
3. Cancel ma zatrzymywać proces potomny oraz oznaczać run jako `cancelled`.
4. Po restarcie osierocone runy `running` lub `cancelling` mają być deterministycznie oznaczone jako `interrupted` albo wznowione tylko wtedy, gdy mechanizm resume jest bezpieczny.
5. Błąd nowego runu nie może usuwać wcześniejszego poprawnego wyniku produktu.

## 5. Atomowe zapisy

Wprowadź wspólne funkcje atomowego zapisu dla JSON, JSONL, CSV i plików statusowych:

- zapis do pliku tymczasowego w tym samym filesystemie,
- flush i fsync, gdy ma zastosowanie,
- atomowe `replace`,
- zachowanie kopii `.previous` dla krytycznych stanów,
- brak częściowo zapisanych plików po przerwaniu procesu.

Zastosuj je co najmniej do:

- statusu produktu,
- manifestów runów,
- finalnego stanu produktu,
- indeksów runów,
- globalnych agregacji.

## 6. Kanoniczny status produktu

Utwórz jeden kanoniczny stan produktu, np. `output/product_state.json` lub równoważny istniejący kontrakt.

Stan ma rozróżniać:

- brak analizy,
- analiza w toku,
- ostatni run zakończony sukcesem,
- ostatni run zakończony błędem,
- istniejący wcześniejszy poprawny rezultat,
- potrzebę odświeżenia,
- potrzebę review.

Najważniejsza reguła:

> Nieudany nowszy run nie usuwa ani nie ukrywa ostatniego poprawnego wyniku. UI może pokazać ostrzeżenie o błędzie odświeżenia, ale nadal udostępnia ostatni poprawny produkt.

## 7. Startup script

Napraw `scripts/start_fieldnote_local.sh` albo odpowiadający mu skrypt:

- domyślnie bez autoreloadu,
- tryb `dev` może używać reload,
- PID files,
- `start`, `stop`, `status`,
- healthcheck backendu i frontendu,
- nie zabijaj obcego procesu tylko dlatego, że zajmuje port,
- przed kill sprawdź PID, command i working directory,
- czytelne logi i ograniczenie ich rozmiaru.

## 8. Testy P0

Dodaj testy offline obejmujące:

1. dwa równoległe runy tego samego produktu,
2. równoległe runy różnych produktów,
3. timeout subprocessu,
4. anulowanie,
5. recovery osieroconego runu,
6. atomowy zapis przy przerwaniu,
7. zachowanie poprzedniego poprawnego wyniku po błędzie,
8. obcy proces na porcie nie jest zabijany,
9. standardowy start nie używa reload.

## 9. Status

Nie twórz osobnego rozbudowanego audytu.

Utwórz lub zaktualizuj wyłącznie:

`docs/audit/IMPLEMENTATION_STATUS.md`

Dodaj:

- zakres P0,
- pliki zmienione,
- testy,
- znane ograniczenia,
- następny etap `P1_DATA_HISTORY_SOURCES`.

Na końcu wypisz:

```text
p0_run_coordinator
p0_product_locks
p0_global_lock
p0_timeout
p0_cancel
p0_recovery
p0_atomic_writes
p0_canonical_product_state
p0_previous_success_preserved
p0_start_script_hardened
backend_tests
frontend_typecheck
frontend_build
network_fetches=0
openai_calls=0
next_item=P1_DATA_HISTORY_SOURCES
Result: P0_COMPLETE
```

Nie oznaczaj sukcesu, jeżeli testy P0 nie przechodzą.
