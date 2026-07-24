#!/usr/bin/env python3
"""Build the offline Lionelo product taxonomy from the inventory CSV."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = Path.home() / "Downloads" / "FIELDNOTE_product_inventory.csv"
OUTPUT = ROOT / "output" / "taxonomy"
EXTRA_COLUMNS = [
    "category_key", "category_label_pl", "subcategory_key", "subcategory_label_pl",
    "benchmark_group_key", "benchmark_group_label_pl", "benchmarkable", "secondary_functions",
    "classification_confidence", "review_required", "review_reason",
]

CATEGORY_LABELS = {
    "mobility": "Mobilność", "car_safety": "Bezpieczeństwo w samochodzie",
    "feeding": "Karmienie", "sleep_and_relax": "Sen i relaks",
    "play_and_ride": "Zabawa i jazda", "monitoring_and_health": "Monitoring i zdrowie",
    "home_safety": "Bezpieczeństwo w domu", "textiles": "Tekstylia dziecięce", "accessories": "Akcesoria",
}
SUBCATEGORY_LABELS = {
    "strollers": "Wózki dziecięce", "car_seats": "Foteliki samochodowe", "car_seat_accessories": "Akcesoria do fotelików",
    "stroller_accessories": "Akcesoria do wózków", "travel_cots": "Łóżeczka turystyczne", "bedside_cots": "Łóżeczka dostawne",
    "playpens": "Kojce", "cradles": "Kołyski", "rockers": "Bujaczki i leżaczki", "high_chairs": "Krzesełka do karmienia",
    "kitchen_helpers": "Pomocniki kuchenne", "breast_pumps": "Laktatory", "lactation_accessories": "Akcesoria laktacyjne",
    "bottle_warmers": "Podgrzewacze do butelek", "portable_bottle_warmers": "Przenośne podgrzewacze do butelek",
    "wipe_warmers": "Podgrzewacze do chusteczek", "sterilizers_and_dryers": "Sterylizatory i suszarki",
    "water_and_formula_makers": "Urządzenia do wody i mleka", "food_processors": "Roboty kuchenne",
    "baby_monitors": "Nianie elektroniczne", "nasal_aspirators": "Aspiratory do nosa", "nebulizers": "Nebulizatory",
    "thermometers": "Termometry dziecięce", "baby_scales": "Wagi niemowlęce", "safety_gates": "Bramki ochronne",
    "bed_rails": "Barierki do łóżka", "balance_bikes": "Rowerki biegowe", "tricycles": "Rowerki trójkołowe",
    "scooters": "Hulajnogi", "helmets": "Kaski", "baby_blankets": "Kocyki dziecięce",
    "swaddles_and_muslins": "Otulacze i pieluszki muślinowe", "baby_bedding": "Pościel i prześcieradła dziecięce",
    "bath_textiles": "Tekstylia kąpielowe", "general_accessories": "Akcesoria specjalistyczne",
    "monitor_accessories": "Akcesoria do niań", "feeding_consumables": "Materiały eksploatacyjne do karmienia", "diaper_disposal": "Utylizacja pieluch",
}

GROUPS = {
    "light_stroller": ("Lekkie wózki spacerowe", "Kompaktowe spacerówki do codziennych podróży i miasta."),
    "standard_stroller": ("Standardowe wózki spacerowe", "Spacerówki bez deklarowanej lekkiej, podróżnej konstrukcji."),
    "stroller_2in1": ("Wózki 2w1", "Zestawy gondola i spacerówka."),
    "stroller_3in1": ("Wózki 3w1", "Zestawy gondola, spacerówka i fotelik lub adaptery."),
    "infant_car_seat": ("Foteliki niemowlęce", "Foteliki dla niemowląt, zwykle w zakresie 40–87 cm."),
    "extended_rwf_car_seat": ("Foteliki RWF 40–150 cm", "Foteliki umożliwiające jazdę tyłem w szerokim zakresie wzrostu."),
    "toddler_car_seat": ("Foteliki 76–150 cm", "Foteliki dla starszych dzieci w zakresie 76–150 cm."),
    "high_back_booster": ("Foteliki podwyższające 100–150 cm", "Foteliki high-back booster dla dzieci 100–150 cm."),
    "isofix_base": ("Bazy ISOFIX", "Bazy do kompatybilnych fotelików samochodowych."),
    "travel_cot": ("Łóżeczka turystyczne", "Składane łóżeczka do podróży i snu."),
    "bedside_cot": ("Łóżeczka dostawne", "Łóżeczka ustawiane przy łóżku rodzica."),
    "playpen": ("Kojce", "Kojce zapewniające wydzieloną przestrzeń do zabawy."),
    "cradle": ("Kołyski", "Niewielkie łóżeczka lub kołyski dla niemowląt."),
    "rocker": ("Bujaczki i leżaczki", "Siedziska kołyszące lub leżaczki dla niemowląt."),
    "classic_high_chair": ("Klasyczne krzesełka do karmienia", "Krzesełka do posiłków dla małych dzieci."),
    "growing_high_chair": ("Krzesełka rosnące", "Krzesełka regulowane wraz ze wzrostem dziecka."),
    "kitchen_helper": ("Pomocniki kuchenne", "Podesty umożliwiające dziecku udział w czynnościach kuchennych."),
    "hands_free_breast_pump": ("Laktatory hands-free", "Laktatory noszone w biustonoszu."),
    "electric_breast_pump": ("Laktatory elektryczne", "Klasyczne laktatory elektryczne."),
    "milk_collector": ("Kolektory mleka", "Kolektory i ręczne rozwiązania do zbierania pokarmu."),
    "countertop_bottle_warmer": ("Stacjonarne podgrzewacze", "Podgrzewacze do butelek używane głównie w domu."),
    "portable_bottle_warmer": ("Przenośne podgrzewacze", "Podgrzewacze do butelek do użycia poza domem."),
    "sterilizer_warmer": ("Podgrzewacze ze sterylizacją", "Urządzenia łączące podgrzewanie i sterylizację."),
    "water_formula_maker": ("Ekspresy do wody i mleka", "Urządzenia przygotowujące wodę lub mleko dla dziecka."),
    "baby_food_processor": ("Roboty kuchenne dla dzieci", "Urządzenia do przygotowywania posiłków dla dzieci."),
    "audio_baby_monitor": ("Nianie audio", "Nianie przekazujące dźwięk do odbiornika audio."),
    "video_baby_monitor": ("Nianie wideo", "Nianie z kamerą i dedykowanym monitorem."),
    "app_baby_monitor": ("Nianie aplikacyjne", "Nianie z funkcjami aplikacji lub AI."),
    "video_app_baby_monitor": ("Nianie wideo z aplikacją", "Nianie z kamerą, monitorem i obsługą aplikacji."),
    "nasal_aspirator": ("Aspiratory do nosa", "Urządzenia do oczyszczania nosa dziecka."),
    "nebulizer": ("Nebulizatory", "Urządzenia do inhalacji."), "thermometer": ("Termometry dziecięce", "Termometry do pomiaru temperatury."),
    "baby_scale": ("Wagi niemowlęce", "Wagi do kontroli masy dziecka."), "safety_gate": ("Bramki ochronne", "Bramki zabezpieczające przejścia."),
    "bed_rail": ("Barierki do łóżka", "Barierki chroniące dziecko przed upadkiem z łóżka."),
    "balance_bike": ("Rowerki biegowe", "Rowerki bez pedałów do nauki równowagi."),
    "tricycle": ("Rowerki trójkołowe", "Trójkołowe pojazdy dla małych dzieci."),
    "balance_scooter": ("Hulajnogi balansowe", "Hulajnogi przeznaczone do nauki równowagi."),
    "stunt_scooter": ("Hulajnogi wyczynowe", "Hulajnogi do jazdy sportowej i trików."),
    "child_helmet": ("Kaski dziecięce", "Kaski ochronne do jazdy."),
    "baby_blanket": ("Kocyki dziecięce", "Kocyki do snu, spacerów i codziennego okrycia."),
    "swaddle_and_muslin": ("Otulacze i pieluszki", "Otulacze oraz pieluszki muślinowe lub bambusowe."),
    "baby_bedding": ("Pościel i prześcieradła", "Tekstylia do łóżeczka dziecięcego."),
    "bath_textile": ("Tekstylia kąpielowe", "Ręczniki i okrycia po kąpieli."),
    "stroller_accessory": ("Akcesoria do wózków", "Akcesoria i części do wózków."),
    "car_seat_accessory": ("Akcesoria do fotelików", "Akcesoria i części do fotelików."),
    "feeding_accessory": ("Akcesoria do karmienia", "Akcesoria eksploatacyjne do karmienia."),
    "feeding_consumable": ("Materiały eksploatacyjne do karmienia", "Jednorazowe materiały do przechowywania lub sterylizacji pokarmu."),
    "diaper_disposal": ("Kosze na pieluchy", "Systemy do higienicznej utylizacji pieluch."),
    "monitor_accessory": ("Akcesoria do niań", "Akcesoria do urządzeń monitorujących dziecko."),
    "care_accessory": ("Akcesoria pielęgnacyjne", "Dedykowane akcesoria pielęgnacyjne bez własnego rynku benchmarkowego."),
    "wipe_warmer": ("Podgrzewacze do chusteczek", "Urządzenia utrzymujące temperaturę i wilgotność chusteczek."),
}


def clean(value: str | None) -> str:
    return (value or "").strip()


def normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", clean(value).casefold()).strip()


def load_specification(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    """Read each sheet once, using row 3 as property names and row 6+ as data."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise SystemExit("Brak openpyxl: uruchom generator interpreterem workspace dependencies.") from exc
    workbook = load_workbook(path, read_only=True, data_only=True)
    records: dict[tuple[str, str], dict[str, str]] = {}
    for sheet in workbook.worksheets:
        if sheet.title.startswith("__"):
            continue
        header_row = next(sheet.iter_rows(min_row=3, max_row=3, values_only=True), ())
        headers = [clean(str(value)) for value in header_row]
        for values in sheet.iter_rows(min_row=6, values_only=True):
            if not values or not clean(str(values[0] or "")):
                continue
            record = {headers[index]: clean(str(value or "")) for index, value in enumerate(values) if index < len(headers) and headers[index]}
            model = normalize(record.get("model"))
            if model:
                records.setdefault((sheet.title, model), record)
    return records


def classify(row: dict[str, str], spec: dict[str, str]) -> tuple[str, str, str, str, str, str, str, bool, str]:
    """Return category, subcategory, group, benchmarkability, secondary, confidence, review, reason."""
    tab, kind, l2, l3, config = (clean(row[k]) for k in ("source_tab", "type", "collection_l2", "collection_l3", "configuration"))
    text = " ".join((tab, kind, l2, l3, row.get("product_name", ""))).lower()
    accessory = clean(row.get("scope")) != "produkt główny"
    review: list[str] = []
    secondary = ""
    confidence = "high"
    if clean(row.get("additional_tabs")):
        review.append("produkt występuje w kilku zakładkach")
        confidence = "medium"
    spec_type = normalize(spec.get("Typ produktu") or spec.get("typ produktu"))
    kind_normalized = normalize(kind)
    collection_normalized = normalize(" ".join((l2, l3)))
    # Textiles are retail product types, not generic care accessories. The
    # sheet only identifies their origin; type and collection decide the market.
    if tab == "TEKSTYLIA":
        if "kocyk" in kind_normalized:
            return "textiles", "baby_blankets", "baby_blanket", "later", "", confidence, bool(review), "; ".join(review)
        if "otulacz" in kind_normalized or "pielusz" in kind_normalized or "pieluch" in kind_normalized:
            return "textiles", "swaddles_and_muslins", "swaddle_and_muslin", "later", "", confidence, bool(review), "; ".join(review)
        if "prześcierad" in kind_normalized or "posciel" in kind_normalized:
            return "textiles", "baby_bedding", "baby_bedding", "later", "", confidence, bool(review), "; ".join(review)
        if "kąpiel" in kind_normalized or "ręcznik" in kind_normalized:
            return "textiles", "bath_textiles", "bath_textile", "later", "", confidence, bool(review), "; ".join(review)
        return "textiles", "baby_bedding", "baby_bedding", "later", "", "low", True, "niejednoznaczny typ tekstyliów"
    if accessory:
        if "kask" in text or "helmet" in text:
            return "play_and_ride", "helmets", "child_helmet", "yes", "", confidence, bool(review), "; ".join(review)
        if "wózk" in text or tab == "AKCESORIA_WÓZKI": return "accessories", "stroller_accessories", "stroller_accessory", "later" if any(x in text for x in ("torba", "organizer", "śpiworek", "mufk")) else "no", "", confidence, bool(review), "; ".join(review)
        if "fotelik" in text or tab == "AKCESORIA_FOTELIKI": return "accessories", "car_seat_accessories", "car_seat_accessory", "later" if "baza" in text else "no", "", confidence, bool(review), "; ".join(review)
        if "uchwyt do kamery" in spec_type or "kamery" in text: return "accessories", "monitor_accessories", "monitor_accessory", "no", "", confidence, bool(review), "; ".join(review)
        if "kosz na zużyte pieluszki" in spec_type or "kosz na pieluch" in text: return "accessories", "diaper_disposal", "diaper_disposal", "later", "", confidence, bool(review), "; ".join(review)
        if any(x in text for x in ("woreczki", "pokarm", "steryliz")): return "accessories", "feeding_consumables", "feeding_consumable", "later", "", confidence, bool(review), "; ".join(review)
        return "accessories", "general_accessories", "care_accessory", "no", "", confidence, bool(review), "; ".join(review)
    if tab == "WÓZKI":
        group = "stroller_2in1" if config == "2w1" else "stroller_3in1" if config == "3w1" else "light_stroller" if "spacerówki lekkie" in l3.lower() else "standard_stroller"
        return "mobility", "strollers", group, "yes", "", confidence, bool(review), "; ".join(review)
    if tab == "FOTELIKI":
        group = "infant_car_seat" if "40-87" in l3 else "extended_rwf_car_seat" if "40-150" in l3 else "toddler_car_seat" if "76-150" in l3 else "high_back_booster"
        return "car_safety", "car_seats", group, "yes", "includes_base" if config == "Set" else "", confidence, bool(review), "; ".join(review)
    if tab == "ŁÓŻECZKA_I_KOJCE":
        group = "travel_cot" if "turystyczne" in kind.lower() else "bedside_cot" if "dostawne" in kind.lower() else "playpen"
        return "sleep_and_relax", {"travel_cot":"travel_cots","bedside_cot":"bedside_cots","playpen":"playpens"}[group], group, "yes", "", confidence, bool(review), "; ".join(review)
    if tab == "BUJACZKI":
        group = "cradle" if "kołysk" in kind.lower() or "łóżeczko" in kind.lower() else "classic_high_chair" if "krzesełko" in kind.lower() else "rocker"
        if ";" in kind or config == "Set": secondary = "; ".join(x.strip() for x in kind.split(";")[1:]) or "zestaw"
        return ("feeding", "high_chairs", group, "yes", secondary, "medium" if secondary else confidence, bool(review or secondary), "; ".join(filter(None, [*review, "produkt wielofunkcyjny" if secondary else ""]))) if group == "classic_high_chair" else ("sleep_and_relax", "cradles" if group == "cradle" else "rockers", group, "yes", secondary, "medium" if secondary else confidence, bool(review or secondary), "; ".join(filter(None, [*review, "produkt wielofunkcyjny" if secondary else ""])))
    if tab == "KRZESEŁKA":
        group = "kitchen_helper" if "pomocnik" in kind.lower() else "growing_high_chair" if "rosnące" in l2.lower() or "rosnące" in kind.lower() else "classic_high_chair"
        secondary = "; ".join(x.strip() for x in kind.split(";")[1:]) if ";" in kind else ""
        return "feeding", "kitchen_helpers" if group == "kitchen_helper" else "high_chairs", group, "yes", secondary, "medium" if secondary else confidence, bool(review or secondary), "; ".join(filter(None, [*review, "produkt wielofunkcyjny" if secondary else ""]))
    if tab == "LAKTATORY": return "feeding", "breast_pumps", "hands_free_breast_pump" if "hands-free" in kind.lower() else "electric_breast_pump", "yes", "double" if "Duo" in config else "", confidence, bool(review), "; ".join(review)
    if tab == "KOLEKTORY": return "feeding", "lactation_accessories", "milk_collector", "later", "manual_pump" if "laktator" in kind.lower() else "", "medium", True, "produkt mieszany: kolektor/laktator ręczny" if "laktator" in kind.lower() else "niski priorytet benchmarku"
    if tab in {"PODGRZEWACZE", "PODGRZEWACZE_PRZENOSNE", "STERYLIZATORY_SUSZARKI"}:
        group = "wipe_warmer" if "chusteczek" in spec_type or "chusteczek" in kind_normalized else "portable_bottle_warmer" if "przenośny" in spec_type or "przenośny" in kind_normalized or "przenośne" in collection_normalized else "sterilizer_warmer" if "steryliz" in spec_type or "steryliz" in kind_normalized else "countertop_bottle_warmer"
        subcategory = {"wipe_warmer": "wipe_warmers", "portable_bottle_warmer": "portable_bottle_warmers", "sterilizer_warmer": "sterilizers_and_dryers", "countertop_bottle_warmer": "bottle_warmers"}[group]
        return "feeding", subcategory, group, "yes", "", confidence, bool(review), "; ".join(review)
    if tab == "EKSPRESY_DO_WODY": return "feeding", "water_and_formula_makers", "water_formula_maker", "yes", "", confidence, bool(review), "; ".join(review)
    if tab == "ROBOTY_KUCHENNE": return "feeding", "food_processors", "baby_food_processor", "yes", "", "medium", True, "grupa jednoelementowa"
    if tab == "NIANIE_ELEKTRYCZNE":
        kind_monitor, reception = normalize(spec.get("Rodzaj niani")), normalize(spec.get("Sposób odbioru"))
        group = "audio_baby_monitor" if kind_monitor == "audio" else "video_app_baby_monitor" if "monitor" in reception and "aplikacja" in reception else "app_baby_monitor" if "aplikacja" in reception else "video_baby_monitor"
        return "monitoring_and_health", "baby_monitors", group, "yes", "", "high", bool(review), "; ".join(review)
    if tab == "ASPIRATORY": return "monitoring_and_health", "nasal_aspirators", "nasal_aspirator", "yes", "", "medium", True, "grupa jednoelementowa"
    if tab == "NEBULIZATORY": return "monitoring_and_health", "nebulizers", "nebulizer", "yes", "", "medium", True, "grupa jednoelementowa"
    if tab == "TERMOMETRY": return "monitoring_and_health", "thermometers", "thermometer", "yes", "", "medium", True, "grupa jednoelementowa"
    if tab == "WAGA": return "monitoring_and_health", "baby_scales", "baby_scale", "yes", "", "medium", True, "grupa jednoelementowa"
    if tab == "BRAMKI_OCHRONNE": return "home_safety", "safety_gates", "safety_gate", "yes", "", confidence, bool(review), "; ".join(review)
    if tab == "BARIERKI_DO_ŁÓŻKA": return "home_safety", "bed_rails", "bed_rail", "yes", "", confidence, bool(review), "; ".join(review)
    if tab == "ROWERKI": return "play_and_ride", "balance_bikes", "balance_bike", "yes", "", confidence, bool(review), "; ".join(review)
    if tab == "TRÓJKOŁOWCE": return "play_and_ride", "tricycles", "tricycle", "yes", "", confidence, bool(review), "; ".join(review)
    if tab == "HULAJNOGI":
        group = "child_helmet" if "kask" in kind.lower() else "stunt_scooter" if "wyczynowa" in kind.lower() else "balance_scooter"
        return "play_and_ride", "helmets" if group == "child_helmet" else "scooters", group, "yes", "", confidence, bool(review), "; ".join(review)
    return "accessories", "general_accessories", "care_accessory", "no", "", "low", True, "brak reguły klasyfikacji"


def candidates(group: str) -> list[tuple[str, str, str]]:
    sets = {
        "light_stroller": [("masa", "Waga produktu (kg)", "core"), ("wymiary po złożeniu", "Wymiary", "core"), ("koła", "Koła", "core"), ("amortyzacja", "Amortyzacja", "core"), ("udźwig", "Maksymalne obciążenie", "core"), ("budka", "Budka", "useful")],
        "standard_stroller": [("masa", "Waga produktu (kg)", "core"), ("wymiary", "Wymiary", "core"), ("koła", "Koła", "core"), ("amortyzacja", "Amortyzacja", "core"), ("siedzisko", "Siedzisko", "core"), ("udźwig", "Maksymalne obciążenie", "useful")],
        "audio_baby_monitor": [("typ transmisji", "Rodzaj niani", "core"), ("sposób odbioru", "Sposób odbioru", "core"), ("zasięg", "Zasięg (m)", "core"), ("VOX", "Tryb VOX", "useful"), ("rozmowa dwukierunkowa", "Rozmowa dwukierunkowa", "useful"), ("czas pracy", "Czas pracy", "useful")],
        "video_baby_monitor": [("przekątna ekranu", "Przekątna ekranu", "core"), ("rozdzielczość kamery", "Rozdzielczość obrazu", "core"), ("zasięg", "Zasięg (m)", "core"), ("tryb nocny", "Tryb nocny", "core"), ("rozmowa dwukierunkowa", "Rozmowa dwukierunkowa", "useful"), ("obsługa kamer", "Obsługa dodatkowych kamer", "useful")],
        "app_baby_monitor": [("typ transmisji", "Rodzaj niani", "core"), ("aplikacja", "Sposób odbioru", "core"), ("zasięg", "Zasięg (m)", "core"), ("tryb nocny", "Tryb nocny", "useful"), ("wykrywanie ruchu", "Wykrywanie ruchu", "useful"), ("powiadomienia", "Dodatkowe funkcje", "useful")],
        "video_app_baby_monitor": [("przekątna ekranu", "Przekątna ekranu", "core"), ("rozdzielczość kamery", "Rozdzielczość obrazu", "core"), ("monitor i aplikacja", "Sposób odbioru", "core"), ("zasięg", "Zasięg (m)", "core"), ("tryb nocny", "Tryb nocny", "useful"), ("wykrywanie ruchu", "Wykrywanie ruchu", "useful")],
        "hands_free_breast_pump": [("pojedynczy lub podwójny", "Pojedynczy / podwójny", "core"), ("liczba trybów", "Tryby pracy", "core"), ("liczba poziomów", "Poziomy mocy", "core"), ("pojemność", "Pojemność", "core"), ("poziom hałasu", "Poziom hałasu", "useful"), ("czas pracy baterii", "Czas pracy", "useful")],
        "electric_breast_pump": [("pojedynczy lub podwójny", "Pojedynczy / podwójny", "core"), ("tryby stymulacji i odciągania", "Tryby pracy", "core"), ("poziomy mocy", "Poziomy mocy", "core"), ("zasilanie", "Typ zasilania", "core"), ("system zamknięty", "Dodatkowe funkcje", "useful"), ("kompatybilność butelek", "Akcesoria", "useful")],
        "milk_collector": [("pojemność kolektora", "Pojemność", "core"), ("materiał kontaktowy", "Materiały", "core"), ("sposób mocowania", "Konstrukcja", "core"), ("zawartość zestawu", "Akcesoria", "useful"), ("możliwość sterylizacji", "Czyszczenie", "useful")],
        "diaper_disposal": [("pojemność kosza", "Pojemność", "core"), ("system uszczelniania", "Dodatkowe funkcje", "core"), ("kompatybilne wkłady", "Akcesoria", "core"), ("sposób otwierania", "Konstrukcja", "useful"), ("wymiary", "Wymiary", "useful")],
        "nasal_aspirator": [("rodzaj aspiratora", "Typ produktu", "core"), ("moc ssania", "Moc ssania", "core"), ("liczba poziomów", "Poziomy mocy", "core"), ("liczba końcówek", "Końcówki", "useful"), ("zasilanie", "Typ zasilania", "useful"), ("mycie elementów", "Czyszczenie", "useful")],
        "countertop_bottle_warmer": [("liczba butelek", "Liczba butelek jednocześnie", "core"), ("zakres temperatur", "Zakres / poziomy temperatury", "core"), ("czas podgrzewania", "Szybkość podgrzewania", "core"), ("utrzymywanie temperatury", "Funkcja utrzymywania temperatury", "core"), ("zabezpieczenie", "Zabezpieczenie przed przegrzaniem", "useful"), ("zasilanie", "Typ zasilania", "useful")],
        "portable_bottle_warmer": [("pojemność akumulatora", "Pojemność akumulatora", "core"), ("czas podgrzewania", "Szybkość podgrzewania", "core"), ("zakres temperatur", "Zakres / poziomy temperatury", "core"), ("zasilanie", "Typ zasilania", "core"), ("masa", "Waga", "useful"), ("wymiary", "Wymiary", "useful")],
        "wipe_warmer": [("pojemność", "Pojemność", "core"), ("utrzymanie wilgotności", "Dodatkowe funkcje", "core"), ("utrzymanie temperatury", "Dodatkowe funkcje", "core"), ("lampka nocna", "Dodatkowe funkcje", "useful"), ("zasilanie", "Typ zasilania", "useful")],
    }
    if group in sets: return sets[group]
    if group in {"stroller_accessory", "car_seat_accessory", "monitor_accessory", "feeding_consumable", "care_accessory", "baby_blanket", "swaddle_and_muslin", "baby_bedding", "bath_textile"}: return []
    if group == "stroller_2in1": return [("elementy zestawu 2w1", "Konfiguracja", "core"), ("typ gondoli", "Gondola", "core"), ("siedzisko spacerowe", "Siedzisko", "core"), ("masa stelaża", "Waga produktu", "core"), ("koła i amortyzacja", "Koła", "core"), ("składanie stelaża", "Składanie", "useful")]
    if group == "stroller_3in1": return [("elementy zestawu 3w1", "Konfiguracja", "core"), ("typ gondoli", "Gondola", "core"), ("siedzisko spacerowe", "Siedzisko", "core"), ("fotelik w zestawie", "Adaptery lub fotelik", "core"), ("masa stelaża", "Waga produktu", "useful"), ("koła i amortyzacja", "Koła", "useful")]
    if group in {"infant_car_seat", "extended_rwf_car_seat", "toddler_car_seat", "high_back_booster"}:
        specific = {"infant_car_seat": "wkładka niemowlęca", "extended_rwf_car_seat": "maksymalny zakres RWF", "toddler_car_seat": "zakres jazdy przodem", "high_back_booster": "prowadzenie pasa"}[group]
        return [("zakres wzrostu", "Zakres wzrostu", "core"), ("kierunek jazdy", "RWF/FF", "core"), ("sposób montażu", "Sposób montażu", "core"), ("norma bezpieczeństwa", "Homologacja", "core"), (specific, "Specyfikacja grupy", "useful"), ("masa", "Waga produktu", "useful")]
    if group in {"travel_cot", "bedside_cot", "playpen", "cradle"}:
        specific = {"travel_cot": "torba transportowa", "bedside_cot": "mocowanie do łóżka", "playpen": "funkcja kojca", "cradle": "mechanizm kołysania"}[group]
        return [("wymiary", "Wymiary", "core"), ("masa", "Waga produktu", "core"), ("sposób składania", "Składanie", "core"), ("materac", "Materac", "core"), (specific, "Specyfikacja grupy", "useful"), ("mobilność", "Kółka lub torba", "useful")]
    if group in {"rocker", "classic_high_chair", "growing_high_chair", "kitchen_helper"}:
        specific = {"rocker": "funkcja bujania", "classic_high_chair": "pozycja do karmienia", "growing_high_chair": "regulacja wraz ze wzrostem", "kitchen_helper": "platforma pomocnika"}[group]
        return [("zakres użytkowania", "Wiek lub obciążenie", "core"), ("regulacja", "Regulacja", "core"), ("pasy bezpieczeństwa", "Pasy", "core"), ("tacka lub pałąk", "Wyposażenie", "core"), (specific, "Specyfikacja grupy", "useful"), ("materiał", "Materiały", "useful")]
    if group in {"water_formula_maker", "baby_food_processor", "sterilizer_warmer"}:
        specific = {"water_formula_maker": "dozowanie wody", "baby_food_processor": "blendowanie i gotowanie", "sterilizer_warmer": "sterylizacja",}[group]
        return [("główna funkcja", "Typ produktu", "core"), ("pojemność", "Pojemność", "core"), ("programy", "Dodatkowe funkcje", "core"), ("czas działania", "Czas programu", "core"), (specific, "Specyfikacja grupy", "useful"), ("wymiary", "Wymiary", "useful")]
    if group in {"balance_bike", "tricycle", "balance_scooter", "stunt_scooter", "child_helmet"}:
        specific = {"balance_bike": "brak napędu", "tricycle": "pedały i prowadnik", "balance_scooter": "liczba kół", "stunt_scooter": "konstrukcja wyczynowa", "child_helmet": "obwód głowy i ochrona"}[group]
        return [("zakres wieku", "Wiek użytkownika", "core"), ("maksymalne obciążenie", "Maksymalne obciążenie", "core"), ("masa", "Waga produktu", "core"), ("regulacja", "Regulacja wysokości", "core"), (specific, "Specyfikacja grupy", "useful"), ("materiał", "Materiały", "useful")]
    if group in {"nasal_aspirator", "nebulizer", "thermometer", "baby_scale"}:
        specific = {"nasal_aspirator": "moc ssania", "nebulizer": "wielkość cząstek", "thermometer": "metoda pomiaru", "baby_scale": "dokładność ważenia"}[group]
        return [("typ urządzenia", "Typ produktu", "core"), ("zasilanie", "Typ zasilania", "core"), ("tryby pomiaru lub pracy", "Funkcje", "core"), (specific, "Specyfikacja grupy", "core"), ("akcesoria", "Zawartość zestawu", "useful"), ("czyszczenie", "Czyszczenie", "useful")]
    if group in {"safety_gate", "bed_rail"}:
        specific = "kierunek otwierania bramki" if group == "safety_gate" else "wysokość barierki"
        return [("zakres wymiarów", "Wymiary", "core"), ("sposób montażu", "Montaż", "core"), ("zabezpieczenie", "Mechanizm blokady", "core"), ("materiał", "Materiały", "core"), (specific, "Specyfikacja grupy", "useful"), ("certyfikacja", "Normy", "useful")]
    generic = [("wymiary", "Wymiary produktu", "core"), ("masa", "Waga produktu", "core"), ("materiały", "Materiały", "core"), ("funkcje", "Dodatkowe funkcje", "core"), ("bezpieczeństwo", "Certyfikacja lub zabezpieczenia", "core"), ("pielęgnacja", "Czyszczenie", "useful")]
    return generic


def group_rules(group: str) -> tuple[list[str], list[str]]:
    if group == "light_stroller": return (["samodzielny wózek spacerowy", "konstrukcja składana", "brak gondoli w podstawowej konfiguracji", "pozycjonowanie lekkie, kompaktowe lub podróżne"], ["zestaw 2w1 albo 3w1", "wózek bliźniaczy", "sama rama, gondola lub akcesorium"])
    if group in {"stroller_2in1", "stroller_3in1"}: return (["zestaw wózka z gondolą i spacerówką", "konfiguracja odpowiada oznaczeniu grupy"], ["samodzielna spacerówka", "akcesorium lub część zamienna"])
    if group in {"audio_baby_monitor", "video_baby_monitor", "app_baby_monitor", "video_app_baby_monitor"}: return (["rodzaj niani i sposób odbioru zgodne z grupą", "urządzenie służy do monitorowania dziecka"], ["kamera lub odbiornik sprzedawane jako samodzielne akcesorium", "inny rodzaj transmisji"])
    if group == "wipe_warmer": return (["produkt ogrzewa lub utrzymuje wilgotność chusteczek"], ["podgrzewacz do butelek", "sterylizator bez funkcji chusteczek"])
    if group in {"countertop_bottle_warmer", "portable_bottle_warmer", "sterilizer_warmer"}: return (["produkt podgrzewa butelki lub pokarm", "funkcje zgodne z mobilnym, stacjonarnym lub sterylizującym zastosowaniem"], ["podgrzewacz do chusteczek", "ekspres do wody"])
    if group.endswith("accessory") or group in {"feeding_consumable", "diaper_disposal"}: return (["produkt należy do wskazanego systemu akcesoriów lub materiałów eksploatacyjnych"], ["samodzielny produkt główny innej kategorii"])
    if group in {"baby_blanket", "swaddle_and_muslin", "baby_bedding", "bath_textile"}: return (["typ tekstyliów odpowiada funkcji snu, otulania, łóżeczka lub kąpieli"], ["akcesorium techniczne do innego produktu", "tekstylia o innym zastosowaniu"])
    return (["podstawowe zastosowanie produktu odpowiada nazwie i definicji grupy", "produkt jest samodzielnym wyrobem konsumenckim"], ["akcesorium dedykowane innemu produktowi", "produkt o innym podstawowym zastosowaniu"])


def main() -> int:
    global OUTPUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--spec-xlsx", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Directory for the four generated taxonomy artifacts.")
    args = parser.parse_args()
    OUTPUT = args.output.resolve()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("Pusty inventory CSV.")
    specification = load_specification(args.spec_xlsx)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    classified = []
    for row in rows:
        spec = specification.get((row["source_tab"], normalize(row.get("model") or row.get("product_name"))), {})
        category, subcategory, group, benchmarkable, secondary, confidence, review, reason = classify(row, spec)
        value = dict(row)
        value.update({
            "category_key": category, "category_label_pl": CATEGORY_LABELS[category],
            "subcategory_key": subcategory, "subcategory_label_pl": SUBCATEGORY_LABELS[subcategory],
            "benchmark_group_key": group, "benchmark_group_label_pl": GROUPS[group][0],
            "benchmarkable": benchmarkable, "secondary_functions": secondary,
            "classification_confidence": confidence, "review_required": str(review).lower(), "review_reason": reason,
        })
        classified.append(value)
    # The source inventory already has placeholder category_key and
    # benchmark_group columns. Keep the original positions but never emit
    # duplicate CSV headers.
    fields = list(dict.fromkeys([*rows[0], *EXTRA_COLUMNS]))
    with (OUTPUT / "FIELDNOTE_product_inventory_classified.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(classified)
    group_rows = defaultdict(list)
    for row in classified: group_rows[row["benchmark_group_key"]].append(row)
    registry = {"categories": []}
    categories = defaultdict(lambda: defaultdict(list))
    benchmark_rows = []
    attr_rows = []
    for group, members in sorted(group_rows.items()):
        sample = members[0]; category = sample["category_key"]; subcategory = sample["subcategory_key"]
        definition = GROUPS[group][1]; tabs = sorted({r["source_tab"] for r in members})
        warning = len(members) == 1
        include_rules, exclude_rules = group_rules(group)
        group_benchmarkable = "yes" if any(r["benchmarkable"] == "yes" for r in members) else "later" if any(r["benchmarkable"] == "later" for r in members) else "no"
        group_data = {"key": group, "label_pl": GROUPS[group][0], "definition": definition,
                      "include_when": include_rules, "exclude_when": exclude_rules,
                      "lionelo_product_count": len(members), "benchmarkable": group_benchmarkable == "yes"}
        categories[category][subcategory].append(group_data)
        benchmark_rows.append({"category_key":category,"subcategory_key":subcategory,"benchmark_group_key":group,"benchmark_group_label_pl":GROUPS[group][0],"definition":definition,"include_rules":"; ".join(include_rules),"exclude_rules":"; ".join(exclude_rules),"lionelo_product_count":len(members),"benchmarkable":group_benchmarkable,"group_size_warning":str(warning).lower(),"source_tabs":"; ".join(tabs),"review_required":str(warning or any(r["review_required"] == "true" for r in members)).lower()})
        for attribute, source, importance in candidates(group): attr_rows.append({"benchmark_group_key":group,"attribute_candidate":attribute,"source_column_or_reason":source,"importance":importance,"publicly_researchable":"yes","notes":"kandydat oparty o XLSX lub potrzebę porównawczą"})
    for category, subcategories in sorted(categories.items()):
        registry["categories"].append({"key":category,"label_pl":CATEGORY_LABELS[category],"subcategories":[{"key":sub,"label_pl":SUBCATEGORY_LABELS[sub],"benchmark_groups":groups} for sub,groups in sorted(subcategories.items())]})
    (OUTPUT / "category_registry.json").write_text(json.dumps(registry, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for filename, rows_out, headers in [("benchmark_groups.csv",benchmark_rows,list(benchmark_rows[0])), ("benchmark_attribute_candidates.csv",attr_rows,list(attr_rows[0]))]:
        with (OUTPUT / filename).open("w",encoding="utf-8",newline="") as handle:
            writer=csv.DictWriter(handle,fieldnames=headers); writer.writeheader(); writer.writerows(rows_out)
    print(f"products={len(classified)}")
    print(f"categories={len(categories)}")
    print(f"benchmark_groups={len(group_rows)}")
    print(f"review_required={sum(r['review_required']=='true' for r in classified)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
