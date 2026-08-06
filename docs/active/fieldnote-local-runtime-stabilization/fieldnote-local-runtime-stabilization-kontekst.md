# Kontekst — lokalny runtime Fieldnote

**Data:** 2026-08-06  
**Branch:** `main`  
**Plan:** `docs/plans/2026-08-06-001-fieldnote-local-runtime-stabilization-plan.md`

Repo ma istniejące niezacommitowane zmiany dokumentacji audytu; nie są częścią
tego tasku i nie mogą być stage'owane. Unit 8.5 pozostaje zatrzymany.

Problem reprodukowany: Supabase Auth odpowiada, frontend może zostać podany z
builda, lecz backend znika po zamknięciu terminala albo `/api/auth/me` nie ma
limitu czasu. Wtedy UI pozostaje na „Wczytywanie sesji”. Istniejący skrypt
startowy ma odłączone procesy, ale rozpoznawanie obcego backendu i health-check
nie pokrywają wszystkich przypadków.

Decyzja: zachować jeden skrypt start/stop/status, dodać jawny `/health`,
timeouty po stronie API klienta i AuthProvider oraz testy bez płatnych usług.

## Wynik Unit 1

- Backend działa odłączony od terminala przez `scripts/start_fieldnote_local.sh`;
  `/health` i `/api/health` zwracają HTTP 200.
- Frontend domyślnie jest serwowany z istniejącego `fieldnote-frontend/dist`
  przez `python3 -m http.server`, ponieważ to stabilniejszy tryb lokalnego
  demo; Vite pozostaje dostępny jawnie przez `FIELDNOTE_FRONTEND_MODE=dev`.
- Supabase Auth health zwraca HTTP 200. Bez tokena `/api/auth/me` zwraca
  szybkie HTTP 401 zamiast timeoutu.
- Testy: backend `29/29 PASS`, frontend `21/21 PASS`, typecheck PASS.
  Build Vite zatrzymał się na etapie `transforming` w środowisku roboczym;
  istniejący `dist` był obecny i został użyty do wykonawczej weryfikacji.
- Weryfikacja po osobnym poleceniu statusu potwierdziła działające procesy
  backend PID 81287 i frontend PID 81289.
