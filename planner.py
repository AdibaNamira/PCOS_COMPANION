"""
Part 3: Response Planner.

Reads a patient's message, figures out the intent (factual / emotional /
mixed), and decides what percentage of the eventual response should be
factual vs. empathetic. It also decides whether we actually have enough
knowledge to answer a factual question at all, or whether the "not sure"
fallback should kick in.
"""

import json
import os
from retriever import KnowledgeRetriever

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "planner_config.json")


def _load_config(path=CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class ResponsePlanner:
    def __init__(self, retriever=None, config_path=CONFIG_PATH):
        self.retriever = retriever or KnowledgeRetriever()
        self.config = _load_config(config_path)

    def _has_keyword(self, message, keywords):
        message_lower = message.lower()
        return any(kw in message_lower for kw in keywords)

    def _factual_confidence_label(self, score):
        t = self.config["thresholds"]
        if score >= t["factual_confident"]:
            return "high"
        elif score >= t["factual_weak"]:
            return "low"
        else:
            return "none"

    def plan(self, patient_message, has_emotion_override=None, is_high_risk_override=None):
        factual_matches = self.retriever.retrieve_factual(patient_message, top_k=2)
        empathetic_matches = self.retriever.retrieve_empathetic(patient_message, top_k=2)

        top_factual_score = factual_matches[0]["score"] if factual_matches else 0.0
        top_empathetic_score = empathetic_matches[0]["score"] if empathetic_matches else 0.0

        has_question = self._has_keyword(patient_message, self.config["question_keywords"])
        # Prefer the real classifier's judgment when available; fall back
        # to keyword detection only if the classifier call failed.
        has_emotion = has_emotion_override if has_emotion_override is not None else self._has_keyword(patient_message, self.config["emotion_keywords"])
        has_high_risk = is_high_risk_override if is_high_risk_override is not None else self._has_keyword(patient_message, self.config.get("high_risk_keywords", []))

        t = self.config["thresholds"]
        relevance_floor = t.get("relevance_floor", 0.05)

        # FIX: if the top factual match isn't even weakly relevant, drop it
        # entirely rather than attaching a random unrelated fact to a
        # message like "hello" or general small talk.
        if top_factual_score < relevance_floor:
            factual_matches = []
            top_factual_score = 0.0

        # --- Step 1: decide intent (label only - used for the default ratio) ---
        if has_question and not has_emotion and top_factual_score >= t["factual_confident"] and top_empathetic_score < t["empathetic_present"]:
            intent = "factual"
        elif has_emotion and not has_question:
            intent = "emotional"
        else:
            intent = "mixed"

        ratios = dict(self.config["default_ratios"][f"{intent}_intent"])

        factual_confidence = self._factual_confidence_label(top_factual_score)
        use_not_sure_fallback = False

        if has_high_risk:
            return {
                "patient_message": patient_message,
                "intent": intent,
                "factual_ratio": 0.0,
                "empathetic_ratio": 1.0,
                "factual_confidence": "none",
                "use_not_sure_fallback": True,
                "high_risk_override": True,
                "top_factual_match": None,
                "top_empathetic_match": empathetic_matches[0] if empathetic_matches else None,
                "signals": {
                    "has_question_keyword": has_question,
                    "has_emotion_keyword": has_emotion,
                    "has_high_risk_keyword": True,
                    "top_factual_score": round(top_factual_score, 3),
                    "top_empathetic_score": round(top_empathetic_score, 3),
                },
            }

        # FIX: only treat this as "the patient wants a factual answer" if
        # they actually asked something question-shaped. Being in the
        # "mixed" bucket by default (e.g. plain greetings, small talk) does
        # NOT mean a factual answer - or the not-sure fallback - is needed.
        wants_factual_answer = has_question

        if wants_factual_answer and factual_confidence == "none":
            ratios["factual"] = 0.0
            ratios["empathetic"] = 1.0
            use_not_sure_fallback = True
        elif wants_factual_answer and factual_confidence == "low":
            ratios["factual"] = ratios["factual"] * 0.5
            ratios["empathetic"] = 1.0 - ratios["factual"]
        elif not wants_factual_answer:
            # No real factual question was asked - keep any factual content
            # minimal regardless of the intent bucket's default ratio.
            ratios["factual"] = min(ratios["factual"], 0.1)
            ratios["empathetic"] = 1.0 - ratios["factual"]

        floor = self.config["minimum_empathetic_floor"]
        if ratios["empathetic"] < floor:
            ratios["empathetic"] = floor
            ratios["factual"] = 1.0 - floor

        return {
            "patient_message": patient_message,
            "intent": intent,
            "factual_ratio": round(ratios["factual"], 2),
            "empathetic_ratio": round(ratios["empathetic"], 2),
            "factual_confidence": factual_confidence,
            "use_not_sure_fallback": use_not_sure_fallback,
            "high_risk_override": False,
            "top_factual_match": factual_matches[0] if factual_matches else None,
            "top_empathetic_match": empathetic_matches[0] if empathetic_matches else None,
            "signals": {
                "has_question_keyword": has_question,
                "has_emotion_keyword": has_emotion,
                "top_factual_score": round(top_factual_score, 3),
                "top_empathetic_score": round(top_empathetic_score, 3),
            },
        }


if __name__ == "__main__":
    planner = ResponsePlanner()
    result = planner.plan("hello")
    print(json.dumps(result, indent=2, default=lambda o: o))