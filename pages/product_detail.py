from __future__ import annotations

from urllib.parse import urlencode

import streamlit as st

from ui.components import catalog_chip, coverage, field_chip, hero, kpis, run_chip
from ui.state import current_data, field_rows, model_by_key, model_name, model_sources, status_label


data = current_data()
group_key = str(st.query_params.get("product", ""))
model = model_by_key(data, group_key)
catalog_params = {key: str(st.query_params.get(key, "")) for key in ("q", "status", "brand") if str(st.query_params.get(key, ""))}
catalog_query = "&".join(f"{key}={value}" for key, value in catalog_params.items())
catalog_href = f"/products?{catalog_query}" if catalog_query else "/products"
if not model:
    hero("Produkty", "Nie znaleziono produktu", "Link nie wskazuje produktu dostępnego w aktualnym katalogu.")
    st.link_button("Wróć do produktów", catalog_href, type="primary")
    st.stop()
context = data["contexts"][group_key]
breadcrumb_left, breadcrumb_right = st.columns([1, 7])
breadcrumb_left.link_button("Produkty", catalog_href, type="secondary")
breadcrumb_right.markdown(f'<div class="breadcrumb">/ {model["brand"]} / {model["model"]}</div>', unsafe_allow_html=True)
st.link_button("← Wróć do produktów", catalog_href, type="secondary")
hero("Produkt", model_name(model), "Sprawdź wynik benchmarku, źródła oraz pola wymagające kolejnego researchu.")
first, second, third = st.columns([3, 1, 1])
first.markdown(catalog_chip(model["catalog_status"]), unsafe_allow_html=True)
research_params = {"research_step": "1", "brand": model["brand"], "model": model["model"], "from": "product", "from_product": model["group_key"], **{f"catalog_{key}": value for key, value in catalog_params.items()}}
second.link_button("Uzupełnij dane", f"/research?{urlencode(research_params)}", type="primary", width="stretch")
third.link_button("Porównaj", f"/compare?primary={model['group_key']}", width="stretch")
kpis([
    ("Poziom pokrycia", f"{float(model['coverage_percent'] or 0):.1f}%", "potwierdzone pola"),
    ("Źródła", model["sources_total"], model["marketplace"]),
    ("Potwierdzone", model["fields_confirmed"] if model["fields_confirmed"] is not None else "—", "pola benchmarku"),
    ("Braki", model["fields_x"] if model["fields_x"] is not None else "—", "brak potwierdzenia"),
])

summary_tab, data_tab, sources_tab, gaps_tab, history_tab = st.tabs(("Podsumowanie", "Dane produktu", "Źródła", "Braki i konflikty", "Historia researchu"))
rows = field_rows(context)
with summary_tab:
    attention = [row for row in rows if row["value"] == "X" or row["status"] in {"open", "conflicting"} or row["confidence"] == "low"]
    if attention:
        st.warning(f"{len(attention)} pól wymaga jeszcze decyzji lub dodatkowego potwierdzenia.")
        st.markdown(" · ".join(row["field"] for row in attention[:8]))
    else:
        st.success("Wszystkie pola mają potwierdzone wartości.")
    coverage(model["coverage_percent"] or 0)
with data_tab:
    sections = {
        "Podstawowe informacje": ("Marka", "Model", "Status"), "Konstrukcja i składanie": ("Rama", "Auto-folding", "Składanie jedną ręką", "Regulacja rączki"), "Koła i prowadzenie": ("Koła", "Koła 360°", "Amortyzacja", "Hamulec"), "Siedzisko i komfort": ("Siedzisko", "Regulacja oparcia"), "Budka i ochrona": ("Budka XXL", "Filtr UPF50+", "Wodoodporna budka"), "Wymiary": ("Waga", "Udźwig", "Wymiary po złożeniu", "Wymiary oparcia / miejsce do spania"), "Akcesoria": ("Akcesoria",),
    }
    field_filter = st.selectbox("Pokaż pola", ("Wszystkie", "Potwierdzone", "Sprzeczne źródła", "Wymagające sprawdzenia", "Brak danych"))
    filter_status = {
        "Wszystkie": lambda row: True,
        "Potwierdzone": lambda row: row["status"] == "confirmed" and row["value"] != "X",
        "Sprzeczne źródła": lambda row: row["status"] == "conflicting",
        "Wymagające sprawdzenia": lambda row: row["status"] in {"open", "unclear"},
        "Brak danych": lambda row: row["value"] == "X",
    }[field_filter]
    for section, names in sections.items():
        values = [row for row in rows if row["field"] in names and filter_status(row)]
        if not values:
            continue
        with st.expander(section, expanded=section == "Podstawowe informacje"):
            for row in values:
                confidence_label = {"high": "wysoka", "medium": "średnia", "low": "niska"}.get(row["confidence"], "niska")
                first, second = st.columns([4, 1])
                with first:
                    st.markdown(f"**{row['field']}**  \n{'Brak danych' if row['value'] == 'X' else row['value']}")
                    st.caption(f"{status_label(row['status'], row['value'])} · pewność: {confidence_label} · {len(row['evidence'])} źródeł")
                with second:
                    st.markdown(field_chip(row["status"], row["value"]), unsafe_allow_html=True)
                with st.expander("Źródła i dowody"):
                    if not row["evidence"]:
                        st.info("Nie ma zapisanego fragmentu źródłowego. Pole pozostaje bez potwierdzenia.")
                    else:
                        grouped: dict[str, list[dict]] = {}
                        for evidence in row["evidence"]:
                            grouped.setdefault(evidence.get("value") or row["value"], []).append(evidence)
                        for source_value, entries in grouped.items():
                            if row["status"] == "conflicting":
                                st.markdown(f"**Wartość: {source_value}**")
                            for evidence_index, evidence in enumerate(entries, start=1):
                                st.caption(f"{evidence.get('marketplace') or 'Źródło'} · oferta {evidence.get('external_offer_id') or '—'} · {evidence.get('source_id') or 'brak identyfikatora'}")
                                with st.expander("Pokaż fragment", expanded=False):
                                    st.write(evidence.get("evidence") or "Brak fragmentu źródłowego.")
                                if str(evidence.get("source_url", "")).startswith("http"):
                                    st.link_button("Otwórz źródło", evidence["source_url"], key=f"field-source-{row['field']}-{evidence.get('source_id')}-{evidence.get('external_offer_id')}-{evidence_index}")
with sources_tab:
    sources = model_sources(context)
    if not sources:
        st.info("Nie zapisano źródeł tego produktu.")
    for source in sources:
        with st.container(border=True):
            st.markdown(f"**{source.get('marketplace') or 'Nieznany serwis'}** · oferta `{source.get('external_offer_id') or '—'}`")
            if str(source.get("source_url", "")).startswith("http"):
                st.link_button("Otwórz źródło", source["source_url"])
    st.caption("Pełne dowody dla każdego pola są dostępne poniżej w sekcji Braki i konflikty.")
with gaps_tab:
    flagged = [row for row in rows if row["value"] == "X" or row["status"] in {"open", "conflicting"}]
    if not flagged:
        st.success("Brak otwartych pól i konfliktów.")
    for row in flagged:
        with st.expander(f"{row['field']} · {status_label(row['status'], row['value'])}"):
            st.markdown(field_chip(row["status"], row["value"]), unsafe_allow_html=True)
            if row["reason"]:
                st.caption(row["reason"])
            if not row["evidence"]:
                st.info("Sprawdzone źródła nie dostarczyły zwalidowanego potwierdzenia dla tego pola.")
            for evidence in row["evidence"]:
                st.write(evidence.get("evidence") or "Brak fragmentu źródłowego.")
                if str(evidence.get("source_url", "")).startswith("http"):
                    st.link_button("Otwórz źródło", evidence["source_url"], key=f"evidence-{row['field']}-{evidence.get('external_offer_id')}")
with history_tab:
    related = [run for run in data["runs"] if run.get("group_key") == group_key or (run.get("brand") == model["brand"] and run.get("model") == model["model"])]
    if not related:
        st.info("Nie ma jeszcze zapisanej historii researchu tego produktu.")
    for run in related:
        st.markdown(f"**{run.get('started_at', '—')}** · {run_chip(run.get('pipeline_status'))}", unsafe_allow_html=True)
        st.caption(f"Nowe oferty: {run.get('new_offers', '—')} · Pokrycie po: {run.get('coverage_after', '—')}%")
