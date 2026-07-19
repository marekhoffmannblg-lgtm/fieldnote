from __future__ import annotations

from datetime import datetime

import streamlit as st

from services.integrations import INTEGRATIONS, delete_secret, integration_statuses, read_secret, save_secret
from ui.components import hero
from ui.state import switch


def return_to_research() -> None:
    if st.query_params.get("return_to") == "research":
        brand = str(st.query_params.get("brand", "Kinderkraft"))
        model = str(st.query_params.get("model", ""))
        step = str(st.query_params.get("research_step", "2"))
        origin = {key: str(st.query_params.get(key, "")) for key in ("from", "from_product", "catalog_q", "catalog_status", "catalog_brand") if str(st.query_params.get(key, ""))}
        st.query_params.clear()
        st.query_params.update({"research_step": step, "brand": brand, "model": model, **origin})
        switch("research")


hero("Integracje", "Połącz aplikację z usługami", "Klucze są przechowywane lokalnie w systemowym magazynie haseł. Nie zapisujemy ich w plikach, historii ani logach.")
statuses = integration_statuses()
for slug, entry in statuses.items():
    integration = entry["integration"]
    with st.container(border=True):
        first, second = st.columns([4, 1])
        first.markdown(f"### {integration.label}\n{integration.description}")
        second.markdown("✅ Połączono" if entry["connected"] else "⚪ Niepołączono")
        if entry["error"]:
            st.warning(entry["error"])
        key_input = st.text_input(f"Klucz {integration.label}", type="password", key=f"secret-{slug}", placeholder="Wklej klucz tylko, aby zapisać połączenie")
        save, check, remove = st.columns(3)
        if save.button("Podłącz" if not entry["connected"] else "Zmień klucz", key=f"save-{slug}", type="primary", width="stretch"):
            if not key_input.strip():
                st.error("Wpisz klucz przed zapisaniem.")
            else:
                error = save_secret(integration.key_name, key_input.strip())
                if error:
                    st.error(error)
                else:
                    st.session_state.pop(f"secret-{slug}", None)
                    st.success("Połączenie zapisano lokalnie w systemowym magazynie haseł.")
                    st.rerun()
        if check.button("Sprawdź połączenie", key=f"check-{slug}", width="stretch"):
            value, error = read_secret(integration.key_name)
            if error:
                st.error(error)
            elif value:
                st.session_state[f"checked-{slug}"] = datetime.now().strftime("%d.%m.%Y, %H:%M")
                st.success("Połączenie jest zapisane i będzie przekazane w pamięci do kolejnego researchu.")
            else:
                st.info("Nie zapisano jeszcze klucza dla tej integracji.")
        if remove.button("Usuń połączenie", key=f"remove-{slug}", width="stretch", disabled=not entry["connected"]):
            error = delete_secret(integration.key_name)
            if error:
                st.error(error)
            else:
                st.success("Połączenie usunięto z systemowego magazynu haseł.")
                st.rerun()
        if st.session_state.get(f"checked-{slug}"):
            st.caption(f"Ostatnie sprawdzenie lokalnego połączenia: {st.session_state[f'checked-{slug}']}")

if st.query_params.get("return_to") == "research":
    st.divider()
    if st.button("Wróć do researchu", type="primary"):
        return_to_research()
