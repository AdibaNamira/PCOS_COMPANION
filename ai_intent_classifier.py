"""
Fallback AI classifier - only called for messages that are in the
"uncertain middle" of TF-IDF similarity (not confidently a special intent,
not confidently NOT one either). Kept as a separate, tiny, cheap call:
one word out, nothing else, so it's fast and minimizes API usage.

SAFE DEFAULT: any failure, timeout, or unparseable response returns None,
which means the message falls through to the normal medical-safety
pipeline - never blocks or breaks anything if this fails.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

ALLOWED_LABELS = {"source_followup", "meta_about", "doc_prep", "doctor_directory_request", "none"}

CLASSIFIER_SYSTEM_PROMPT = """You are a strict message classifier for a PCOS support chatbot. Reply with EXACTLY ONE WORD from this list and nothing else - no punctuation, no explanation:

source_followup - the patient is asking where a previous answer's information came from, or asking to verify/fact-check something already said
meta_about - the patient is asking about the chatbot itself, this app, how it works, privacy, or what the feedback buttons do
doc_prep - the patient wants help preparing questions or a list for an upcoming doctor/gynecologist visit
doctor_directory_request - the patient wants a specific doctor, clinic, or specialist recommended or named
none - anything else, including medical questions, emotional messages, greetings, or anything not clearly matching the above

Reply with exactly one of: source_followup, meta_about, doc_prep, doctor_directory_request, none"""


def classify_with_ai(message, timeout=8):
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_actual_openrouter_key_here":
        return None
    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
                "max_tokens": 10,
                "temperature": 0,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        if "choices" not in data or not data["choices"]:
            return None
        raw_label = data["choices"][0]["message"]["content"].strip().lower()
        raw_label = raw_label.strip(".,!\"' ")
        if raw_label in ALLOWED_LABELS and raw_label != "none":
            return raw_label
        return None
    except Exception as e:
        print(f"[warning] AI intent classifier failed: {e}")
        return None