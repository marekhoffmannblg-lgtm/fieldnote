# 04 — Końcowe zamknięcie integracji producentów

To jest jeden końcowy audyt zamykający integrację producentów. Nie twórz po nim kolejnego audytu.

Etap jest read-only poza aktualizacją statusu. Nie wykonuj requestów sieciowych ani OpenAI.

## 1. Zweryfikuj wyniki

Sprawdź bezpośrednio kod, artefakty, API i testy:

- Kinderkraft NEBO live PASS,
- CYBEX ORFEO live PASS,
- wspólny `SourceAdapter`,
- wspólny lifecycle źródeł,
- raw/clean/normalized/extracted artifacts,
- quality gate i evidence,
- authority per field,
- content family deduplication,
- Research i UI źródeł,
- resume i refresh idempotency,
- brak bezpośredniego zapisu adaptera do benchmarku/finalnego produktu,
- wcześniejszy poprawny wynik zachowany po failed refreshu.

## 2. Bramka końcowa

Uruchom:

```bash
scripts/check_fieldnote.sh
```

Wykonaj lokalny smoke test bez sieci:

- `GET /api/health`
- `GET /api/products/kinderkraft__nebo`
- `GET /api/products/kinderkraft__nebo/sources`
- `GET /api/products/kinderkraft__nebo/evidence`
- `GET /api/products/cybex__orfeo`
- `GET /api/products/cybex__orfeo/sources`
- `GET /api/products/cybex__orfeo/evidence`
- `GET /api/products/cybex__orfeo/benchmark`
- `GET /api/runs`
- `GET /api/sources`

## 3. Kryteria PASS

PASS tylko gdy:

1. Oba live runy zakończyły się sukcesem.
2. Co najmniej jeden realny Firecrawl request zakończył się sukcesem dla każdego modelu.
3. OpenAI został poprawnie użyty albo jawnie pominięty, ponieważ nie było nierozstrzygniętych kandydatów.
4. Oba produkty mają poprawne źródło producenta i link produkt–źródło.
5. Snapshoty i evidence istnieją.
6. Nie ma duplikatów linków ani content families.
7. Test gate przechodzi.
8. Frontend typecheck, testy i build przechodzą.
9. Nie występuje krytyczny regres P0–P2.

Dalsza modularizacja `app.py` i `App.tsx` nie jest blokerem.

## 4. Status

Zaktualizuj tylko `docs/audit/IMPLEMENTATION_STATUS.md` i dodaj sekcję:

`MANUFACTURER PRODUCTION CLOSURE`.

Na końcu wypisz:

```text
kinderkraft_nebo_live_verified=true/false
cybex_orfeo_live_verified=true/false
manufacturer_same_pipeline_verified=true/false
manufacturer_sources_in_research=true/false
manufacturer_sources_in_product_ui=true/false
manufacturer_authority_verified=true/false
manufacturer_content_family_verified=true/false
manufacturer_resume_verified=true/false
manufacturer_refresh_verified=true/false
critical_failures=
offline_tests_passed=true/false
smoke_tests_passed=true/false
manufacturer_pipeline_production_verified=true/false
next_phase=SECOND_MARKETPLACE_SELECTION
Result: MANUFACTURER_PRODUCTION_CLOSURE_PASS lub MANUFACTURER_PRODUCTION_CLOSURE_FAIL
```

Po PASS zatrzymaj się. Nie implementuj samodzielnie drugiego marketplace'u, dopóki użytkownik nie wskaże konkretnego celu.
