import os
from dotenv import load_dotenv

load_dotenv()

print("Tavily:", bool(os.getenv("TAVILY_API_KEY")))
print("Google:", bool(os.getenv("GOOGLE_PLACES_API_KEY")))
