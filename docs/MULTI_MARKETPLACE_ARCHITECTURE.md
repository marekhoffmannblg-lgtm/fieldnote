# Multi-marketplace architecture

Finalnym obiektem analizy jest `brand + normalized_model`, a nie pojedyncza aukcja ani marketplace. Każde źródło ma globalny `source_id`, marketplace, source type, external offer ID, URL kanoniczny, sprzedawcę, język, kraj i ścieżki provenance.

## Rekomendacja researchu

`report_model_coverage.py` rekomenduje dodatkowy research, gdy model ma mniej niż 3 źródła, mniej niż 3 źródła Allegro, więcej niż 5 otwartych pól, więcej niż 5 pól X, coverage poniżej 70%, niską jakość jedynego marketplace’u albo konflikty/niski confidence dla pól.

Kolejność działań: dokładne wyszukiwanie marka + model na obecnym marketplace, następnie inne marketplace’y po dodaniu adapterów, a na końcu oficjalna strona producenta jako osobny `source_type`.

Nowe źródła są dołączane przez registry i analizowane przez kaskadę tylko dla pól otwartych, niepewnych lub konfliktowych. `model_state.json` nie jest resetowany.
