# Review — Unit 2: Supabase schema, Auth, Storage i RLS

- **Data:** 2026-07-24
- **Zakres diffu:** pełny review `807e81b..53af30a`; ograniczony re-review `53af30a435be85d19f1dce3a01776e13b55be1b3..c436472`
- **Tryb:** `re-review` (zakres ograniczony do czterech P2)
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

---

## Ograniczony re-review — `53af30a..c436472`

### Zakres i zweryfikowane poprawki

Re-review obejmuje wyłącznie naprawy czterech P2: trigger aktora audytu, trigger
spójności evidence, wykonawcze testy ról/RLS/Storage oraz wykonawczy test seedów.
Nie obejmuje Unit 3 ani innych fragmentów aplikacji.

### Skonsolidowane findings re-review

#### P2 — Aktualizacja użytego linku provenance omija walidację evidence

- **File:** `supabase/migrations/202607230002_sources_provenance.sql:70-103`; powiązana polityka `supabase/migrations/202607230005_auth_roles_rls_storage.sql:120`
- **Evidence:** trigger sprawdza wyłącznie insert/update `evidence_items`; analityk może następnie zmienić `product_id` lub `source_id` wskazanego `product_source_links`.
- **Impact:** istniejący evidence może znów wskazać inny produkt/źródło niż link provenance.
- **Scenario:** poprawne evidence `(A, X, link(A,X))`, potem update linku na `(B,Y)`.
- **Recommendation:** zablokować zmianę kluczowych kolumn użytego linku albo walidować zależne evidence przy update; alternatywnie złożony FK/constraint.
- **Missing test:** update użytego linku musi być odrzucony albo atomowo utrzymać zgodność.

#### P2 — Runtime test nie wykonuje RLS tabel dla anon i ról przez API

- **File:** `tests/test_supabase_runtime_contract.py:155-203`
- **Evidence:** testuje helpery dla authenticated ról i Storage API, lecz nie wysyła requestu anon ani CRUD tabel przez PostgREST/API.
- **Impact:** tabela może omyłkowo pozwalać anonowi albo odmawiać/dozwalać operację roli mimo zielonego testu.
- **Scenario:** zmiana `authenticated_read` lub `analyst_write` na tabeli przechodzi obecne testy helperów oraz Storage.
- **Recommendation:** dodać API/PostgREST assertions dla anon, viewer, analyst i admin na reprezentatywnej tabeli.
- **Missing test:** anon denied; viewer read-only; analyst write bez admin-write; admin administruje katalogiem/profilem.

#### P2 — Seed runtime test nie potwierdza stabilnych UUID

- **File:** `tests/test_supabase_runtime_contract.py:114-129`
- **Evidence:** po dwóch uruchomieniach obu seedów asercja sprawdza wyłącznie liczność rekordów.
- **Impact:** usunięcie i ponowne utworzenie rekordu mogłoby zachować liczność, ale zerwać referencje UUID.
- **Scenario:** przyszły seed zastępuje rekord przy zachowaniu jednego produktu na klucz biznesowy.
- **Recommendation:** zachować UUID po pierwszym uruchomieniu i porównać je po drugim dla brandów, produktów i schema metadata.
- **Missing test:** powtórny seed zachowuje UUID rekordów dev i E2E.

### Wyniki reviewerów re-review

| Reviewer | Wynik | Findings przyjęte |
|---|---|---:|
| correctness_reviewer | P2 | 1 |
| security_reviewer | PASS | 0 |
| test_reviewer | P2 | 2 |
| data_reviewer | P2 | 1 (duplikat correctness) |

### Testy re-review

| Kontrola | Wynik |
|---|---|
| Kontrakty schema/RLS | PASS — 9 testów |
| `FIELDNOTE_SUPABASE_INTEGRATION=1` runtime contract | PASS — 4 testy |
| `git diff --check 53af30a..c436472` | PASS |

### Decyzja gate re-review

**WYMAGA POPRAWEK** — 0 P1, 3 P2, 0 P3. Poprawka spoofingu aktora audytu jest zaakceptowana; Unit 2 pozostaje nieukończony.

### Rekomendowany następny krok re-review

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 2` — napraw wyłącznie trzy P2 z ograniczonego re-review, potem ponów ograniczony `$dev-docs-review docs/active/fieldnote-stroller-mvp 2`.

---

## Status wykonania napraw trzech P2

Executor wdrożył wyłącznie wskazane naprawy: blokadę rewrite provenance linku używanego przez evidence, requesty PostgREST dla anon/viewer/analyst/admin oraz porównanie stabilnych UUID po drugim uruchomieniu obu seedów. Dodane granty dla `authenticated` pozwalają PostgREST dotrzeć do tabel, przy zachowaniu RLS jako granicy autoryzacji; `anon` nie otrzymał grantów tabel.

Wyniki executora: `supabase db reset --local --yes` PASS, runtime contract 5 PASS, kontrakty schema/RLS/runtime 14 PASS (5 opt-in skipped), pełna offline bramka `bash scripts/check_fieldnote.sh` PASS i `git diff --check` PASS. Ten wpis nie jest re-review: decyzja gate pozostaje **WYMAGA POPRAWEK** do czasu ograniczonego review tych napraw.

---

## Ograniczony re-review — `eaa580e^..eaa580e`

### Kryteria i zakres

Re-review obejmuje wyłącznie trzy naprawy P2 z poprzedniego re-review i ich regresje:

1. zmiana `product_id` lub `source_id` linku używanego przez evidence musi być odrzucona;
2. PostgREST musi wykonawczo sprawdzać anon, viewer, analyst oraz admin dla tabel RLS;
3. oba seedy muszą zachować UUID marek i produktów po drugim uruchomieniu.

Zakres kodu: `202607230002_sources_provenance.sql`, `202607230005_auth_roles_rls_storage.sql` oraz trzy kontrakty Supabase. Nie obejmuje Unit 3.

### Skonsolidowane findings

#### P1 — blocking

Brak.

#### P2 — important

##### P2 — Wykonawczy test RLS pomija adminowy zapis katalogu

- **File:** `tests/test_supabase_runtime_contract.py:259-293`
- **Evidence:** requesty PostgREST pokrywają anon, viewer, analyst oraz `POST /profiles` dla admina, lecz nie wykonują operacji na tabeli katalogu chronionej odrębną polityką `admin_write` (`brands`, `products` i pokrewne).
- **Impact:** regresja polityki `admin_write` może zablokować administratorowi zarządzanie katalogiem, podczas gdy obecny test nadal przechodzi.
- **Scenario:** `admin_write` na `public.products` zostaje usunięte lub jego warunek przestaje działać; admin nadal utworzy profil, więc runtime contract zwróci PASS.
- **Recommendation:** dodać deterministyczny POST/UPSERT katalogowego rekordu przez PostgREST z JWT administratora oraz odmowę analogicznego zapisu dla roli nie-admin.
- **Missing test:** admin tworzy lub aktualizuje fixture `brand`/`product` przez REST; analyst otrzymuje 401/403 dla tej samej akcji.

#### P3 — non-blocking

Brak.

### Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | P2 | 1 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | P2 | 1 (duplikat correctness) | 0 |
| data_reviewer | PASS | 0 | 0 |

### Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Kontrakty schema/RLS/runtime offline | PASS | 14 testów, 5 opt-in skipped |
| `FIELDNOTE_SUPABASE_INTEGRATION=1 fieldnote-api/.venv/bin/python -m unittest tests/test_supabase_runtime_contract.py` | PASS | 5 testów |
| `bash scripts/check_fieldnote.sh` | PASS | backend, checkery i frontend typecheck/test/build |
| `git diff --check eaa580e^ eaa580e` | PASS | brak błędów whitespace |

### Bezpieczeństwo

Security review PASS. Granty tabel i sekwencji dla `authenticated` umożliwiają PostgREST dojście do RLS; `anon` nie ma grantów tabel, a polityki nadal są granicą autoryzacji. Nie wykryto sekretów ani eskalacji uprawnień w zakresie diffu.

### Odchylenia od planu

Brak odchyleń funkcjonalnych. Nie rozpoczęto Unit 3.

### Decyzja gate

**WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3. Dwa pozostałe P2 z poprzedniego re-review są zamknięte; Unit 2 nie jest jeszcze ukończony.

### Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 2` — napraw wyłącznie P2: wykonawczy test PostgREST adminowego zapisu katalogu (wraz z odmową dla nie-admina); potem ponów ograniczony `$dev-docs-review docs/active/fieldnote-stroller-mvp 2`.

---

## Status wykonania ostatniego P2

Executor zmienił wyłącznie `tests/test_supabase_runtime_contract.py`: JWT analyst otrzymuje odmowę zapisu `brands` przez PostgREST, a JWT admin wykonuje idempotentny UPSERT tego samego fixture po `brand_key`. Wyniki: runtime integration 5 PASS; kontrakty schema/RLS/runtime 14 PASS (5 opt-in skipped); pełna offline bramka PASS; `git diff --check` PASS. Ten wpis nie jest re-review — gate pozostaje **WYMAGA POPRAWEK** do czasu ograniczonego review poprawki.

---

## Ograniczony re-review — `39c5fdd^..39c5fdd`

### Kryterium i zakres

Re-review obejmuje wyłącznie wykonawczy zapis katalogu `brands` przez PostgREST: odmowę dla analyst i uprawniony UPSERT dla admina. Zmiana kodowa jest ograniczona do `tests/test_supabase_runtime_contract.py`; nie obejmuje migracji, modeli ani Unit 3.

### Skonsolidowane findings

#### P1 — blocking

Brak.

#### P2 — important

##### P2 — Test nie weryfikuje idempotencji adminowego zapisu katalogu

- **File:** `tests/test_supabase_runtime_contract.py:279-288`
- **Evidence:** adminowy POST/UPSERT jest wykonywany tylko raz; test nie wysyła drugiego identycznego requestu ani nie potwierdza, że istnieje dokładnie jeden `brand_key`.
- **Impact:** regresja obsługi `on_conflict` lub nagłówka upsert może złamać ponowiony zapis katalogu, mimo zielonego testu.
- **Scenario:** drugi POST po zmianie `Prefer: resolution=merge-duplicates` zwraca konflikt; obecny test nadal przechodzi.
- **Recommendation:** wykonać drugi identyczny POST admina i potwierdzić sukces obu requestów oraz jedną pozycję fixture.
- **Missing test:** dwa POST-y dla tego samego `brand_key` przez `/rest/v1/brands`, oba udane, końcowo liczność równa 1.

#### P3 — non-blocking

Brak.

### Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | PASS | 0 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | P2 | 1 | 0 |

`data_reviewer` nie był wymagany: diff nie zmienia migracji, modeli, persistence, importu, scoringu, kolejki ani workera.

### Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Kontrakty schema/RLS/runtime offline | PASS | 14 testów, 5 opt-in skipped |
| `FIELDNOTE_SUPABASE_INTEGRATION=1 fieldnote-api/.venv/bin/python -m unittest tests/test_supabase_runtime_contract.py` | PASS | 5 testów |
| `bash scripts/check_fieldnote.sh` | PASS | backend, checkery i frontend typecheck/test/build |
| `git diff --check 39c5fdd^ 39c5fdd` | PASS | brak błędów whitespace |

### Bezpieczeństwo

Security review PASS. Test nie wprowadza nowego grantu ani sekretu; nadal sprawdza odmowę zapisu katalogu dla analyst i uprawnienie admina przez PostgREST.

### Odchylenia od planu

Brak odchyleń funkcjonalnych. Nie rozpoczęto Unit 3.

### Decyzja gate

**WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3. Unit 2 nie jest ukończony.

### Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 2` — napraw wyłącznie P2: wykonaj drugi adminowy POST/UPSERT `brands` przez PostgREST i potwierdź jedną pozycję fixture; następnie ponów ograniczony `$dev-docs-review docs/active/fieldnote-stroller-mvp 2`.

---

## Status wykonania ostatniego P2 po re-review

Executor zmienił wyłącznie `tests/test_supabase_runtime_contract.py`: po pierwszym udanym adminowym UPSERT `brands` wykonuje drugi identyczny request i przez adminowy GET PostgREST potwierdza dokładnie jedną pozycję `runtime-admin-catalog`. Odmowa zapisu dla analyst pozostaje. Wyniki: runtime integration 5 PASS; kontrakty schema/RLS/runtime 14 PASS (5 opt-in skipped); pełna offline bramka PASS; `git diff --check` PASS. Ten wpis nie jest re-review — gate pozostaje **WYMAGA POPRAWEK** do czasu ograniczonego review poprawki.

---

## Końcowy ograniczony re-review — `aa9ca91^..aa9ca91`

### Kryterium i zakres

Re-review obejmuje wyłącznie naprawę wykonawczej idempotencji adminowego UPSERT `brands`: drugi identyczny POST przez PostgREST oraz odczyt potwierdzający jeden rekord fixture. Nie obejmuje migracji, modeli danych ani Unit 3.

### Skonsolidowane findings

#### P1 — blocking

Brak.

#### P2 — important

Brak.

#### P3 — non-blocking

Brak.

### Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | PASS | 0 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | PASS | 0 | 0 |

`data_reviewer` i `ui_reviewer` nie były wymagane: diff nie zmienia migracji, modeli, persistence ani interfejsu.

### Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Kontrakty schema/RLS/runtime offline | PASS | 14 testów, 5 opt-in skipped |
| `FIELDNOTE_SUPABASE_INTEGRATION=1 fieldnote-api/.venv/bin/python -m unittest tests/test_supabase_runtime_contract.py` | PASS | 5 testów |
| `bash scripts/check_fieldnote.sh` | PASS | backend, checkery i frontend typecheck/test/build |
| `git diff --check aa9ca91^ aa9ca91` | PASS | brak błędów whitespace |

### Bezpieczeństwo

Security review PASS. Dwa requesty admina i odczyt nadal przechodzą przez PostgREST/RLS; odmowa dla analyst pozostaje wykonawczo sprawdzona. Nie wykryto sekretów ani nowych uprawnień.

### Odchylenia od planu

Brak. Unit 3 nie został rozpoczęty.

### Decyzja gate

**GOTOWE DO KONTYNUACJI** — 0 P1, 0 P2, 0 P3. Unit 2 jest ukończony.

### Rekomendowany następny krok

Po wyraźnym poleceniu użytkownika: `$dev-docs-execute docs/active/fieldnote-stroller-mvp 3`.
