from __future__ import annotations

import streamlit as st

from ui.components import hero
from ui.state import switch


hero("Pomoc", "Jak pracować z benchmarkiem", "Odpowiedzi są uporządkowane według zadań, które wykonujesz w aplikacji.")
topics = {
    "Jak dodać produkt?": "Otwórz Nowy research, wpisz markę i model albo wybierz produkt z katalogu, a następnie sprawdź dostępne oferty.",
    "Jak uruchomić research?": "Kreator prowadzi od wyboru produktu, przez sprawdzenie ofert, do jasnego potwierdzenia pobierania i analizy danych.",
    "Co oznacza poziom pokrycia?": "To udział pól benchmarku potwierdzonych w pobranych źródłach. Brak danych nie oznacza braku cechy produktu.",
    "Co oznacza konflikt?": "Dwa lub więcej źródeł podało rozbieżne wartości. Otwórz produkt i sprawdź źródła przy danym polu.",
    "Jak ponowić błąd?": "Otwórz Kolejkę, wybierz błędną ofertę i użyj bezpiecznej akcji ponowienia. Następnie możesz wrócić do Researchu produktu.",
    "Jak zmienić klucz API?": "Otwórz Integracje. Klucz wpisujesz w polu hasła; po zapisie pozostaje wyłącznie w systemowym magazynie haseł.",
}
for question, answer in topics.items():
    with st.expander(question):
        st.write(answer)

st.divider()
st.subheader("Samouczek")
st.write("Możesz ponownie przejść krótkie wprowadzenie bez zmiany danych benchmarku.")
if st.button("Uruchom samouczek", type="primary"):
    st.session_state["tutorial_done"] = False
    st.session_state["tutorial_step"] = 1
    st.session_state["show_tutorial"] = True
    switch("home")
