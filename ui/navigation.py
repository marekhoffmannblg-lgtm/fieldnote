from __future__ import annotations

import streamlit as st

def build_navigation() -> st.navigation:
    pages = {
        "home": st.Page("pages/home.py", title="Start", icon="🏠", default=True),
        "products": st.Page("pages/products.py", title="Produkty", icon="📦"),
        "compare": st.Page("pages/compare.py", title="Porównanie", icon="↔️"),
        "research": st.Page("pages/research.py", title="Nowy research", icon="🔎"),
        "queue": st.Page("pages/queue.py", title="Kolejka", icon="📥"),
        "runs": st.Page("pages/runs.py", title="Historia", icon="⏱️"),
        "integrations": st.Page("pages/integrations.py", title="Integracje", icon="🔗"),
        "help": st.Page("pages/help.py", title="Pomoc", icon="❓"),
    }
    primary = list(pages.values())
    # Szczegóły są trasą potomną Produktów, nie osobną pozycją ani researchem.
    detail_page = st.Page("pages/product_detail.py", title="Produkty", icon="📦", url_path="produkt", visibility="hidden")
    return st.navigation([*primary, detail_page], position="top")
