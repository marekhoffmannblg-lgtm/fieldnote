from __future__ import annotations

import subprocess
import sys

import streamlit as st

from services.integrations import pipeline_environment
from ui.components import hero, kpis
from ui.state import current_data


data = current_data()
queue = data["queue"]
hero("Kolejka", "Pobrane oferty", "Sprawdź, co czeka na pobranie, co jest gotowe oraz które oferty wymagają bezpiecznego ponowienia.")
pending = [row for row in queue if row.get("status") == "pending"]
fetched = [row for row in queue if row.get("status") == "fetched"]
errors = [row for row in queue if row.get("status") == "error"]
kpis([("Do pobrania", len(pending), "oczekujące oferty"), ("Pobrane", len(fetched), "gotowe źródła"), ("Wymagają ponowienia", len(errors), "błędy pobrania")])
if not queue:
    st.info("Kolejka jest pusta. Najpierw sprawdź dostępne oferty dla wybranego modelu.")
    st.stop()

if errors:
    st.subheader("Oferty wymagające działania")
    for row in errors:
        with st.container(border=True):
            st.markdown(f"**{row.get('detected_model') or row.get('model') or 'Nieznany model'}** · oferta {row.get('offer_id') or '—'}")
            st.caption(row.get("normalized_url") or "Brak adresu oferty")
            st.warning(row.get("error_message") or "Nie zapisano przyczyny błędu.")
            st.caption(f"Próby: {row.get('retry_count') or 0} · ostatni błąd: {row.get('last_error_at') or '—'}")
            if st.button("Ponów tę ofertę", key=f"retry-{row.get('offer_id')}", disabled=int(row.get("retry_count") or 0) >= 3):
                command = [sys.executable, "scripts/fetch_firecrawl_offer_pages.py", "--retry-errors", "--offer-id", str(row.get("offer_id") or "")]
                result = subprocess.run(command, capture_output=True, text=True, env=pipeline_environment(), check=False)
                if result.returncode == 0:
                    st.success("Ponowienie zostało uruchomione. Odśwież stronę, aby zobaczyć aktualny stan.")
                else:
                    st.error("Nie udało się ponowić pobrania. Szczegóły są dostępne w sekcji technicznej.")
                    with st.expander("Szczegóły techniczne"):
                        st.code(result.stdout + "\n" + result.stderr)
else:
    st.success("Nie ma błędnych pobrań w kolejce.")

with st.expander("Podsumowanie kolejki"):
    st.dataframe([{"Model": row.get("detected_model") or row.get("model") or "—", "Oferta": row.get("offer_id") or "—", "Stan": {"pending": "Oczekuje", "fetched": "Pobrano", "error": "Błąd"}.get(row.get("status"), row.get("status") or "—"), "Liczba prób": row.get("retry_count") or 0} for row in queue], hide_index=True, width="stretch")
