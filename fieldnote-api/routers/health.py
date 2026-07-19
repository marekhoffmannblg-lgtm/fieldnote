"""Pure health response builder; secrets are never included."""

from __future__ import annotations

import os


def health_payload() -> dict[str, bool]:
    return {
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "firecrawl_configured": bool(os.getenv("FIRECRAWL_API_KEY")),
    }
