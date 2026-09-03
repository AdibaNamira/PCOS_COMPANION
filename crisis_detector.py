"""
Crisis detection.

ARCHITECTURE NOTE: this mirrors the deliberate choice already made in
intent_classifier.py for high-risk medical questions - the deterministic
pattern check runs ALWAYS and does not depend on an AI call succeeding.
A safety-critical decision should not hinge on a network request that can
time out or a model that can misjudge. The AI check is additive only: it
can escalate a message the patterns missed, never de-escalate one they
caught.

TWO CATEGORIES, different responses:
  self_harm         - emotional crisis, suicidal thoughts, self-harm
  medical_emergency - acute physical symptoms needing urgent care

Patterns deliberately describe intent and states, not methods. Listing
methods in source code that gets read, logged, and shared is its own
small harm, and adds nothing to detection accuracy.
"""

import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SELF_HARM_PATTERNS = [
    r"\bkill myself\b", r"\bend my life\b", r"\bend it all\b", r"\btake my own life\b",
    r"\bwant to die\b", r"\bwish i (was|were) dead\b", r"\bbetter off dead\b",
    r"\bdon'?t want to (live|be here|exist)\b", r"\bno reason to live\b",
    r"\bnothing to live for\b", r"\bsuicidal\b", r"\bsuicide\b",
    r"\bharm(ing|ed)? myself\b", r"\bhurt(ing)? myself\b", r"\bself[- ]?harm(ing|ed|s)?\b",
    r"\bcut(ting)? myself\b", r"\bhurting my ?self\b",
    r"\bcan'?t go on\b", r"\bcan'?t do this anymore\b.{0,30}\b(life|living)\b",
    r"\beveryone would be better off without me\b",
    r"\bgive up on life\b", r"\bdisappear forever\b",
]

MEDICAL_EMERGENCY_PATTERNS = [
    r"\bbleeding (heavily|so much|non[- ]?stop|for (days|weeks))\b",
    r"\bsoaking through\b", r"\bcan'?t stop bleeding\b",
    r"\bcan'?t breathe\b", r"\btrouble breathing\b",
    r"\bchest pain\b", r"\bpain in my chest\b",
    r"\b(fainted|passed out|blacked out)\b",
    r"\bunbearable pain\b", r"\bworst pain of my life\b",
    r"\bsevere (pain|cramps)\b.{0,40}\b(can'?t|cannot)\b",
    r"\bvomiting (blood|non[- ]?stop)\b",
]

_SELF_HARM_RE = re.compile("|".join(SELF_HARM_PATTERNS), re.IGNORECASE)
_MEDICAL_RE = re.compile("|".join(MEDICAL_EMERGENCY_PATTERNS), re.IGNORECASE)

AI_PROMPT = """You screen messages from a PCOS support chatbot for crisis situations. Reply with EXACTLY ONE WORD, nothing else:

self_harm - the person expresses suicidal thoughts, intent to harm themselves, or that they don't want to be alive
medical_emergency - the person describes acute physical symptoms that need urgent medical attention right now
none - anything else, including ordinary sadness, frustration, pain, or distress that is not an emergency

Be careful: everyday venting ("I hate this", "this is so frustrating", "I'm exhausted") is NOT a crisis. Only flag genuine emergencies.

Reply with exactly one of: self_harm, medical_emergency, none"""


def _detect_with_patterns(message):
    if _SELF_HARM_RE.search(message):
        return "self_harm"
    if _MEDICAL_RE.search(message):
        return "medical_emergency"
    return None


def _detect_with_ai(message, timeout=6):
    """Additive only. Any failure returns None and changes nothing."""
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_actual_openrouter_key_here":
        return None
    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "system", "content": AI_PROMPT},
                             {"role": "user", "content": message}],
                "max_tokens": 8,
                "temperature": 0,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        label = response.json()["choices"][0]["message"]["content"].strip().lower()
        label = label.strip(".,!\"' ")
        return label if label in ("self_harm", "medical_emergency") else None
    except Exception as e:
        print(f"[warning] crisis AI check failed (patterns still applied): {e}")
        return None


def detect_crisis(message, use_ai=True):
    """
    Returns "self_harm", "medical_emergency", or None.

    The pattern check runs first and always. The AI check only runs if the
    patterns found nothing, and can only escalate - it is never consulted
    to overturn a pattern match.
    """
    found = _detect_with_patterns(message)
    if found:
        return found
    if use_ai:
        return _detect_with_ai(message)
    return None
