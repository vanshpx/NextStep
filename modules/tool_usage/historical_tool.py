"""
modules/tool_usage/historical_tool.py
--------------------------------------
HistoricalInsightTool — resolves the cultural/historical significance of a
place when the re-optimization system needs to inform the traveller of what
they would lose if a crowded stop is skipped.

Resolution priority (per place, cached per session):
  1. AttractionRecord.historical_importance  (non-empty string)
  2. LLM call (USE_STUB_LLM=False and llm_client is set)
  3. Stub fallback keyed by attraction category

Output: HistoricalInsight dataclass with format_for_display() word-wrapper.
"""

from __future__ import annotations
import textwrap
from dataclasses import dataclass, field
from typing import Any

import config


# ─────────────────────────────────────────────────────────────────────────────
# Output dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HistoricalInsight:
    """Cultural/historical significance of a single place."""
    place_name: str
    city:       str
    category:   str
    importance: str   # 2–3 sentence paragraph
    source:     str   # "record" | "llm" | "stub"

    def format_for_display(self, width: int = 62) -> list[str]:
        """Word-wrap importance text to fit within `width` characters."""
        return textwrap.wrap(self.importance, width=width)


# ─────────────────────────────────────────────────────────────────────────────
# Category stub fallbacks
# ─────────────────────────────────────────────────────────────────────────────

_STUB_BY_CATEGORY: dict[str, str] = {
    "museum": (
        "This museum preserves centuries of regional history, housing artefacts "
        "that are unavailable anywhere else in the country. Skipping it means "
        "missing the only permanent public collection of its kind."
    ),
    "landmark": (
        "This landmark is a defining symbol of the city's cultural identity and "
        "appears in the historical record as far back as the founding era. "
        "It is one of the most architecturally significant structures in the region."
    ),
    "park": (
        "This park occupies historically significant ground — the site of key "
        "civic events that shaped the city. Its riverside or garden sections "
        "contain preserved heritage structures not found elsewhere."
    ),
    "temple": (
        "This temple is an active centre of religious and cultural life, with "
        "architectural elements spanning multiple centuries. It represents a "
        "living tradition that has influenced the surrounding community for generations."
    ),
    "default": (
        "This is a noted attraction on your itinerary with recognised cultural "
        "or historical significance. Visiting provides context that enriches "
        "the rest of your trip experience."
    ),
}


def _stub_importance(category: str) -> str:
    return _STUB_BY_CATEGORY.get(category.lower(), _STUB_BY_CATEGORY["default"])


# ─────────────────────────────────────────────────────────────────────────────
# Tool
# ─────────────────────────────────────────────────────────────────────────────

class HistoricalInsightTool:
    """
    Resolves HistoricalInsight for a place.

    Usage:
        tool = HistoricalInsightTool(llm_client=my_llm)
        insight = tool.get(record, city="Delhi")
    """

    def __init__(self, llm_client: Any = None) -> None:
        self._llm    = llm_client
        self._cache: dict[str, HistoricalInsight] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, record: Any, city: str = "") -> HistoricalInsight:
        """
        Resolve historical insight for an AttractionRecord.

        Priority:
          1. record.historical_importance (non-empty)
          2. LLM call
          3. Stub by category
        """
        name     = getattr(record, "name",     "Unknown Place")
        category = getattr(record, "category", "")
        prefilled = getattr(record, "historical_importance", "")

        return self.get_by_name(
            place_name=name,
            city=city,
            category=category,
            prefilled=prefilled,
        )

    def get_by_name(
        self,
        place_name: str,
        city: str = "",
        category: str = "",
        prefilled: str = "",
    ) -> HistoricalInsight:
        """
        Resolve historical insight by explicit name/category.
        Uses cache to avoid repeated LLM calls for the same place.
        """
        cache_key = f"{place_name}::{city}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Priority 1: pre-filled record field
        if prefilled and prefilled.strip():
            insight = HistoricalInsight(
                place_name=place_name,
                city=city,
                category=category,
                importance=prefilled.strip(),
                source="record",
            )
            self._cache[cache_key] = insight
            return insight

        # Priority 2: LLM call
        if not config.USE_STUB_LLM and self._llm is not None:
            try:
                importance = self._call_llm(place_name, city, category)
                insight = HistoricalInsight(
                    place_name=place_name,
                    city=city,
                    category=category,
                    importance=importance,
                    source="llm",
                )
                self._cache[cache_key] = insight
                return insight
            except Exception:
                pass  # fall through to stub

        # Priority 3: stub fallback
        insight = HistoricalInsight(
            place_name=place_name,
            city=city,
            category=category,
            importance=_stub_importance(category),
            source="stub",
        )
        self._cache[cache_key] = insight
        return insight

    # ── Private ───────────────────────────────────────────────────────────────

    def _call_llm(self, place_name: str, city: str, category: str) -> str:
        """Call LLM to generate a 2–3 sentence historical importance paragraph."""
        prompt = (
            f"You are a knowledgeable travel guide.\n"
            f"In 2–3 sentences, explain the cultural and historical significance of "
            f"'{place_name}' in {city or 'the destination city'}.\n"
            f"Category: {category}.\n"
            f"Focus on: why it matters historically, what the traveller would miss "
            f"by skipping it, and any unique feature found nowhere else.\n"
            f"Keep it factual and vivid. No bullet points."
        )
        return self._llm.complete(prompt).strip()
