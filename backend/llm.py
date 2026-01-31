import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing")

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-3-flash-preview"


def call_llm(prompt: str) -> str:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )

    if not response or not response.text:
        raise RuntimeError("Empty Gemini response")

    return response.text.strip()
