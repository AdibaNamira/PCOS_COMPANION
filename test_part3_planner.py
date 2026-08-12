"""
Part 3 test script.
Run with: python3 test_part3_planner.py

Shows, for each sample patient message, what the planner decided: intent,
factual/empathetic ratio, confidence, and whether the "not sure" fallback
got triggered. Pay special attention to the messages marked NOT IN KB below
— those should trigger the fallback rather than getting a confident-looking
factual ratio.
"""

import json
from planner import ResponsePlanner

TEST_MESSAGES = [
    ("Is it true that PCOS is linked to insulin resistance?", "should be factual, high confidence"),
    ("I feel so ugly because of my acne and weight gain", "should be emotional, near-zero factual"),
    ("My period is really late this month and I'm scared", "should be mixed/emotional, low factual (not in KB)"),
    ("How do doctors confirm if I have PCOS?", "should be factual, high confidence"),
    ("What dosage of metformin should I take for PCOS?", "NOT IN KB — must trigger not-sure fallback, not guess a dosage"),
    ("Should I tell my family about my diagnosis?", "should be mixed, empathetic-led"),
    ("What's the capital of France?", "NOT IN KB, not even PCOS-related — must trigger not-sure"),
]


def run():
    planner = ResponsePlanner()
    for msg, expectation in TEST_MESSAGES:
        result = planner.plan(msg)
        print("=" * 70)
        print(f"MESSAGE: {msg}")
        print(f"EXPECTATION: {expectation}")
        print(f"  intent: {result['intent']}")
        print(f"  factual_ratio: {result['factual_ratio']}   empathetic_ratio: {result['empathetic_ratio']}")
        print(f"  factual_confidence: {result['factual_confidence']}")
        print(f"  use_not_sure_fallback: {result['use_not_sure_fallback']}")
        print(f"  high_risk_override: {result.get('high_risk_override')}")
        print(f"  signals: {result['signals']}")
        print()


if __name__ == "__main__":
    run()
