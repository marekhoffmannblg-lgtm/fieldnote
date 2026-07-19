from __future__ import annotations

import streamlit as st

from services.integrations import integration_statuses
from ui.components import catalog_chip, hero, kpis, run_chip
from ui.state import current_data, switch


data = current_data()
models = data["models"]
runs = data["runs"]
integrations = integration_statuses()
hero("Start", "Co chcesz zrobić?", "Przejdź od katalogu produktów do researchu bez znajomości narzędzi technicznych.")

if "tutorial_done" not in st.session_state:
    st.session_state["tutorial_done"] = False
if "tutorial_step" not in st.session_state:
    st.session_state["tutorial_step"] = 1
show_tutorial = bool(st.session_state.get("show_tutorial", False))
if show_tutorial:
    steps = (
        ("1. Wybierz model", "W katalogu produktów znajdziesz każdy model, jego źródła i poziom pokrycia."),
        ("2. Odczytaj pokrycie", "Pokrycie mówi, ile pól benchmarku ma potwierdzone źródła. Brak danych nie oznacza braku cechy."),
        ("3. Porównaj modele", "Wybierz dwa do pięciu gotowych benchmarków, aby szybko zobaczyć podobieństwa i różnice."),
        ("4. Sprawdź oferty", "Podgląd ofert niczego nie zmienia. Dopiero pełny research pobiera nowe dane i aktualizuje benchmark."),
        ("5. Zweryfikuj źródła", "Przy każdym polu możesz rozwinąć dowody i zobaczyć ofertę, z której pochodzi wartość."),
    )
    step = max(1, min(len(steps), int(st.session_state["tutorial_step"])))
    title, description = steps[step - 1]
    st.markdown(f'<div class="action"><strong>Jak działa aplikacja · {step}/{len(steps)}</strong><br><strong>{title}</strong><br>{description}</div>', unsafe_allow_html=True)
    previous, next_step, skip = st.columns((1, 2, 1))
    with previous:
        if st.button("Wstecz", disabled=step == 1, key="tutorial-previous"):
            st.session_state["tutorial_step"] = step - 1
            st.rerun()
    with next_step:
        if st.button("Rozpocznij pracę" if step == len(steps) else "Dalej", type="primary", width="stretch", key="tutorial-next"):
            if step == len(steps):
                st.session_state["tutorial_done"] = True
                st.session_state["show_tutorial"] = False
            else:
                st.session_state["tutorial_step"] = step + 1
            st.rerun()
    with skip:
        if st.button("Pomiń", key="tutorial-skip"):
            st.session_state["tutorial_done"] = True
            st.session_state["show_tutorial"] = False
            st.rerun()

if not st.session_state["tutorial_done"] and not show_tutorial:
    st.markdown('<div class="action"><strong>Skonfiguruj aplikację w 3 krokach</strong><br>1. Podłącz Firecrawl. 2. Podłącz OpenAI. 3. Uruchom pierwszy research.<br><span class="muted">Możesz pominąć konfigurację i od razu przeglądać dane.</span></div>', unsafe_allow_html=True)
    welcome_first, welcome_second, welcome_third = st.columns(3)
    welcome_first.link_button("Podłącz usługi", "/integrations", type="primary", width="stretch")
    if welcome_second.button("Pokaż samouczek", width="stretch"):
        st.session_state["show_tutorial"] = True
        st.rerun()
    if welcome_third.button("Przejdź do katalogu", width="stretch"):
        st.session_state["tutorial_done"] = True
        switch("products")

cards = st.columns(3, gap="medium")
actions = [
    ("Przejrzyj produkty", "Zobacz dostępne modele, dane i braki.", "Otwórz produkty", "/products"),
    ("Rozpocznij research", "Znajdź nowe oferty i uzupełnij benchmark.", "Nowy research", "/research"),
    ("Sprawdź historię", "Zobacz postęp, błędy i wyniki procesów.", "Otwórz historię", "/runs"),
]
for column, (title, text, label, href) in zip(cards, actions):
    with column:
        st.markdown(f'<div class="card product-card"><h3>{title}</h3><p class="muted">{text}</p></div>', unsafe_allow_html=True)
        st.link_button(label, href, type="primary" if title == "Rozpocznij research" else "secondary", width="stretch")

missing_integrations = [status["integration"].label for status in integrations.values() if not status["connected"]]
if missing_integrations:
    st.markdown('<div class="action"><strong>Brakuje połączeń do usług.</strong><br>Bez nich możesz bezpiecznie przeglądać dane. Aby uruchomić research, podłącz Firecrawl oraz OpenAI.</div>', unsafe_allow_html=True)
    st.link_button("Otwórz integracje", "/integrations", width="stretch")

st.subheader("Wymaga uwagi")
waiting = [model for model in models if model["catalog_status"] in {"waiting_for_analysis", "analyzed_no_coverage"}]
attention = [model for model in models if model.get("targeted_search_recommended")]
queue_errors = [row for row in data["queue"] if row.get("status") == "error"]
if not (waiting or attention or queue_errors):
    st.success("Na teraz nie ma pilnych działań. Możesz przejść do porównania gotowych modeli.")
else:
    if waiting:
        st.info(f"{len(waiting)} modeli czeka na analizę lub raport. Otwórz produkt, aby rozpocząć uzupełnianie danych.")
        st.link_button("Zobacz produkty czekające na analizę", "/products?status=waiting_for_analysis")
    if attention:
        st.warning(f"{len(attention)} modeli ma zbyt mało potwierdzonych danych i może wymagać dodatkowego researchu.")
    if queue_errors:
        st.error(f"{len(queue_errors)} pobrań wymaga ponowienia. Szczegóły i bezpieczne akcje znajdziesz w Kolejce.")
        st.link_button("Przejdź do błędów pobierania", "/queue")

st.subheader("Ostatnie uruchomienia")
if not runs:
    st.info("Nie ma jeszcze zapisanych uruchomień. Pierwszy podgląd ofert lub pełny research pojawi się tutaj automatycznie.")
else:
    for run in runs[:3]:
        left, right = st.columns([5, 1])
        with left:
            stamp = run.get("started_at", "—")
            st.markdown(f"**{run.get('brand', '—')} {run.get('model', '—')}**  \\n{run_chip(run.get('pipeline_status'))} &nbsp; <span class=\"meta\">{stamp}</span>", unsafe_allow_html=True)
        with right:
            st.link_button("Szczegóły", f"/runs?run={run.get('run_id', '')}")
