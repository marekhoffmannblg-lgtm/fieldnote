from __future__ import annotations

import streamlit as st

from ui.components import coverage, hero
from ui.state import BENCHMARK_FIELDS, current_data, field_rows, model_name


data = current_data()
ready = [model for model in data["models"] if model["catalog_status"] == "ready"]
hero("Porównanie", "Porównaj modele", "Zestaw obok siebie wyłącznie gotowe benchmarki. Brak danych nie jest interpretowany jako brak cechy.")
if len(ready) < 2:
    st.info("Do porównania potrzebujesz co najmniej dwóch gotowych modeli.")
    st.stop()

labels = {model_name(model): model for model in ready}
primary_key = str(st.query_params.get("primary", ""))
primary_label = next((label for label, model in labels.items() if model["group_key"] == primary_key), "")
defaults = tuple([primary_label, *[label for label in labels if label != primary_label][:2]]) if primary_label else tuple(list(labels)[:min(3, len(labels))])
selected_labels = st.multiselect("Wybierz od 2 do 5 modeli", tuple(labels), default=defaults, max_selections=5)
show_differences = st.checkbox("Pokaż tylko pola różniące modele", value=False)
if len(selected_labels) < 2:
    st.info("Wybierz co najmniej dwa modele.")
    st.stop()

selected = [labels[label] for label in selected_labels]
columns = st.columns(len(selected))
for column, model in zip(columns, selected):
    with column:
        st.markdown(f"**{model_name(model)}**")
        coverage(model["coverage_percent"] or 0)
        st.caption(f"{model['sources_total']} źródeł · {model['fields_x'] or 0} braków")

by_model = {model["group_key"]: {row["field"]: row for row in field_rows(data["contexts"][model["group_key"]])} for model in selected}
table: list[dict[str, str]] = []
for field in BENCHMARK_FIELDS:
    values = [by_model[model["group_key"]][field]["value"] for model in selected]
    shown = ["Brak danych" if value == "X" else value for value in values]
    if show_differences and len(set(shown)) <= 1:
        continue
    row = {"Pole": field}
    row.update({model_name(model): value for model, value in zip(selected, shown)})
    table.append(row)
if not table:
    st.info("Wybrane modele nie mają różniących się pól przy aktualnym filtrze.")
else:
    st.dataframe(table, hide_index=True, width="stretch", column_config={"Pole": st.column_config.TextColumn("Pole", width="medium")})
