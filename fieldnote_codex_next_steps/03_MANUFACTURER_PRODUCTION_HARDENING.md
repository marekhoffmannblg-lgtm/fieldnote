# 03 — Manufacturer production hardening

Wykonaj ten etap tylko wtedy, gdy NEBO i ORFEO mają wynik LIVE PASS.

Nie wykonuj nowych requestów sieciowych ani OpenAI. Użyj artefaktów zapisanych w dwóch poprzednich etapach.

## Cel

Domknij produkcyjne użycie źródeł producenta w aplikacji, bez tworzenia osobnego pipeline'u.

## 1. Spójność danych

Dla NEBO i ORFEO potwierdź:

- stabilny `source_id`,
- dokładnie jeden `ProductSourceLink` dla produktu i źródła,
- raw snapshot,
- clean snapshot,
- `NormalizedDocument`,
- evidence z excerpt i `source_id`,
- poprawne content family,
- brak duplikatów linków,
- brak bezpośredniego zapisu adaptera do benchmarku lub finalnego `model_state`.

## 2. Research

Widok Research ma:

- pokazywać oficjalne źródło oddzielnie od ofert marketplace,
- pokazywać domenę i URL,
- pokazywać exact model match,
- pokazywać fetch/clean/extraction status,
- pozwalać zatwierdzić albo odrzucić źródło,
- nie zaznaczać jako źródła produktu globalnych wpisów kolejki bez relacji.

Nie dodawaj automatycznego masowego discovery.

## 3. Widok produktu i źródeł

Dla źródła producenta pokaż:

- badge `Źródło oficjalne`,
- URL,
- datę pobrania,
- raw snapshot,
- clean snapshot,
- pola oparte na źródle,
- wkład źródła,
- konflikty z marketplace,
- informację o content family.

Przy zerowym wkładzie pokaż jawny komunikat zamiast pustego panelu.

## 4. Authority per field

Zweryfikuj automatycznymi testami:

- producent wygrywa dla wymiarów, wagi, udźwigu, materiałów i oficjalnej kompatybilności,
- marketplace wygrywa dla ceny, sprzedawcy, dostępności i konkretnego bundle,
- konflikt nie jest nadpisywany po cichu,
- opis marketplace skopiowany od producenta nie daje drugiego niezależnego potwierdzenia danych technicznych.

## 5. Refresh i resume

Potwierdź, że:

- `resume` nie wykonuje ponownego requestu dla zakończonego etapu,
- brak zmiany content hash nie tworzy nowej rodziny treści,
- refresh nie duplikuje `ProductSourceLink`,
- failed refresh nie usuwa wcześniejszego poprawnego wyniku,
- cache nie jest raportowany jako nowy live fetch.

Testuj providerami mockowanymi lub istniejącymi snapshotami. Bez sieci.

## 6. Regression gate

Uruchom:

```bash
scripts/check_fieldnote.sh
```

Wykonaj lokalny smoke test:

- produkty,
- Research,
- źródła NEBO,
- źródła ORFEO,
- dane produktu,
- benchmark,
- historia runów.

## 7. Status

Zaktualizuj wyłącznie `docs/audit/IMPLEMENTATION_STATUS.md`.

Na końcu wypisz:

```text
manufacturer_research_integration=PASS/FAIL
manufacturer_product_ui=PASS/FAIL
manufacturer_authority_matrix=PASS/FAIL
manufacturer_content_family_dedup=PASS/FAIL
manufacturer_resume=PASS/FAIL
manufacturer_refresh_idempotent=PASS/FAIL
previous_success_preserved=PASS/FAIL
product_source_link_duplicates=0
offline_tests_passed=true/false
frontend_typecheck=PASS/FAIL
frontend_tests=PASS/FAIL
frontend_build=PASS/FAIL
next_item=MANUFACTURER_FINAL_CLOSURE
Result: MANUFACTURER_PRODUCTION_HARDENING_PASS lub MANUFACTURER_PRODUCTION_HARDENING_FAIL
```
