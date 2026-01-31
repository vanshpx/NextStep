import os
from dotenv import load_dotenv

load_dotenv()

# Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in .env")

# Gemini model (working, tested)
MODEL_NAME = "gemini-3-flash-preview"
