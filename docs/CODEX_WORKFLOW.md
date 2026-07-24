# Workflow Codexa

## Podstawowy cykl

1. W razie braków produktowych użyj `$grill-me`.
2. Utwórz lub popraw plan przez `$dev-plan`.
3. Wykonaj jeden unit przez `$execute-plan`.
4. Uruchom `$code-review`; przy auth, bazie, uploadach lub wdrożeniu także `$security-review`.
5. Popraw findings i przejdź do kolejnego unitu.

## Przykładowe polecenia

- `Użyj $dev-plan i zaktualizuj plan na podstawie aktualnego repo. Nie implementuj.`
- `Użyj $execute-plan. Wykonaj wyłącznie Unit 1 z aktywnego planu.`
- `Użyj $code-review. Przejrzyj diff względem main; nie edytuj.`
- `Poproś explorer o mapę przepływu researchu, a potem wróć z potwierdzonymi ścieżkami.`

## Ograniczanie kosztu

- Nie uruchamiaj wielu builderów równolegle.
- Subagentów równoległych używaj do read-only eksploracji i review.
- Nie ładuj wszystkich skilli naraz; przywołuj właściwy skill nazwą `$...`.
- Wykonuj małe unity i testy celowane przed pełnym zestawem.
