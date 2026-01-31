import json
import uuid
from backend.schemas import Activity, Itinerary, TripState
from backend.llm import call_llm
from backend.place_provider import get_places_for_destination

 



# 1️⃣ Destination → type mapping
DESTINATION_TYPE_MAP = {
    "goa": "beach",
    "manali": "mountain",
    "shimla": "mountain",
    "paris": "city",
    "new york": "city"
}

# 2️⃣ Destination type → daily time window
DESTINATION_TIME_PROFILES = {
    "beach": ("10:00", "23:00"),
    "mountain": ("07:00", "21:00"),
    "city": ("09:00", "22:00")
}


# 3️⃣ Infer daily time internally
def infer_daily_time(destination: str):
    dest_key = destination.lower()
    dest_type = DESTINATION_TYPE_MAP.get(dest_key, "city")
    return DESTINATION_TIME_PROFILES[dest_type]

def remove_consecutive_food(activities):
    cleaned = []
    last_was_food = False

    for act in activities:
        is_food = act.category == "food"
        if is_food and last_was_food:
            continue
        cleaned.append(act)
        last_was_food = is_food

    return cleaned

def clean_place_name(name: str) -> str:
    bad_phrases = ["tour guide", "private tour", "guided tour"]
    cleaned = name.lower()
    for phrase in bad_phrases:
        cleaned = cleaned.replace(phrase, "")
    return cleaned.strip().title()




# 4️⃣ Main generator
def generate_itinerary(user):
    # ⏰ infer time instead of asking user
    start_time, end_time = infer_daily_time(user.destination)
    places = get_places_for_destination(user.destination)


    prompt = f"""
Create a {user.days}-day travel itinerary for {user.destination}.

Inferred daily schedule:
- Start time: {start_time}
- End time: {end_time}

User preferences:
- Interests: {', '.join(user.interests)}
- Pace: {user.pace}
- Budget level: {user.budget_level}

User suggestions:
{user.suggestions or "None"}


REAL-WORLD PLACES (use ONLY these, do not invent):
{[p["name"] for p in places]}

You must decide for each place:
- whether it is a sightseeing / tourist activity or a food-related activity
- when it is suitable to visit based on time of day
- how it fits naturally into the daily flow


ICONIC LANDMARKS (IMPORTANT):
If the destination has well-known or iconic landmarks that most visitors expect to see,
prefer including 2–3 such places somewhere in the itinerary.


TRAVEL CONTEXT:
The user is traveling with: {user.traveling_with}

Adjust the itinerary accordingly:
- Solo: flexible, calm, personal experiences
- Couple: scenic, romantic, relaxed experiences
- Family: safe, popular, comfortable places; avoid very late nights
- Friends: social, lively places; markets, night activities, energetic flow


DESTINATION AWARENESS:
First, infer what this destination is naturally known for.
The itinerary should reflect the character of this place and feel like a local recommendation.
Do not force any type of place that does not naturally fit the destination.





REALISM & DISTANCE:
Assume the user stays within the city and nearby areas.
Do not include places that are far away or impractical to visit in a day.
Group nearby places on the same day.


ITINERARY INTENT:
The main focus of each day is sightseeing and experiences.
Food should support the day, not dominate it.


FOOD GUIDANCE:
Most days should naturally include:
- breakfast (light start)
- lunch (one main meal)
- a short cafe or snack break
- dinner (one main meal)
Do not place food activities back-to-back.


DAY FLOW:
Mornings and afternoons are best for sightseeing.
Evenings are good for walks or relaxed experiences.
After dinner, prefer a suitable night activity if it makes sense.
At night, prefer a walk, public space, scenic area, or landmark over adding another food stop.

DAILY ACTIVITY COUNT (IMPORTANT):
- Each day should ideally have around 6 activities.
- Each day MUST have at least 5 activities.
- Each day MUST NOT have more than 7 activities.
- If there are many good places, distribute them across days instead of packing them into one day.
- Do NOT invent places just to reach the count.



TIME SENSE:
Schedule places at times when people normally visit them
(e.g., monuments in the day, walks in the evening, night markets at night).


QUALITY:
Prefer concrete places (landmarks, markets, walks) over generic services or tours.
Avoid vague names like "Local".


OUTPUT:
Return ONLY valid JSON.
No explanations.
No markdown.
Do not repeat places across days.





JSON format:
{{
  "day_1": [
    {{
      "name": "",
      "category": "",
      "estimated_duration_min": 0,
      "day": 1,
      "start_time": "",
      "end_time": "",
      "budget_level": ""
    }}
  ]
}}
"""


    raw_output = call_llm(prompt)
    data = json.loads(raw_output)

    days = {}

    for day_key, activities in data.items():
        parsed = []
        for act in activities:
            parsed.append(
                Activity(
                    activity_id=str(uuid.uuid4()),
                    name=clean_place_name(act["name"]),
                    category=act["category"],
                    estimated_duration_min=act["estimated_duration_min"],
                    day=act["day"],
                    start_time=act["start_time"],
                    end_time=act["end_time"],
                    budget_level=act["budget_level"],
                )
            )
            
            
        days[day_key] = remove_consecutive_food(parsed)


    return TripState(
    trip_id=str(uuid.uuid4()),
    version=1,
    days=days
)

