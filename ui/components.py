from __future__ import annotations

import html
from typing import Any

import streamlit as st

from ui.state import catalog_status_label, integer, plural, run_status_label, status_label


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def hero(eyebrow: str, title: str, description: str) -> None:
    st.markdown(f'<section class="hero"><div class="eyebrow">{esc(eyebrow)}</div><h1>{esc(title)}</h1><p>{esc(description)}</p></section>', unsafe_allow_html=True)


def kpis(items: list[tuple[str, object, str]]) -> None:
    cards = "".join(f'<div class="kpi"><small>{esc(label)}</small><b>{esc(value)}</b><small>{esc(note)}</small></div>' for label, value, note in items)
    st.markdown(f'<div class="kpis">{cards}</div>', unsafe_allow_html=True)


def chip(text: str, tone: str = "muted-chip") -> str:
    return f'<span class="chip {tone}">{esc(text)}</span>'


def catalog_chip(status: object) -> str:
    tone = {"ready": "ok", "analyzed_no_coverage": "info", "waiting_for_analysis": "wait", "no_sources": "muted-chip", "error": "warn"}.get(str(status), "muted-chip")
    return chip(catalog_status_label(status), tone)


def run_chip(status: object) -> str:
    tone = {"success": "ok", "partial": "warn", "failed": "wait", "preview": "info"}.get(str(status), "muted-chip")
    return chip(run_status_label(status), tone)


def field_chip(status: object, value: object) -> str:
    tone = "muted-chip" if str(value) == "X" else {"confirmed": "ok", "conflicting": "warn", "open": "wait"}.get(str(status), "wait")
    return chip(status_label(status, value), tone)


def coverage(value: object) -> None:
    percent = max(0, min(100, float(value or 0)))
    st.markdown(f'<div class="bar"><i style="width:{percent}%"></i></div><div class="meta">Poziom pokrycia: <strong>{percent:.1f}%</strong></div>', unsafe_allow_html=True)


def stepper(current: int, labels: tuple[str, ...]) -> None:
    blocks = []
    for index, label in enumerate(labels, start=1):
        state = "done" if index < current else "active" if index == current else ""
        blocks.append(f'<span class="step {state}">{index}. {esc(label)}</span>')
    st.markdown(f'<div class="stepper">{"".join(blocks)}</div>', unsafe_allow_html=True)


def no_data(title: str, description: str, action: str | None = None) -> None:
    st.info(f"**{title}**\n\n{description}")
    if action:
        st.caption(action)


def offer_metrics(result: dict[str, str]) -> None:
    kpis([
        ("Znalezione oferty", result.get("cards_found", "—"), "wyniki listingu"),
        ("Nowe oferty", result.get("new_offers", "—"), "gotowe do pobrania"),
        ("Już znane", result.get("already_known", "—"), "nie zostaną dodane ponownie"),
        ("Inne modele", result.get("rejected_other_models", "—"), "odrzucone wyniki"),
    ])


def result_metrics(result: dict[str, str]) -> None:
    kpis([
        ("Nowe oferty", result.get("new_offers", "—"), "wynik wyszukiwania"),
        ("Pobrane", result.get("offers_fetched", "—"), "karty ofert"),
        ("Błędne", result.get("offers_failed", "—"), "wymagają ponowienia"),
        ("Źródła", result.get("sources_total", "—"), "dla modelu"),
        ("Pokrycie", f"{result.get('coverage_after', result.get('coverage_percent', '—'))}%", f"zmiana: {result.get('coverage_change', '—')} p.p."),
    ])


def stage_label(value: object) -> str:
    return {"targeted search": "Szukanie ofert", "merge": "Dodawanie nowych ofert", "fetch offer pages": "Pobieranie stron", "technical cleaner": "Porządkowanie danych", "source registry": "Aktualizacja źródeł", "model groups": "Aktualizacja produktu", "model facts cascade": "Analiza AI", "model benchmark": "Budowa benchmarku", "coverage report": "Raport pokrycia"}.get(str(value or ""), str(value or "—"))


def stage_timeline(stages: list[dict[str, Any]]) -> None:
    for stage in stages:
        status = str(stage.get("status", "pending"))
        tone = "ok" if status == "success" else "warn" if status in {"partial", "skipped"} else "wait" if status == "failed" else "info"
        left, right = st.columns([3, 1])
        left.markdown(f"**{stage_label(stage.get('name'))}**  \\n<span class=\"meta\">{esc(stage.get('summary', '') or 'Oczekuje na wynik.')}</span>", unsafe_allow_html=True)
        label = "Pominięto" if status == "skipped" else "W toku" if status == "running" else run_status_label(status)
        right.markdown(chip(label, tone), unsafe_allow_html=True)
