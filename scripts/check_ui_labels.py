from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
REQUIRED_LABELS = (
    "Marka",
    "Kategoria",
    "Wózki",
    "Tytuł aukcji",
    "Cena",
    "Link do aukcji",
    "Otwórz aukcję",
    "Sponsorowana",
)


def main() -> int:
    app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    missing = [label for label in REQUIRED_LABELS if label not in app_source]
    if missing:
        print("FAIL")
        for label in missing:
            print(f"missing_label:{label}")
        return 1
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
