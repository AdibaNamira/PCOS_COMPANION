"""
Single, upfront message classifier - replaces the patchwork of TF-IDF
example-matching, emotion keyword lists, and guard-word lists that kept
needing one more entry added every time a new phrasing slipped through.

One clean AI call per message, using real language understanding instead
of string matching, decides both:
  1. What category this message is (medical question / emotional /
     casual / app-meta / source-followup / doc-prep / doctor-directory)
  2. Whether it carries real emotional weight (for the response planner)

EXCEPTION, DELIBERATE: high-risk medical detection (dosages, medication
names/amounts) does NOT depend on this AI call. That stays as a small,
deterministic pattern/keyword backstop in this same file, checked
separately and always, regardless of whether the AI classifier succeeds.
This is intentional defense-in-depth for the single highest-stakes flag
in the system - a safety-critical decision should not depend solely on
an AI call that could misjudge or time out (both have been observed).
"""

import os
import re
import json
import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

VALID_CATEGORIES = {
    "medical_question", "emotional_support", "casual_greeting",
    "source_followup", "meta_about_app", "doc_prep", "doctor_directory_request",
}

CLASSIFIER_SYSTEM_PROMPT = """You are a precise message classifier for a PCOS patient support chatbot. Read the patient's message and classify it.

Reply with ONLY a compact JSON object, nothing else, no explanation:
{"category": "<one category>", "has_emotion": true or false}

Categories (pick exactly one):
- medical_question: asking about PCOS symptoms, causes, biology, treatments, or any factual medical topic, even if phrased casually. Note: PCOD (Polycystic Ovarian Disease) is a related but medically distinct term from PCOS, not simply a misspelling - treat questions about PCOD as genuine medical_question requests, not as PCOS restated.
- emotional_support: the message expresses feelings, distress, frustration, venting, or emotional weight - even briefly or mixed with a question (e.g. "why do I have this", "I hate this")
- casual_greeting: simple greetings, small talk, or very short low-content messages (hi, hello, thanks, ok, good)
- source_followup: asking where previous information came from, wants the source, citation, or link for something already said, or is asking to verify/fact-check something already said. This includes short variations like "source?", "link?", "can you provide the source link", "where's that from", "give me the source", "source link".
- meta_about_app: asking about the chatbot/app ITSELF - how it works, what it can do, privacy, what the feedback buttons mean, "who are you" as a product (not "why do I have PCOS")
- doc_prep: wants help preparing questions for an upcoming doctor/gynecologist appointment
- doctor_directory_request: wants a SPECIFIC doctor, clinic, or specialist named or recommended

has_emotion: true if the message carries any real feeling (worry, sadness, frustration, fear, anger), even if it's also a factual question. false only for genuinely neutral/informational messages.

If a message is both emotional AND a factual question, category is "emotional_support" and has_emotion is true - the emotional weight takes priority for how the response should be shaped, but the factual content still gets addressed normally afterward.

Examples:
"why does it have to be me, why do I have pcos" -> {"category": "emotional_support", "has_emotion": true}
"does pcos cause bloating" -> {"category": "medical_question", "has_emotion": false}
"what is pcod" -> {"category": "medical_question", "has_emotion": false}
"who are you" -> {"category": "meta_about_app", "has_emotion": false}
"good" -> {"category": "casual_greeting", "has_emotion": false}
"what's the source of that" -> {"category": "source_followup", "has_emotion": false}"""

# --- Deterministic high-risk backstop (NOT part of the AI classifier on purpose) ---
HIGH_RISK_PATTERNS = [
    r"\bdosage\b", r"\bdose\b", r"\bhow many (mg|milligrams|pills|tablets)\b",
    r"\bwhat (medication|medicine|pills?|drug)s? should i take\b",
    r"\bwhich (medication|medicine|pill|drug) should i take\b",
    r"\bwhat should i take for\b", r"\bprescription\b", r"\bhow much metformin\b",
    r"\bhow often should i take\b", r"\bstop taking my medication\b",
    r"\bdrug interaction\b", r"\bbirth control brand\b",
]
# --- Deterministic source-followup backstop (same reasoning as high-risk
# detection above): asking about a source is a narrow, well-defined intent
# that doesn't need AI judgment, and the AI classifier proved unreliable
# at catching every phrasing of it. This runs as a simple keyword check
# instead, checked in app.py alongside (not instead of) the AI category. ---
SOURCE_FOLLOWUP_PATTERNS = [
    r"\bsource\b", r"\bcitation\b", r"\breference\b", r"\blink\b",
    r"\bwhere.*(from|did.*get)\b", r"\bverify\b", r"\bfact.?check\b", r"\bcite\b",
    r"\bhow do you know\b", r"\bis (that|this) (true|verified|accurate)\b",
]
_SOURCE_FOLLOWUP_REGEX = re.compile("|".join(SOURCE_FOLLOWUP_PATTERNS), re.IGNORECASE)


def is_source_followup_request(message):
    return bool(_SOURCE_FOLLOWUP_REGEX.search(message))
_HIGH_RISK_REGEX = re.compile("|".join(HIGH_RISK_PATTERNS), re.IGNORECASE)


def is_high_risk_medical(message):
    return bool(_HIGH_RISK_REGEX.search(message))


def classify_message(message, timeout=8):
    """
    Returns (category_or_None, has_emotion_or_None).
    On ANY failure (no key, network error, bad response, unparseable JSON,
    invalid category), returns (None, None) - callers must have a safe
    default for that case (see planner.py / app.py).
    """
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_actual_openrouter_key_here":
        return None, None
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
                "max_tokens": 40,
                "temperature": 0,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        if "choices" not in data or not data["choices"]:
            return None, None
        raw = data["choices"][0]["message"]["content"].strip()
        raw = raw.strip("` \n")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
        parsed = json.loads(raw)
        category = parsed.get("category")
        has_emotion = parsed.get("has_emotion")
        if category not in VALID_CATEGORIES:
            category = None
        if not isinstance(has_emotion, bool):
            has_emotion = None
        return category, has_emotion
    except Exception as e:
        print(f"[warning] intent classifier failed: {e}")
        return None, None