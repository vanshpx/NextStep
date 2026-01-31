from fastapi import FastAPI
from backend.schemas import UserPreferences
from backend.itinerary_generator import generate_itinerary


app = FastAPI(title="Voyage – Itinerary Generator")


@app.post("/generate-itinerary")
def generate(user: UserPreferences):
    return generate_itinerary(user)
