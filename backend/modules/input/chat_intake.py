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
    PassengerDetails,
    SoftConstraints,
)

# ─────────────────────────────────────────────────────────────────────────────# Local keyword → category map (USE_STUB_LLM-safe interest extractor)
# ────────────────────────────────────────────────────────────────────────────
_INTEREST_KEYWORD_MAP: dict[str, str] = {
    # Nature / outdoor
    "beach": "natural_feature",  "beaches": "natural_feature",
    "nature": "park",            "garden": "park",
    "park": "park",              "parks": "park",
    "hike": "natural_feature",   "hiking": "natural_feature",
    "trek": "natural_feature",   "trekking": "natural_feature",
    "adventure": "natural_feature",
    # Culture / heritage
    "museum": "museum",          "museums": "museum",
    "history": "museum",         "historical": "museum",
    "heritage": "landmark",      "monument": "landmark",
    "fort": "landmark",          "palace": "landmark",
    "castle": "landmark",        "landmark": "landmark",
    # Worship
    "temple": "temple",          "temples": "temple",
    "shrine": "place_of_worship", "mosque": "place_of_worship",
    "church": "place_of_worship", "worship": "place_of_worship",
    # Shopping / markets
    "market": "market",          "markets": "market",
    "shopping": "market",        "bazaar": "market",
    "shop": "market",
    # Art
    "art": "art_gallery",        "gallery": "art_gallery",
    "galleries": "art_gallery",  "painting": "art_gallery",
    # Wildlife
    "zoo": "zoo",                "wildlife": "zoo",
    "safari": "zoo",             "animals": "zoo",
    # Food / dining
    "food": "restaurant",        "cuisine": "restaurant",
    "dining": "restaurant",      "eat": "restaurant",
    "restaurant": "restaurant",  "foodie": "restaurant",
    "street food": "restaurant",
    "cafe": "restaurant",        "cafes": "restaurant",
    "coffee": "restaurant",      "coffee shop": "restaurant",
    "bakery": "restaurant",      "brunch": "restaurant",
    "dessert": "restaurant",     "sweets": "restaurant",
    "tea": "restaurant",
    # Nightlife
    "bar": "nightlife",          "bars": "nightlife",
    "pub": "nightlife",          "pubs": "nightlife",
    "club": "nightlife",         "clubs": "nightlife",
    "nightlife": "nightlife",    "night out": "nightlife",
    # Wellness / relaxation
    "spa": "spa",                "massage": "spa",
    "yoga": "spa",               "wellness": "spa",
    "relax": "spa",              "relaxation": "spa",
    # Entertainment / amusement
    "amusement": "amusement_park", "theme park": "amusement_park",
    "waterpark": "amusement_park", "carnival": "amusement_park",
    # Scenic / viewpoints
    "viewpoint": "natural_feature", "sunset": "natural_feature",
    "sunrise": "natural_feature",   "scenic": "natural_feature",
    "lake": "natural_feature",      "river": "natural_feature",
    "waterfall": "natural_feature", "mountain": "natural_feature",
    "hill": "natural_feature",
}

# ────────────────────────────────────────────────────────────────────────────# Soft constraint extraction prompt
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
        self._raw_chat_text: str = ""   # Phase 2 history — used for local extraction + validation
        self._passengers: list[PassengerDetails] = []

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def run(self) -> tuple[ConstraintBundle, float]:
        """Run both phases and return a complete ConstraintBundle."""
        self._print_banner()
        self._phase1_form()
        self._phase2_chat()
        self._phase3_passengers()

        # ── Derive spending_power from budget if still unset ──────────────
        if not self._soft.spending_power and self._total_budget > 0:
            num_people = max(self._hard.num_adults + self._hard.num_children, 1)
            days = 1
            if self._hard.departure_date and self._hard.return_date:
                delta = (self._hard.return_date - self._hard.departure_date).days
                if delta > 0:
                    days = delta
            per_person_per_day = self._total_budget / num_people / days
            if per_person_per_day < 3000:
                self._soft.spending_power = "low"
            elif per_person_per_day < 8000:
                self._soft.spending_power = "medium"
            else:
                self._soft.spending_power = "high"

        bundle = ConstraintBundle(
            hard=self._hard,
            soft=self._soft,
            commonsense=self._commonsense,
            total_budget=self._total_budget,
            has_chat_input=bool(self._raw_chat_text.strip()),
            passengers=self._passengers,
        )
        # Bind: assert user budget stored in bundle
        assert bundle.total_budget == self._total_budget, (
            f"INPUT_BINDING_ERROR: bundle.total_budget={bundle.total_budget} "
            f"!= collected budget={self._total_budget}"
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

        # group_size and traveler_ages removed — no venue capacity/age API source

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

        nationality = self._ask(
            "  Your nationality (ISO-2 code, e.g. IN for India) [IN]: ",
            required=False,
        ) or "IN"
        self._hard.guest_nationality = nationality.strip().upper()[:2]

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

        history_text = "\n  ".join(history)
        self._raw_chat_text = history_text  # store for validation + local extraction

        # ── Step 1: Local keyword extraction (always runs, USE_STUB_LLM-safe) ──────────
        local_interests = self._extract_interests_local(history_text)
        if local_interests:
            self._soft.interests = list(
                dict.fromkeys(self._soft.interests + local_interests)
            )

        # ── Step 2: LLM extraction (supplements local results when LLM is real) ─────
        prompt = _SC_EXTRACTION_PROMPT.format(history=history_text)
        try:
            raw = self._llm.complete(prompt)
            extracted = self._parse_json(raw)
            if extracted:                     # skip stub no-op response
                self._apply_sc(extracted)
        except Exception as exc:
            print(f"  [LLM] SC extraction skipped ({exc}); local extraction still applied.")
        # ── Step 2b: Local SC fallbacks (USE_STUB_LLM-safe) ────────────────────
        self._apply_local_sc_fallbacks(history_text)
        # ── Step 3: Validate binding ──────────────────────────────────────────────
        if history and not self._soft.interests:
            print(
                "  ⚠  INPUT_BINDING_ERROR: Preferences chat detected but no interests "
                "could be extracted. Please describe your interests more explicitly."
            )

        print(f"\n  ✓ Preferences extracted: interests={self._soft.interests}")
        if self._soft.spending_power:
            print(f"    spending_power={self._soft.spending_power}")
        if self._soft.pace_preference:
            print(f"    pace_preference={self._soft.pace_preference}")
        if self._soft.avoid_crowds:
            print(f"    avoid_crowds={self._soft.avoid_crowds}")
        if self._soft.dietary_preferences:
            print(f"    dietary_preferences={self._soft.dietary_preferences}")
        print()

    # ─────────────────────────────────────────────────────────────────────────    # PHASE 3 — Passenger Details (for TBO Booking)
    # ───────────────────────────────────────────────────────────────────────────

    def _phase3_passengers(self) -> None:
        total = self._hard.num_adults + self._hard.num_children
        print("── Phase 3: Passenger Details (required for booking) ────────")
        print(f"  Collecting details for {total} passenger(s).")
        print("  Press Enter to skip optional fields.\n")
        self._passengers = []
        for i in range(self._hard.num_adults):
            print(f"  ── Adult {i + 1} ───────────────────────")
            self._passengers.append(self._collect_one_passenger(passenger_type=1))
        for i in range(self._hard.num_children):
            print(f"  ── Child {i + 1} ───────────────────────")
            self._passengers.append(self._collect_one_passenger(passenger_type=2))
        print(f"\n  ✓ {len(self._passengers)} passenger(s) registered.\n")

    def _collect_one_passenger(self, passenger_type: int) -> PassengerDetails:
        type_label = "Adult" if passenger_type == 1 else "Child"
        p = PassengerDetails(passenger_type=passenger_type)

        raw_title = self._ask(f"    Title (Mr/Mrs/Ms/Dr) [Mr]: ", required=False) or "Mr"
        p.title = raw_title.strip()

        p.first_name = self._ask(f"    First name*: ", required=True)
        p.last_name  = self._ask(f"    Last name*: ",  required=True)

        while not p.date_of_birth:
            raw = self._ask(f"    Date of birth (YYYY-MM-DD)*: ", required=True)
            try:
                datetime.strptime(raw.strip(), "%Y-%m-%d")
                p.date_of_birth = raw.strip()
            except ValueError:
                print("    ⚠  Use format YYYY-MM-DD.")

        raw_gender = self._ask(f"    Gender (M/F) [M]: ", required=False) or "M"
        p.gender = 2 if raw_gender.strip().upper().startswith("F") else 1

        p.email  = self._ask(f"    Email (optional): ",  required=False) or ""
        p.mobile = self._ask(f"    Mobile number (digits, optional): ", required=False) or ""

        p.mobile_country_code = (
            self._ask(f"    Mobile country code (e.g. 91) [91]: ", required=False) or "91"
        )
        p.nationality_code = (
            self._ask(f"    Nationality ISO-2 code (e.g. IN) [IN]: ", required=False) or "IN"
        ).upper()[:2]

        p.id_number = self._ask(f"    ID/Passport number (optional): ", required=False) or ""
        if p.id_number:
            p.id_expiry = self._ask(f"    ID expiry date (YYYY-MM-DD, optional): ", required=False) or ""

        return p

    # ───────────────────────────────────────────────────────────────────────────    # Apply extracted SC/commonsense onto internal state
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
    # Local keyword-based SC fallback (USE_STUB_LLM-safe)
    # ─────────────────────────────────────────────────────────────────────────

    _PACE_KEYWORDS: dict[str, str] = {
        "slow": "relaxed", "relaxed": "relaxed", "easy": "relaxed",
        "chill": "relaxed", "leisurely": "relaxed", "laid back": "relaxed",
        "fast": "fast", "packed": "fast", "maximum": "fast",
        "intense": "fast", "non-stop": "fast", "nonstop": "fast",
    }

    _CROWD_KEYWORDS: set[str] = {
        "avoid crowd", "avoid crowds", "no crowd", "no crowds",
        "hate crowd", "hate crowds", "less crowd", "less crowded",
        "quiet", "peaceful", "secluded", "uncrowded", "off the beaten path",
    }

    _DIETARY_KEYWORDS: dict[str, str] = {
        "vegetarian": "vegetarian", "vegan": "vegan", "veg": "vegetarian",
        "halal": "halal", "kosher": "kosher", "gluten free": "gluten_free",
        "gluten-free": "gluten_free", "non-veg": "non_vegetarian",
        "non veg": "non_vegetarian", "jain": "jain",
    }

    _SPENDING_KEYWORDS: dict[str, str] = {
        "budget": "low", "cheap": "low", "affordable": "low",
        "economy": "low", "backpack": "low", "backpacker": "low",
        "mid-range": "medium", "mid range": "medium", "moderate": "medium",
        "comfort": "medium", "comfortable": "medium",
        "luxury": "high", "premium": "high", "splurge": "high",
        "five star": "high", "5 star": "high", "upscale": "high",
    }

    def _apply_local_sc_fallbacks(self, text: str) -> None:
        """
        Keyword-based extraction for soft-constraint fields that the LLM
        would normally handle. Ensures values are set even with USE_STUB_LLM=true.
        Only sets a field if it has not already been set (by LLM or otherwise).
        """
        lower = text.lower()

        # ── spending_power from chat keywords ──────────────────────────────
        if not self._soft.spending_power:
            for kw, level in self._SPENDING_KEYWORDS.items():
                pattern = r"(?<!\w)" + re.escape(kw) + r"(?!\w)"
                if re.search(pattern, lower):
                    self._soft.spending_power = level
                    break

        # ── pace_preference ────────────────────────────────────────────────
        if not self._soft.pace_preference:
            for kw, pace in self._PACE_KEYWORDS.items():
                pattern = r"(?<!\w)" + re.escape(kw) + r"(?!\w)"
                if re.search(pattern, lower):
                    self._soft.pace_preference = pace
                    break

        # ── avoid_crowds ──────────────────────────────────────────────────
        for kw in self._CROWD_KEYWORDS:
            if kw in lower:
                self._soft.avoid_crowds = True
                break

        # ── dietary_preferences ───────────────────────────────────────────
        for kw, pref in self._DIETARY_KEYWORDS.items():
            pattern = r"(?<!\w)" + re.escape(kw) + r"(?!\w)"
            if re.search(pattern, lower):
                if pref not in self._soft.dietary_preferences:
                    self._soft.dietary_preferences.append(pref)

    # ─────────────────────────────────────────────────────────────────────────
    # Local keyword-based interest extractor (USE_STUB_LLM-safe)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_interests_local(text: str) -> list[str]:
        """
        Keyword-based interest extraction that works without an LLM.
        Runs always in Phase 2 so preferences survive even when USE_STUB_LLM=true.
        Returns a deduplicated sorted list of internal category strings.
        """
        lower = text.lower()
        found: set[str] = set()
        for keyword, category in _INTEREST_KEYWORD_MAP.items():
            # word-boundary match to avoid partial hits (e.g. "bar" in "embarked")
            pattern = r"(?<!\w)" + re.escape(keyword) + r"(?!\w)"
            if re.search(pattern, lower):
                found.add(category)
        return sorted(found)

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
