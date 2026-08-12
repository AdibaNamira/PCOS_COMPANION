"""
Part 6 analysis script.
Run with: python analyze_feedback.py

Joins logs/interactions.jsonl with feedback/feedback.jsonl on interaction_id
and prints simple summary stats. This is meant as a starting point for the
evaluation section of your paper - feel free to extend it (e.g. export to
a spreadsheet, break down by intent type, etc.) once you have real
participant data instead of the two test entries from test_part6_feedback.py.
"""

import json
import os
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INTERACTIONS_PATH = os.path.join(BASE_DIR, "logs", "interactions.jsonl")
FEEDBACK_PATH = os.path.join(BASE_DIR, "feedback", "feedback.jsonl")


def load_jsonl(path):
    records = []
    if not os.path.exists(path):
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def run():
    interactions = load_jsonl(INTERACTIONS_PATH)
    feedback = load_jsonl(FEEDBACK_PATH)

    interactions_by_id = {i["interaction_id"]: i for i in interactions}

    print(f"Total interactions logged: {len(interactions)}")
    print(f"Total feedback entries logged: {len(feedback)}")
    print()

    if not feedback:
        print("No feedback yet - run test_part6_feedback.py first, or once")
        print("this is wired into a real chat interface, real participant")
        print("feedback will accumulate here over time.")
        return

    rating_counts = defaultdict(int)
    rating_by_fallback = defaultdict(lambda: defaultdict(int))

    print("=" * 70)
    print("DETAILED JOIN (each feedback entry matched to its interaction):")
    for fb in feedback:
        interaction = interactions_by_id.get(fb["interaction_id"])
        rating_counts[fb["rating"]] += 1

        print("-" * 70)
        print(f"  rating: {fb['rating']}   comment: {fb.get('comment')}")
        if interaction:
            print(f"  patient message: {interaction['patient_message']}")
            print(f"  intent: {interaction['intent']}, "
                  f"factual_ratio: {interaction['factual_ratio']}, "
                  f"used_not_sure_fallback: {interaction['use_not_sure_fallback']}")
            print(f"  verification passed: {interaction['verification_passed']}")
            rating_by_fallback[interaction["use_not_sure_fallback"]][fb["rating"]] += 1
        else:
            print("  (no matching interaction found - this shouldn't normally happen)")

    print()
    print("=" * 70)
    print("SUMMARY")
    print(f"  Ratings overall: {dict(rating_counts)}")
    print(f"  Ratings when 'not sure' fallback was used: {dict(rating_by_fallback[True])}")
    print(f"  Ratings when a normal answer was given:    {dict(rating_by_fallback[False])}")


if __name__ == "__main__":
    run()