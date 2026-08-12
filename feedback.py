"""
Part 6: Feedback logging.

Captures how participants react to the bot's actual responses (thumbs
up/down + an optional comment), and ties that feedback to the exact
interaction that produced it via the shared `interaction_id` from
verifier.log_interaction().

This turns logs/interactions.jsonl (what the bot did) into something you
can actually analyze for your paper: does the planner's factual/empathetic
ratio correlate with how helpful patients found the response? Did
verifier overrides (fallback triggered) lead to lower satisfaction, or did
patients appreciate the honesty? etc.

Kept intentionally simple - an append-only JSONL file - given the one-week
timeline. A research prototype with a handful of participants doesn't need
a database for this.
"""

import json
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDBACK_PATH = os.path.join(BASE_DIR, "feedback", "feedback.jsonl")

VALID_RATINGS = ("up", "down")


def log_feedback(interaction_id, rating, comment=None):
    """
    interaction_id: the ID returned by verifier.log_interaction() for the
                     response the participant is reacting to.
    rating:          "up" or "down"
    comment:         optional free-text comment from the participant
    """
    if rating not in VALID_RATINGS:
        raise ValueError(f"rating must be one of {VALID_RATINGS}, got: {rating!r}")

    try:
        os.makedirs(os.path.dirname(FEEDBACK_PATH), exist_ok=True)
        record = {
            "interaction_id": interaction_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rating": rating,
            "comment": comment,
        }
        with open(FEEDBACK_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return record
    except Exception as e:
        print(f"[warning] could not write feedback log: {e}")
        return None