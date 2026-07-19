from __future__ import annotations

import os
from dataclasses import dataclass


SERVICE_NAME = "benchmark-app"
FIRECRAWL_KEY = "FIRECRAWL_API_KEY"
OPENAI_KEY = "OPENAI_API_KEY"


@dataclass(frozen=True)
class Integration:
    key_name: str
    label: str
    description: str


INTEGRATIONS = {
    "firecrawl": Integration(FIRECRAWL_KEY, "Firecrawl", "Pobiera strony ofert do lokalnego katalogu danych."),
    "openai": Integration(OPENAI_KEY, "OpenAI", "Analizuje wyłącznie pobrane dane ofert podczas researchu."),
}


def _keyring():
    try:
        import keyring
        return keyring, ""
    except Exception as exc:  # pragma: no cover - depends on the local keychain backend
        return None, f"Systemowy magazyn haseł jest niedostępny: {exc.__class__.__name__}. Zainstaluj zależność keyring i upewnij się, że macOS Keychain jest dostępny."


def read_secret(key_name: str) -> tuple[str, str]:
    keyring, error = _keyring()
    if keyring is None:
        return "", error
    try:
        return keyring.get_password(SERVICE_NAME, key_name) or "", ""
    except Exception as exc:  # pragma: no cover - OS keychain specific
        return "", f"Nie można odczytać połączenia z systemowego magazynu haseł: {exc.__class__.__name__}."


def save_secret(key_name: str, secret: str) -> str:
    keyring, error = _keyring()
    if keyring is None:
        return error
    try:
        keyring.set_password(SERVICE_NAME, key_name, secret)
        return ""
    except Exception as exc:  # pragma: no cover - OS keychain specific
        return f"Nie można zapisać połączenia w systemowym magazynie haseł: {exc.__class__.__name__}."


def delete_secret(key_name: str) -> str:
    keyring, error = _keyring()
    if keyring is None:
        return error
    try:
        keyring.delete_password(SERVICE_NAME, key_name)
        return ""
    except keyring.errors.PasswordDeleteError:
        return ""
    except Exception as exc:  # pragma: no cover - OS keychain specific
        return f"Nie można usunąć połączenia: {exc.__class__.__name__}."


def integration_statuses() -> dict[str, dict[str, object]]:
    statuses: dict[str, dict[str, object]] = {}
    for slug, integration in INTEGRATIONS.items():
        value, error = read_secret(integration.key_name)
        # Environment values remain supported for existing local installations, but are never exposed.
        connected = bool(value or os.environ.get(integration.key_name, "").strip())
        statuses[slug] = {"integration": integration, "connected": connected, "error": error, "last_checked": "Nie sprawdzono"}
    return statuses


def pipeline_environment() -> dict[str, str]:
    env = os.environ.copy()
    for integration in INTEGRATIONS.values():
        value, _ = read_secret(integration.key_name)
        if value:
            env[integration.key_name] = value
    return env
