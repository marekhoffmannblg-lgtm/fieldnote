# Review — Unit 2: Supabase schema, Auth, Storage i RLS

- **Data:** 2026-07-24
- **Zakres diffu:** `807e81bd9176e274925ce3d1feac67fdb3dc9447..53af30a435be85d19f1dce3a01776e13b55be1b3`
- **Tryb:** `pełny review`
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, data_reviewer`
- **Gate:** `WYMAGA POPRAWEK`

## Kryteria akceptacji unitu

- Migracje tworzą schema katalogu, provenance, benchmarków, jobów, Auth/RLS i Storage.
- Seed jest idempotentny, a role anon/viewer/analyst/admin mają wymagane uprawnienia.
- Prywatne buckety chronią raw/clean snapshots i importy.
- Jeden aktywny job na produkt i współdzielone `source_id` pozostają wymuszone przez bazę.

## Zgodność z planem i zakresem

Review obejmuje wyłącznie 12 plików Unit 2: `supabase/config.toml`, pięć migracji, dwa seedy, dwa offline kontrakty oraz aktualizacje aktywnego tasku. Commit `53af30a` usuwa nieobsługiwaną sekcję `[project]` z configu po udanym `supabase start` i `supabase db reset`. Nie obejmuje Unit 3 ani migracji legacy state.

## Skonsolidowane findings

### P1 — blocking

Brak.

### P2 — important

#### P2 — Analityk może sfałszować aktora zdarzenia audytowego

- **File:** `supabase/migrations/202607230005_auth_roles_rls_storage.sql:110`; schema: `supabase/migrations/202607230004_jobs_audit.sql:42-49`
- **Evidence:** polityka pozwala analitykowi wstawić `audit_events`, a przekazywane przez klienta `actor_id` nie ma defaultu ani triggera wiążącego go z `auth.uid()`.
- **Impact:** analityk może przypisać wpis audytowy innemu użytkownikowi, w tym administratorowi, co podważa audit/provenance.
- **Scenario:** JWT analityka wstawia event z prawidłowym UUID administratora w `actor_id`.
- **Recommendation:** trigger albo kontrolowana funkcja `SECURITY DEFINER` wymusza `actor_id = auth.uid()` i odrzuca mismatch.
- **Missing test:** JWT analityka nie może podać cudzego `actor_id`; poprawny wpis zapisuje subject JWT.

#### P2 — Evidence nie wymusza zgodności produktu, źródła i linku provenance

- **File:** `supabase/migrations/202607230002_sources_provenance.sql:51-68`
- **Evidence:** `evidence_items.source_id` oraz `product_source_link_id` są niezależnymi FK; nie ma constraintu/triggera, który wiąże je z tym samym produktem i źródłem.
- **Impact:** trwały rekord może wskazać produkt A i źródło X, ale link produktu B i źródła Y, zasilając benchmark fałszywym provenance.
- **Scenario:** insert evidence `(product_id=A, source_id=X, product_source_link_id=link(B,Y))` przechodzi obecne pojedyncze FK.
- **Recommendation:** użyć jednego kanonicznego linku albo złożonego constraintu/FK lub triggera, który wymusza zgodność.
- **Missing test:** sprzeczny insert musi kończyć się błędem.

#### P2 — Brak wykonawczych testów RLS ról i prywatnych bucketów

- **File:** `tests/test_rls_policy_contract.py:21-51`
- **Evidence:** test sprawdza tekst SQL, lecz nie wykonuje operacji jako anon/viewer/analyst/admin ani na `storage.objects`.
- **Impact:** realne uprawnienia JWT/RLS/Storage mogą być inne niż deklarowane mimo zielonego kontraktu tekstowego.
- **Scenario:** polityka jest obecna syntaktycznie, lecz odmawia dozwolonej roli lub umożliwia niedozwoloną akcję.
- **Recommendation:** dodać test integracyjny na lokalnym Supabase dla odczytu, zapisu i usuwania danych/obiektów.
- **Missing test:** anon denied; viewer read-only; analyst zapis danych/Storage bez admina; admin profile/katalog/delete.

#### P2 — Idempotencja seedów nie ma wykonawczej regresji

- **File:** `tests/test_supabase_schema_contract.py:53-57`
- **Evidence:** test wymaga jedynie frazy `on conflict`; nie uruchamia obu seedów dwukrotnie ani nie sprawdza liczności i stabilności rekordów.
- **Impact:** kryterium idempotencji nie jest chronione przed zmianą conflict targetu lub relacji.
- **Scenario:** drugi seed zwraca błąd albo zmienia/duplikuje rekordy, mimo że tekst nadal zawiera `on conflict`.
- **Recommendation:** test integracyjny na czystej lokalnej bazie, wykonujący każdy seed dwa razy.
- **Missing test:** oba ponowne wykonania są bez błędu, bez nowych rekordów i ze stabilnymi identyfikatorami.

### P3 — non-blocking

Brak.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | PASS | 0 | 0 |
| security_reviewer | P2 | 1 | 0 |
| test_reviewer | P2 | 2 | 0 |
| data_reviewer | P2 | 1 | 0 |

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| `supabase start` | PASS | wynik zgłoszony przez executora |
| `supabase db reset` | PASS | wynik zgłoszony przez executora |
| `fieldnote-api/.venv/bin/python -m unittest tests/test_supabase_schema_contract.py tests/test_rls_policy_contract.py` | PASS | 7 testów, uruchomione podczas review |
| `bash scripts/check_fieldnote.sh` | PASS | pełna offline bramka, uruchomiona podczas review |
| `git diff --check 807e81b..53af30a` | PASS | brak błędów whitespace |

## Bezpieczeństwo

Brak P1, publicznych bucketów, polityk dla anon i sekretów w diffie. P2 dotyczą ochrony wiarygodności audytu oraz braku wykonawczego potwierdzenia autoryzacji.

## Odchylenia od planu

Brak odchyleń funkcjonalnych. Nie uruchomiono Unit 3.

## Kontrole operatora

`supabase start` i `supabase db reset` zostały wykonane przez executora z wynikiem PASS. Testy RLS/seeda wymagają teraz rozszerzenia o wykonawcze scenariusze ról i powtórzeń.

## Decyzja gate

**WYMAGA POPRAWEK** — 0 P1, 4 P2, 0 P3. Unit 2 nie jest ukończony.

## Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 2` — napraw wyłącznie cztery zaakceptowane P2 z tego raportu; następnie wykonaj ograniczony re-review Unit 2.
