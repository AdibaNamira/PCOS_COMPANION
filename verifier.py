"""
Part 5: Verifier (hallucination-safety net).

Checks the generator's output AFTER it's produced, independent of whether
the model followed instructions. Hard rules that force a safe fallback:
  1. Never state a specific dosage/medication amount.
  2. If the planner flagged "not sure," the response must actually say so.
  3. NEW: never let the model's raw internal reasoning/planning text leak
     into what the patient sees (a real bug found in testing - a response
     once contained "We need to respond with empathy... Let's craft...
     Potential reply:" instead of an actual answer).
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "logs", "interactions.jsonl")

DOSAGE_PATTERN = re.compile(
    r"\b\d+(\.\d+)?\s?(mg|mcg|ml|milligrams?|micrograms?|iu)\b"
    r"|\b\d+\s?(pills?|tablets?|capsules?)\b"
    r"|\b\d+\s?times?\s?(a|per)\s?day\b",
    re.IGNORECASE,
)

REASONING_LEAK_PATTERN = re.compile(
    r"\bwe need to\b|\blet'?s craft\b|\bpotential reply\b|\bnow structure\b|"
    r"\bwe must\b.{0,20}\brespond\b|\bwe should\b.{0,20}\b(write|craft|respond|answer)\b|"
    r"^we\s|^let'?s\s|\bcount(ing)? (the )?words\b|\bmake sure (we|to)\b.{0,20}\bfactual\b|"
    # Broader category: any leaked internal/system-style labels or tags,
    # not just the one exact phrasing seen so far (e.g. "User Safety: safe").
    r"^user safety\s*:|^safety\s*:|^\[?system\]?\s*:|^\[?assistant\]?\s*:|"
    r"^category\s*:|^classification\s*:|^label\s*:|^intent\s*:|"
    r"^\{.*\"category\"|^\{.*\"safety\"",
    re.IGNORECASE,
)

UNCERTAINTY_PHRASES = [
    "not sure", "don't have reliable", "do not have reliable",
    "can't give you", "cannot give you", "can't say for certain",
    "cannot say for certain", "not certain", "unable to confirm",
    "no reliable", "don't have that information", "do not have that information",
    "recommend seeing a doctor", "recommend a doctor", "see a doctor",
    "see a gynecologist", "talk to a doctor", "consult a doctor",
    "consult a healthcare", "healthcare provider", "speak with a healthcare",
    "bring this to a doctor", "worth bringing to a doctor",
]

LOW_GROUNDING_THRESHOLD = 0.12

NOT_SURE_BANNER = "⚠️  NOT FULLY VERIFIED — please confirm with a doctor  ⚠️"

FALLBACK_MESSAGE = (
    "I want to be honest with you rather than guess — I don't have reliable, "
    "verified information to answer that specific part of your question. "
    "This is something worth bringing to a doctor or gynecologist who can look "
    "at your full picture. I'm still here for anything else you'd like to talk "
    "through in the meantime."
)

TECHNICAL_ERROR_MESSAGE = (
    "Sorry, something went wrong on my end generating that response. "
    "Please try asking again — if it keeps happening, this is a known "
    "issue being worked on."
)


def _contains_any(text_lower, phrases):
    return any(p in text_lower for p in phrases)


def _grounding_score(response_text, factual_context_text):
    if not factual_context_text:
        return None
    vectorizer = TfidfVectorizer(stop_words="english")
    try:
        matrix = vectorizer.fit_transform([response_text, factual_context_text])
    except ValueError:
        return None
    score = cosine_similarity(matrix[0:1], matrix[1:2])[0][0]
    return float(score)


def verify(response_text, plan, factual_entry=None):
    text_lower = response_text.lower()
    issues = []
    hard_fail = False
    is_reasoning_leak = False

    if REASONING_LEAK_PATTERN.search(response_text):
        issues.append("reasoning_leak_detected")
        hard_fail = True
        is_reasoning_leak = True

    if DOSAGE_PATTERN.search(response_text):
        issues.append("dosage_or_specific_amount_detected")
        hard_fail = True

    expected_not_sure = bool(plan.get("use_not_sure_fallback") or plan.get("high_risk_override"))
    if expected_not_sure and not is_reasoning_leak:
        if not _contains_any(text_lower, UNCERTAINTY_PHRASES):
            issues.append("missing_uncertainty_acknowledgment")
            hard_fail = True

    grounding_score = None
    if not expected_not_sure and not is_reasoning_leak and factual_entry and plan.get("factual_ratio", 0) > 0:
        grounding_score = _grounding_score(response_text, factual_entry.get("content", ""))
        if grounding_score is not None and grounding_score < LOW_GROUNDING_THRESHOLD:
            issues.append(f"low_grounding_score_{grounding_score:.3f}")

    if is_reasoning_leak:
        # A reasoning leak isn't the same as "I don't know" - it's a
        # technical malfunction, so it gets its own distinct message
        # rather than the medical not-sure fallback.
        safe_response = TECHNICAL_ERROR_MESSAGE
    else:
        safe_response = FALLBACK_MESSAGE if hard_fail else response_text

    should_flag = expected_not_sure or (hard_fail and not is_reasoning_leak)
    if should_flag:
        safe_response = f"{NOT_SURE_BANNER}\n\n{safe_response}"

    return {
        "passed": not hard_fail,
        "issues": issues,
        "grounding_score": grounding_score,
        "safe_response": safe_response,
    }


def log_interaction(patient_message, plan, response_text, verification, interaction_id=None):
    interaction_id = interaction_id or str(uuid.uuid4())
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        record = {
            "interaction_id": interaction_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "patient_message": patient_message,
            "intent": plan.get("intent"),
            "factual_ratio": plan.get("factual_ratio"),
            "empathetic_ratio": plan.get("empathetic_ratio"),
            "use_not_sure_fallback": plan.get("use_not_sure_fallback"),
            "high_risk_override": plan.get("high_risk_override"),
            "response_text": response_text,
            "verification_passed": verification["passed"],
            "verification_issues": verification["issues"],
            "grounding_score": verification["grounding_score"],
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        print(f"[warning] could not write interaction log: {e}")
    return interaction_id