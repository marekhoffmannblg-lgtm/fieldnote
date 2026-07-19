from __future__ import annotations

import re
from urllib.parse import urlencode

import streamlit as st

from services.integrations import integration_statuses
from services.pipeline_runner import run_pipeline
from ui.components import hero, offer_metrics, result_metrics, stepper
from ui.state import current_data, integer, model_by_key, model_name, set_query, switch


STEPS = ("Produkt", "Integracje", "Sprawdzenie ofert", "Potwierdzenie", "Realizacja", "Wynik")


def current_step() -> int:
    try:
        return max(1, min(6, int(st.query_params.get("research_step", "1"))))
    except ValueError:
        return 1


def go(step: int, brand: str, model: str) -> None:
    origin = {key: str(st.query_params.get(key, "")) for key in ("from", "from_product", "catalog_q", "catalog_status", "catalog_brand") if str(st.query_params.get(key, ""))}
    st.query_params.clear()
    st.query_params.update({"research_step": str(step), "brand": brand, "model": model, **origin})
    switch("research")


def integration_page(brand: str, model: str) -> None:
    origin = {key: str(st.query_params.get(key, "")) for key in ("from", "from_product", "catalog_q", "catalog_status", "catalog_brand") if str(st.query_params.get(key, ""))}
    set_query(return_to="research", research_step="2", brand=brand, model=model, **origin)
    switch("integrations")


def sample_titles(data: dict, brand: str, model: str) -> list[str]:
    model_lower = model.lower()
    titles: list[str] = []
    for model_item in data["models"]:
        if model_item["brand"].lower() == brand.lower() and model_lower in model_item["model"].lower():
            titles.append(model_name(model_item))
    return titles[:3]


data = current_data()
hero("Nowy research", "Uzupełnij dane produktu", "Kreator prowadzi krok po kroku: najpierw sprawdzasz oferty, a dopiero potem potwierdzasz zmianę danych.")
step = current_step()
stepper(step, STEPS)
brand_default = str(st.query_params.get("brand", "Kinderkraft"))
model_default = str(st.query_params.get("model", ""))

if step == 1:
    st.subheader("1. Wybierz produkt")
    choice = st.radio("Skąd chcesz rozpocząć?", ("Wybieram produkt z katalogu", "Wpisuję nową markę i model"), horizontal=True)
    if choice.startswith("Wybieram") and data["models"]:
        labels = {model_name(item): item for item in data["models"]}
        selected = st.selectbox("Produkt", tuple(labels), index=next((index for index, label in enumerate(labels) if label.lower() == f"{brand_default} {model_default}".lower()), 0))
        item = labels[selected]
        brand, model = item["brand"], item["model"]
    else:
        brand = st.text_input("Marka", value=brand_default, max_chars=80)
        model = st.text_input("Model", value=model_default, max_chars=100)
    left, right = st.columns([1, 1])
    from_product = str(st.query_params.get("from_product", ""))
    if from_product:
        catalog_context = {key.removeprefix("catalog_"): str(st.query_params.get(key, "")) for key in ("catalog_q", "catalog_status", "catalog_brand") if str(st.query_params.get(key, ""))}
        product_href = f"/produkt?{urlencode({'product': from_product, **catalog_context})}"
        left.link_button("Wróć do produktu", product_href, width="stretch")
    if right.button("Dalej: sprawdź integracje", type="primary", width="stretch"):
        if not brand.strip() or not model.strip():
            st.error("Podaj markę i model produktu.")
        else:
            go(2, brand.strip(), model.strip())

elif step == 2:
    st.subheader("2. Sprawdź integracje")
    statuses = integration_statuses()
    for slug, entry in statuses.items():
        item = entry["integration"]
        left, right = st.columns([4, 1])
        left.markdown(f"**{item.label}**  \\n{item.description}")
        right.markdown("✅ Połączono" if entry["connected"] else "⚪ Niepołączono")
        if entry["error"]:
            st.warning(entry["error"])
    firecrawl_ready = bool(statuses["firecrawl"]["connected"])
    if not firecrawl_ready:
        st.info("Aby sprawdzić nowe oferty, podłącz integrację do pobierania ofert. Klucz zapiszesz lokalnie w systemowym magazynie haseł.")
        if st.button("Podłącz integrację", type="primary"):
            integration_page(brand_default, model_default)
    previous, next_button = st.columns(2)
    if previous.button("Wstecz", width="stretch"):
        go(1, brand_default, model_default)
    if next_button.button("Dalej: sprawdź oferty", type="primary", width="stretch", disabled=not firecrawl_ready):
        go(3, brand_default, model_default)

elif step == 3:
    st.subheader("3. Sprawdź dostępne oferty")
    st.write("To bezpieczny podgląd. Nie pobiera kart ofert i nie zmienia benchmarku.")
    if st.button("Sprawdź dostępne oferty", type="primary"):
        progress = st.progress(0, text="Sprawdzam oferty…")
        output: list[str] = []
        result: dict[str, str] = {}
        for label, lines, final in run_pipeline(brand_default, model_default, "preview"):
            output = lines
            if final:
                result = final
            else:
                progress.progress(min(90, 15 + len(output) * 2), text=label)
        progress.progress(100, text="Sprawdzenie zakończone")
        st.session_state["research_preview"] = result
        st.session_state["research_preview_log"] = "\n".join(output)
    preview = st.session_state.get("research_preview", {})
    if isinstance(preview, dict) and preview:
        if preview.get("pipeline_status") == "preview":
            st.success("Sprawdzenie ofert zakończone. Benchmark nie został zmieniony.")
            offer_metrics(preview)
            examples = sample_titles(data, brand_default, model_default)
            if examples:
                st.caption("Przykładowe pasujące produkty: " + " · ".join(examples))
            if st.button("Dalej: potwierdź pobranie danych", type="primary"):
                go(4, brand_default, model_default)
        else:
            st.error(preview.get("error") or "Nie udało się sprawdzić ofert. Sprawdź integrację lub spróbuj ponownie.")
    if st.button("Wstecz", key="research-back-preview"):
        go(2, brand_default, model_default)

elif step == 4:
    st.subheader("4. Potwierdź zakres zmian")
    preview = st.session_state.get("research_preview", {})
    new_offers = integer(preview.get("new_offers", 0)) if isinstance(preview, dict) else 0
    statuses = integration_statuses()
    st.markdown(f'<div class="action"><strong>Do pobrania: {new_offers} ofert.</strong><br>Research użyje pobierania ofert: <strong>tak</strong>. Analiza AI: <strong>{"tak" if statuses["openai"]["connected"] else "nie"}</strong>. Zaktualizowane mogą zostać źródła, dane modelu i poziom pokrycia.</div>', unsafe_allow_html=True)
    with st.expander("Opcje zaawansowane"):
        skip_ai = st.checkbox("Pomiń analizę AI", value=not bool(statuses["openai"]["connected"]), help="Dane ofert zostaną pobrane i uporządkowane, ale pola benchmarku nie będą analizowane przez AI.")
    st.session_state["research_skip_ai"] = skip_ai
    previous, next_button = st.columns(2)
    if previous.button("Wstecz", width="stretch"):
        go(3, brand_default, model_default)
    if next_button.button("Pobierz i przeanalizuj dane", type="primary", width="stretch"):
        go(5, brand_default, model_default)

elif step == 5:
    st.subheader("5. Realizacja")
    stages = ["Szukanie ofert", "Dodawanie nowych ofert", "Pobieranie stron", "Porządkowanie danych", "Aktualizacja źródeł", "Aktualizacja produktu", "Analiza AI", "Budowa benchmarku", "Raport pokrycia"]
    placeholders = [st.empty() for _ in stages]
    progress = st.progress(0, text="Przygotowuję research…")
    logs: list[str] = []
    final_result: dict[str, str] = {}
    for label, lines, result in run_pipeline(brand_default, model_default, "apply", bool(st.session_state.get("research_skip_ai", False))):
        logs = lines
        match = re.match(r"\[(\d+)/9\]", label)
        if match:
            active = int(match.group(1))
            for index, placeholder in enumerate(placeholders, start=1):
                state = "✅ zakończono" if index < active else "🔄 trwa" if index == active else "○ oczekuje"
                placeholder.write(f"{state} — {stages[index - 1]}")
            progress.progress(active * 11, text=label)
        if result:
            final_result = result
    progress.progress(100, text="Proces zakończony")
    st.session_state["research_result"] = final_result
    st.session_state["research_log"] = "\n".join(logs)
    go(6, brand_default, model_default)

else:
    st.subheader("6. Wynik")
    result = st.session_state.get("research_result", {})
    if not isinstance(result, dict) or not result:
        st.info("Nie zapisano wyniku w tej sesji. Otwórz Uruchomienia, aby sprawdzić trwałą historię procesów.")
    elif result.get("pipeline_status") == "success":
        st.success("Research zakończył się poprawnie. Dane produktu zostały odświeżone.")
        result_metrics(result)
    elif result.get("pipeline_status") == "partial":
        st.warning("Research zakończył się częściowo. Pobrane oferty zostały przetworzone, ale część wymaga ponowienia.")
        result_metrics(result)
    else:
        st.error(result.get("error") or "Research nie został ukończony. Otwórz Uruchomienia, aby sprawdzić etap i bezpieczną akcję naprawczą.")
        result_metrics(result)
    with st.expander("Szczegóły techniczne"):
        st.code(st.session_state.get("research_log", "Brak dodatkowych szczegółów."), language="text")
    action_one, action_two, action_three = st.columns(3)
    fresh = current_data()
    selected = next((item for item in fresh["models"] if item["brand"].lower() == brand_default.lower() and item["model"].lower() == model_default.lower()), None)
    if selected:
        action_one.link_button("Otwórz produkt", f"/produkt?product={selected['group_key']}", type="primary", width="stretch")
    else:
        action_one.info("Produkt będzie widoczny po odświeżeniu danych.")
    action_two.link_button("Zobacz uruchomienia", "/runs", width="stretch")
    action_three.link_button("Kolejny research", "/research?research_step=1&brand=Kinderkraft", width="stretch")
