---
name: dev-plan
description: "Tworzy lub aktualizuje techniczny plan implementacji na podstawie wymagań i rzeczywistego kodu repozytorium. Użyj przy planowaniu feature'u, migracji, refaktoru lub większej poprawki; nie używaj do implementacji kodu."
---

# Dev Plan

Twórz plan techniczny, nie implementuj kodu.

## Przebieg

1. Przeczytaj `AGENTS.md`, `docs/CONCEPTS.md` i najnowszy pasujący dokument w `docs/brainstorms/`.
2. Sprawdź istniejący plan w `docs/plans/`; aktualizuj go zamiast tworzyć duplikat, gdy zakres jest ten sam.
3. Zleć agentowi `explorer` mapowanie rzeczywistych ścieżek, wzorców, testów i zależności.
4. Zweryfikuj zmienne w czasie technologie wyłącznie w aktualnej dokumentacji producenta.
5. Rozwiąż tylko blokujące decyzje produktowe. Nie pytaj o oczywiste wybory techniczne; wybierz najprostszy bezpieczny wariant i zapisz uzasadnienie.
6. Rozbij pracę na atomowe Implementation Units, wykonywane po jednym.
7. Zapisz plan w `docs/plans/YYYY-MM-DD-NNN-<type>-<slug>-plan.md`.

## Wymagany format unitu

Każdy unit zawiera: cel, wymagania, zależności, dokładne pliki, podejście, scenariusze testowe, automatyczną weryfikację i ryzyka. Feature-bearing unit musi wskazywać plik testowy.

## Zasady

- Bazuj na działającym kodzie; nie proponuj przepisywania od zera bez dowodu, że migracja przyrostowa jest niemożliwa.
- Oddziel ustalenia znane od niewiadomych zależnych od runtime'u.
- Nie wpisuj komend git ani kodu implementacji.
- Dla UI wskaż źródło designu albo jawnie zapisz jego brak.
- Dla bezpieczeństwa, auth, Supabase, Firecrawl i Rendera uwzględnij odpowiednie skille repozytorium.

Przed zapisem użyj szablonu z `references/plan-template.md`.
