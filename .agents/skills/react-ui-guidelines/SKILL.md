---
name: react-ui-guidelines
description: "Buduje i poprawia frontend React/Vite/Tailwind dla wewnętrznej aplikacji benchmarkowej. Użyj przy ekranach, formularzach, routingu, stanach async, dostępności i integracji z FastAPI/Supabase."
---

# React UI Guidelines

- Trzymaj logikę biznesową poza komponentami; używaj klienta API i hooków domenowych.
- Typuj kontrakty; waliduj dane z API na granicy systemu.
- Każdy ekran async ma jawne stany: loading, empty, partial, error i success.
- Nie ukrywaj niepełnych danych: pokaż kompletność, datę, źródła i konflikty.
- Nie używaj samego hovera do ważnych informacji; źródła i alternatywne wartości muszą być dostępne kliknięciem i klawiaturą.
- Buduj responsywnie, ale priorytetem jest czytelny desktopowy panel wewnętrzny.
- Używaj semantycznego HTML, widocznego focusu, etykiet formularzy i poprawnego kontrastu.
- Nie kopiuj globalnego stanu do wielu komponentów. Zapytania serwerowe cache'uj jedną warstwą.
- Przy uploadzie pokaż podgląd nowych, zmienionych, błędnych i konfliktowych rekordów przed zatwierdzeniem.
- Testuj zachowanie użytkownika, nie szczegóły implementacji.

Nie redesignuj całej aplikacji podczas zmian backendowych. Zachowuj istniejący routing i komponenty, dopóki nie blokują funkcji.
