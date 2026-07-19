from __future__ import annotations

import streamlit as st

from ui.navigation import build_navigation
from ui.styles import apply_styles


st.set_page_config(page_title="Fieldnote · Benchmark produktów", page_icon="◉", layout="wide", initial_sidebar_state="expanded")
apply_styles()

# The router owns the shared application frame. Individual pages only render a single user task.
build_navigation().run()
