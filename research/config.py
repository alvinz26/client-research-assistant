"""Settings read from the environment (.env). The API key is never printed or logged."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "claude-sonnet-5-5"

# USD per million tokens (input, output), from Anthropic's price list. Used only for the cost estimate.
PRICES = {"claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50), "claude-opus-5-5": (4.00, 20.00)}
SEARCH_PRICE = 0.01  # USD per web search

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}


@dataclass(frozen=True)
class Config:
    api_key: str | None
    model: str
    max_searches: int
    demo: bool
    output_dir: Path

    def __repr__(self) -> str:  # keep the key out of tracebacks and logs
        return f"Config(model={self.model!r}, max_searches={self.max_searches}, demo={self.demo})"


def load_config() -> Config:
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or None
    return Config(
        api_key=api_key,
        model=os.getenv("ANTHROPIC_MODEL", "").strip() or DEFAULT_MODEL,
        max_searches=int(os.getenv("MAX_SEARCHES", "8")),
        demo=os.getenv("DEMO_MODE", "0").strip() == "1" or api_key is None,
        output_dir=Path(os.getenv("OUTPUT_DIR", "outputs")),
    )


def estimate_cost(model: str, input_tokens: int, output_tokens: int, searches: int) -> float | None:
    """Rough USD cost of one run, or None if the model's price isn't listed above."""
    if model not in PRICES:
        return None
    price_in, price_out = PRICES[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000 + searches * SEARCH_PRICE
