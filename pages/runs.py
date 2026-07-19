from __future__ import annotations

import streamlit as st

from ui.components import hero, kpis, run_chip, stage_timeline
from ui.state import current_data, run_status_label, switch


data = current_data()
runs = data["runs"]
hero("Uruchomienia", "Monitor researchu", "Zobacz wynik, etapy i błędy procesów bez szukania informacji w technicznym logu.")
queue_errors = [row for row in data["queue"] if row.get("status") == "error"]
kpis([
    ("Wszystkie", len(runs), "zapisane procesy"),
    ("Udane", sum(run.get("pipeline_status") == "success" for run in runs), "zakończone poprawnie"),
    ("Częściowe", sum(run.get("pipeline_status") == "partial" for run in runs), "wymagają uwagi"),
    ("Błędy pobrań", len(queue_errors), "można ponowić"),
])
if not runs:
    st.info("Nie ma jeszcze historii researchu. Podgląd ofert i pełny research zapiszą tu pierwszy proces.")
    st.stop()

statuses = ("Wszystkie", "Sukces", "Częściowy sukces", "Błąd", "Podgląd ofert")
filter_status = st.selectbox("Status", statuses)
status_codes = {"Wszystkie": "", "Sukces": "success", "Częściowy sukces": "partial", "Błąd": "failed", "Podgląd ofert": "preview"}
visible = [run for run in runs if not status_codes[filter_status] or run.get("pipeline_status") == status_codes[filter_status]]
selected_run = str(st.query_params.get("run", ""))
for run in visible:
    with st.container(border=True):
        left, middle, right = st.columns([4, 2, 1])
        left.markdown(f"**{run.get('brand', '—')} {run.get('model', '—')}**  \\n<span class=\"meta\">{run.get('started_at', '—')} · {run.get('duration_seconds', '—')} s</span>", unsafe_allow_html=True)
        middle.markdown(run_chip(run.get("pipeline_status")), unsafe_allow_html=True)
        if right.button("Otwórz", key=f"run-{run.get('run_id')}"):
            st.query_params["run"] = str(run.get("run_id", ""))
            st.rerun()

detail = next((run for run in runs if str(run.get("run_id")) == selected_run), None)
if detail:
    st.divider()
    st.subheader(f"Szczegóły: {detail.get('brand', '—')} {detail.get('model', '—')}")
    st.markdown(run_chip(detail.get("pipeline_status")), unsafe_allow_html=True)
    kpis([
        ("Nowe oferty", detail.get("new_offers", "—"), "wynik wyszukiwania"),
        ("Pobrane", detail.get("offers_fetched", "—"), "karty ofert"),
        ("Błędne", detail.get("offers_failed", "—"), "wymagają ponowienia"),
        ("Pokrycie po", f"{detail.get('coverage_after', '—')}%", "wynik procesu"),
    ])
    if detail.get("pipeline_status") in {"failed", "partial"}:
        st.warning(detail.get("error_message") or "Część pobrań nie została ukończona. Możesz rozpocząć kolejny research produktu, aby bezpiecznie ponowić obsługę nowych danych.")
        action_one, action_two = st.columns(2)
        action_one.link_button("Uzupełnij dane tego produktu", f"/research?research_step=1&brand={detail.get('brand', '')}&model={detail.get('model', '')}&from=run", type="primary", width="stretch")
        action_two.link_button("Przejdź do błędów pobierania", "/queue", width="stretch")
    stages = detail.get("stages", [])
    if isinstance(stages, list):
        st.subheader("Etapy procesu")
        stage_timeline([stage for stage in stages if isinstance(stage, dict)])
    with st.expander("Szczegóły techniczne"):
        st.json({key: value for key, value in detail.items() if key not in {"_path", "_time"}})
