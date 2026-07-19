from __future__ import annotations

import streamlit as st

from ui.components import catalog_chip, coverage, hero
from ui.state import catalog_status_label, current_data, model_name, switch


data = current_data()
models = data["models"]
hero("Produkty", "Katalog produktów", "Wyszukaj model, sprawdź poziom pokrycia i otwórz tylko te dane, których potrzebujesz.")
if not models:
    st.info("Katalog jest pusty. Rozpocznij research, aby dodać pierwsze produkty i źródła.")
    if st.button("Rozpocznij research", type="primary"):
        switch("research")
    st.stop()

statuses = {"Wszystkie": "", **{catalog_status_label(value): value for value in ("ready", "analyzed_no_coverage", "waiting_for_analysis", "no_sources")}}
first, second, third = st.columns(3)
query = first.text_input("Szukaj marki lub modelu", value=st.query_params.get("q", ""), placeholder="np. Kinderkraft NEBO")
status_label = second.selectbox("Status", tuple(statuses), index=list(statuses).index(next((label for label, value in statuses.items() if value == st.query_params.get("status", "")), "Wszystkie")))
brands = ("Wszystkie", *sorted({str(model["brand"]) for model in models}))
brand = third.selectbox("Marka", brands, index=brands.index(st.query_params.get("brand", "Wszystkie")) if st.query_params.get("brand", "Wszystkie") in brands else 0)
st.query_params.update({"q": query, "status": statuses[status_label], "brand": brand})

filtered = [model for model in models if (not query or query.lower() in model_name(model).lower()) and (not statuses[status_label] or model["catalog_status"] == statuses[status_label]) and (brand == "Wszystkie" or model["brand"] == brand)]
st.caption(f"{len(filtered)} z {len(models)} produktów spełnia wybrane kryteria.")
if not filtered:
    st.info("Nie znaleziono produktu dla tych filtrów. Wyczyść wyszukiwanie albo wybierz inny status.")

for start in range(0, len(filtered), 3):
    columns = st.columns(3, gap="medium")
    for column, model in zip(columns, filtered[start:start + 3]):
        with column:
            st.markdown(f'<div class="card product-card">{catalog_chip(model["catalog_status"])}<h3>{model_name(model)}</h3><div class="meta">{model["marketplace"]} · {model["sources_total"]} źródeł · braki: {model["fields_x"] if model["fields_x"] is not None else "—"}</div></div>', unsafe_allow_html=True)
            coverage(model["coverage_percent"] or 0)
            st.link_button("Otwórz produkt", f"/produkt?product={model['group_key']}&q={query}&status={statuses[status_label]}&brand={brand}", type="primary", width="stretch")
