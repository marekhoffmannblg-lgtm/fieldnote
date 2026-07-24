---
date: 2026-07-23
topic: lionelo-market-intelligence-pipeline
---

# Pipeline market intelligence dla katalogu Lionelo

## Problem

Zespół Lionelo potrzebuje szybko tworzyć i okresowo odświeżać orientacyjny obraz rynku dla całego własnego katalogu. Obecna aplikacja ma fundamenty benchmarku dla wózków oraz źródeł Allegro i producentów, ale docelowy produkt ma wspierać zarówno analityka researchu, jak i zespół produktowo-handlowy — dla wielu kategorii Lionelo i konkurencyjnych modeli.

Wynik nie jest audytem o absolutnej pewności. Dane pochodzą z różnej jakości źródeł, dlatego muszą zachowywać pochodzenie, świeżość i poziom pewności, a jednocześnie szybko dostarczać użyteczny benchmark i wnioski.

## Wymagania

- R1. System importuje katalog i specyfikację produktów Lionelo ręcznie w pierwszej wersji, z przygotowaną drogą do późniejszej integracji źródła firmowego.
- R2. Dla każdego produktu Lionelo system umożliwia prowadzenie benchmarku konkurencyjnych modeli w tej samej kategorii; konkurencja jest proponowana na podstawie produktu i kategorii, a nie tworzona wyłącznie ręcznie.
- R3. Wspólny pipeline obsługuje wiele kategorii Lionelo, przy osobnych wersjonowanych schematach parametrów i kryteriów benchmarku dla każdej kategorii.
- R4. Pipeline zbiera dane z oficjalnych stron producentów, marketplace'ów, sklepów branżowych, recenzji i materiałów społecznościowych.
- R5. Fakty i parametry produktu są oddzielone od insightów rynkowych. Recenzje i materiały społecznościowe służą do tworzenia osobnego modułu trendów, zalet, wad i powtarzających się problemów, a nie jako równorzędna podstawa twardych parametrów.
- R6. Każdy model — własny i konkurencyjny — ma profil zawierający kluczowe parametry, kilka linków do źródeł, datę ostatniego odświeżenia, poziom pewności i krótkie podsumowanie.
- R7. Docelowo każdy model konkurencji powinien mieć 3–4 niezależne źródła (np. producent, marketplace i sklep). Jeśli minimum nie zostanie osiągnięte, profil pozostaje widoczny jako niepełny / o niskiej pewności, a system rekomenduje dalszy research.
- R8. Benchmark kategorii prezentuje porównywalną tabelę modeli, kluczowe parametry, ceny, linki źródłowe, daty świeżości oraz automatyczną syntezę wniosków strategicznych.
- R9. Profil i benchmark publikują automatycznie wersję roboczą. Analityk może ją później oznaczyć jako zweryfikowaną.
- R10. Przy niepełnych lub sprzecznych danych system pokazuje najlepszą dostępną wartość, oznacza ją jako niepewną i prowadzi do źródeł; nie ukrywa automatycznie całego pola ani modelu.
- R11. System proponuje produkty wymagające odświeżenia, a analityk zatwierdza uruchomienie researchu. Polityka świeżości zależy od kategorii i typu danych.
- R12. System zachowuje snapshoty oraz historię zmian i pokazuje, co zmieniło się między odświeżeniami.

## Kryteria sukcesu

- Analityk może zaimportować produkt Lionelo, uruchomić lub zatwierdzić proponowany research konkurencji i otrzymać roboczy benchmark wraz z profilami modeli.
- Zespół produktowo-handlowy może szybko porównać modele, zobaczyć źródła, świeżość, pewność danych i automatyczne wnioski bez ręcznego składania danych z wielu stron.
- Każdy wynik pozwala odróżnić parametry produktowe od insightów pochodzących z opinii i materiałów społecznościowych.
- Produkt z mniejszą niż docelowa liczbą źródeł nie znika z widoku; jest jasno oznaczony i trafia do rekomendacji dalszego researchu.
- Kolejne odświeżenie pozwala zrozumieć, co zmieniło się w danych lub na rynku od poprzedniego snapshotu.

## Granice scope'u

- Pierwsza wersja nie wymaga bezpośredniej integracji z PIM, ERP ani innym firmowym systemem katalogowym.
- Produkt nie jest panelem e-commerce, narzędziem sprzedażowym ani źródłem gwarantowanych parametrów technicznych.
- Recenzje i social media nie rozstrzygają twardych parametrów benchmarku.
- Cykliczne odświeżanie nie uruchamia się bezwarunkowo w tle: system rekomenduje, a analityk akceptuje start.
- Nie należy tworzyć osobnych, równoległych pipeline'ów dla źródeł; źródła mają przechodzić przez wspólny lifecycle, provenance i agregację.

## Kluczowe decyzje

- Użytkownicy: analityk researchu oraz zespół produktowo-handlowy. Priorytetem jest szybki, użyteczny benchmark, z widocznym ograniczeniem pewności danych.
- Zasięg katalogu: wszystkie kategorie produktów Lionelo; nie ogólna platforma dla dowolnych produktów konsumenckich.
- Architektura produktowa: wspólny silnik pipeline'u z per-kategoriowymi schematami danych, zamiast jednego schematu parametrów dla wszystkich produktów.
- Źródła: szeroki zestaw źródeł produktowych oraz osobna ścieżka insightów rynkowych.
- Publikacja: automatyczny draft i opcjonalna późniejsza weryfikacja analityka.
- Niepewność: najlepsza dostępna wartość jest pokazywana z oznaczeniem pewności oraz linkami, nie blokuje wyniku.
- Świeżość: hybrydowa — polityka zależna od danych, system rekomenduje, analityk zatwierdza.
- Historia: snapshoty i widoczny diff zmian są częścią wartości produktu, nie tylko technicznym archiwum.

## Zależności / Założenia

- Istniejący wspólny lifecycle źródeł, evidence, provenance, retry i historia runów są fundamentem do rozszerzenia, a nie do zastąpienia równoległym rozwiązaniem.
- Kategorie Lionelo oraz ich właściwe schematy benchmarku będą wymagać ustalenia i wersjonowania podczas planowania.
- Źródła zewnętrzne podlegają ograniczeniom dostawców, kosztom i zmiennej dostępności; dlatego wynik musi obsługiwać częściowy sukces.

## Otwarte pytania

### Do rozwiązania przed planowaniem

- Brak.

### Odroczone do planowania

- [Dotyczy R1, R3][Techniczne] Jaki format importu ręcznego ma stać się kanoniczny dla katalogu Lionelo i schematów kategorii?
- [Dotyczy R2, R7][Techniczne] Jak system ma proponować konkurencyjne modele i priorytetyzować źródła, bez automatycznego zawężania rynku do jednego marketplace'u?
- [Dotyczy R4, R5][Wymaga researchu] Które źródła, kanały i metody pobrania są dozwolone oraz ekonomicznie uzasadnione dla poszczególnych typów danych?
- [Dotyczy R8, R9][Techniczne] Jakie reguły i oznaczenia jakości mają prowadzić od dowodów do automatycznej syntezy oraz statusu zweryfikowania?
- [Dotyczy R11, R12][Techniczne] Jak modelować polityki świeżości i snapshoty, aby pokazywać zmianę ceny, dostępności, parametrów i insightów bez mylenia ich ze sobą?

## Następne kroki

→ /dev-plan do planowania technicznego implementacji.
