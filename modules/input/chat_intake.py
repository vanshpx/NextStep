"""
modules/input/chat_intake.py
-----------------------------
Two-phase intake layer for Stage 1 of the TravelAgent pipeline.

PHASE 1 — Structured Form (Hard Constraints)
  Prompts the user for exact, concrete values:
    departure_city, destination_city, departure_date, return_date,
    num_adults, num_children, restaurant_preference, total_budget
  No LLM involved — pure input() calls with validation.

PHASE 2 — Free-form Chat (Soft Constraints via NLP)
  User describes themselves, preferences, dislikes in natural language.
  LLM extracts SoftConstraints + CommonsenseConstraints from the conversation.
  Chat ends when user types 'done' or sends an empty line.

Returns a ConstraintBundle + total_budget ready for run_pipeline().
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from schemas.constraints import (
    CommonsenseConstraints,
    ConstraintBundle,
    HardConstraints,
    SoftConstraints,
)

# ─────────────────────────────────────────────────────────────────────────────
# Soft constraint extraction prompt
# ─────────────────────────────────────────────────────────────────────────────
_SC_EXTRACTION_PROMPT = """You are a travel assistant analysing a user's preferences from a conversation.

CONVERSATION:
{history}

TASK:
Extract soft preferences and personal rules the user expressed.
Return ONLY valid JSON — no markdown, no explanation:

{{
  "soft": {{
    "interests":                    ["activity/category interests e.g. museum, park, nightlife"],
    "travel_preferences":           ["travel style e.g. adventure, relaxed, cultural, luxury"],
    "spending_power":               "low | medium | high | null",
    "character_traits":             ["e.g. avoids_crowds, budget_conscious, spontaneous"],
    "dietary_preferences":          ["e.g. vegan, vegetarian, halal, kosher, local_cuisine, no_street_food"],
    "preferred_time_of_day":        "morning | afternoon | evening | null",
    "avoid_crowds":                 true | false | null,
    "pace_preference":              "relaxed | moderate | packed | null",
    "preferred_transport_mode":     ["walking, public_transit, taxi, car, bike"],
    "avoid_consecutive_same_category": true | false | null,
    "novelty_spread":               true | false | null,
    "rest_interval_minutes":        120,
    "heavy_travel_penalty":         true | false | null
  }},
  "commonsense": {{
    "rules": ["explicit dislikes or avoidances as short rules e.g. no street food, avoid tourist traps"]
  }}
}}

RULES:
- Only use what the user actually said. Do NOT invent preferences.
- spending_power: infer from language like 'budget trip'=low, 'mid-range'=medium, 'luxury'=high.
- avoid_crowds: true if user mentions avoiding crowds, preferring quiet spots, going early.
- pace_preference: 'relaxed' if they mention slow travel / few stops; 'packed' if they want max sights.
- preferred_time_of_day: 'morning' if they mention liking mornings; detect 'evening' for nightlife.
- rest_interval_minutes: infer from comments like 'need breaks' (→ 60) or 'non-stop' (→ 240).
- If nothing can be inferred for a field, return an empty list or null.
"""


class ChatIntake:
    """
    Two-phase intake:
      Phase 1 — form()  → fills HardConstraints from structured prompts
      Phase 2 — chat()  → fills SoftConstraints via NLP from free-form chat

    Usage:
        bundle, total_budget = ChatIntake(llm_client).run()
    """

    def __init__(self, llm_client: Any):
        self._llm = llm_client
        self._hard = HardConstraints()
        self._soft = SoftConstraints()
        self._commonsense = CommonsenseConstraints()
        self._total_budget: float = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def run(self) -> tuple[ConstraintBundle, float]:
        """Run both phases and return a complete ConstraintBundle."""
        self._print_banner()
        self._phase1_form()
        self._phase2_chat()
        bundle = ConstraintBundle(
            hard=self._hard,
            soft=self._soft,
            commonsense=self._commonsense,
        )
        return bundle, self._total_budget

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 1 — Structured Form (Hard Constraints)
    # ─────────────────────────────────────────────────────────────────────────

    def _phase1_form(self) -> None:
        print("\n── Phase 1: Trip Details ─────────────────────────────────────")
        print("  Please answer the following (press Enter to skip optional fields)\n")

        self._hard.departure_city   = self._ask("  Travelling FROM (city)*: ", required=True)
        self._hard.destination_city = self._ask("  Travelling TO   (city)*: ", required=True)

        self._hard.departure_date = self._ask_date(
            "  Departure date (YYYY-MM-DD)*: ", required=True
        )
        self._hard.return_date = self._ask_date(
            "  Return date    (YYYY-MM-DD)*: ", required=True
        )

        adults = self._ask("  Number of adults [1]: ", required=False) or "1"
        try:
            self._hard.num_adults = int(adults)
        except ValueError:
            self._hard.num_adults = 1

        children = self._ask("  Number of children [0]: ", required=False) or "0"
        try:
            self._hard.num_children = int(children)
        except ValueError:
            self._hard.num_children = 0

        self._hard.group_size = self._hard.num_adults + self._hard.num_children

        # Traveler ages (optional) — used for age-restriction HC checks
        ages_raw = self._ask(
            "  Ages of all travellers (comma-separated, e.g. 35,32,10): ",
            required=False,
        )
        if ages_raw:
            try:
                self._hard.traveler_ages = [
                    int(a.strip()) for a in ages_raw.split(",") if a.strip().isdigit()
                ]
            except ValueError:
                self._hard.traveler_ages = []

        self._hard.restaurant_preference = (
            self._ask("  Food preference (e.g. Indian / Vegetarian / No preference): ",
                      required=False) or ""
        )

        # Wheelchair accessibility HC
        wc_raw = self._ask(
            "  Does any traveller need wheelchair access? (yes/no) [no]: ",
            required=False,
        ) or "no"
        self._hard.requires_wheelchair = wc_raw.strip().lower() in ("yes", "y", "1", "true")

        while self._total_budget <= 0:
            raw = self._ask("  Total budget (number, e.g. 45000)*: ", required=True)
            try:
                self._total_budget = float(raw.replace(",", "").replace("₹", "").strip())
            except ValueError:
                print("  ⚠  Please enter a valid number.")

        print("\n  ✓ Trip details saved.\n")

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 2 — Free-form Chat (Soft Constraints via NLP)
    # ─────────────────────────────────────────────────────────────────────────

    def _phase2_chat(self) -> None:
        print("── Phase 2: Your Preferences ─────────────────────────────────")
        print("  Tell me about yourself as a traveller — interests, dislikes,")
        print("  travel style, anything you love or hate on trips.")
        print("  Type 'done' or leave empty when finished.\n")

        history: list[str] = []

        while True:
            user_input = input("  You: ").strip()
            if not user_input or user_input.lower() in ("done", "exit", "quit"):
                break
            history.append(user_input)

        if not history:
            print("  (No preferences provided — using defaults)\n")
            return

        # Send full chat history to LLM for SC extraction
        history_text = "\n  ".join(history)
        prompt = _SC_EXTRACTION_PROMPT.format(history=history_text)
        try:
            raw = self._llm.complete(prompt)
            extracted = self._parse_json(raw)
            self._apply_sc(extracted)
            print("\n  ✓ Preferences extracted.\n")
        except Exception as exc:
            print(f"\n  ⚠  Could not extract preferences ({exc}). Using defaults.\n")

    # ─────────────────────────────────────────────────────────────────────────
    # Apply extracted SC/commonsense onto internal state
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_sc(self, ext: dict) -> None:
        s = ext.get("soft", {})
        c = ext.get("commonsense", {})

        if s.get("interests"):
            self._soft.interests = list(
                dict.fromkeys(self._soft.interests + s["interests"])
            )
        if s.get("travel_preferences"):
            self._soft.travel_preferences = list(
                dict.fromkeys(self._soft.travel_preferences + s["travel_preferences"])
            )
        if s.get("spending_power"):
            self._soft.spending_power = s["spending_power"]
        if s.get("character_traits"):
            self._soft.character_traits = list(
                dict.fromkeys(self._soft.character_traits + s["character_traits"])
            )

        # ── New SC fields ─────────────────────────────────────────────────────
        if s.get("dietary_preferences"):
            self._soft.dietary_preferences = list(
                dict.fromkeys(self._soft.dietary_preferences + s["dietary_preferences"])
            )
        if s.get("preferred_time_of_day"):
            self._soft.preferred_time_of_day = s["preferred_time_of_day"]
        if s.get("avoid_crowds") is not None:
            self._soft.avoid_crowds = bool(s["avoid_crowds"])
        if s.get("pace_preference"):
            self._soft.pace_preference = s["pace_preference"]
        if s.get("preferred_transport_mode"):
            self._soft.preferred_transport_mode = list(
                dict.fromkeys(
                    self._soft.preferred_transport_mode + s["preferred_transport_mode"]
                )
            )
        if s.get("avoid_consecutive_same_category") is not None:
            self._soft.avoid_consecutive_same_category = bool(
                s["avoid_consecutive_same_category"]
            )
        if s.get("novelty_spread") is not None:
            self._soft.novelty_spread = bool(s["novelty_spread"])
        if s.get("rest_interval_minutes") is not None:
            try:
                self._soft.rest_interval_minutes = int(s["rest_interval_minutes"])
            except (TypeError, ValueError):
                pass
        if s.get("heavy_travel_penalty") is not None:
            self._soft.heavy_travel_penalty = bool(s["heavy_travel_penalty"])

        for rule in c.get("rules", []):
            if rule and rule not in self._commonsense.rules:
                self._commonsense.rules.append(rule)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _ask(prompt: str, required: bool = False) -> str:
        while True:
            val = input(prompt).strip()
            if val or not required:
                return val
            print("  ⚠  This field is required.")

    @staticmethod
    def _ask_date(prompt: str, required: bool = False) -> date | None:
        while True:
            raw = input(prompt).strip()
            if not raw and not required:
                return None
            try:
                return datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                print("  ⚠  Use format YYYY-MM-DD (e.g. 2026-03-20).")

    @staticmethod
    def _parse_json(raw: str) -> dict:
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return {}

    @staticmethod
    def _print_banner() -> None:
        print("\n" + "=" * 60)
        print("  TRAVELAGENT — Trip Planner")
        print("=" * 60)
