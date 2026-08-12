"""
Part 4 test script — DRY RUN mode.
Run with: python3 test_part4_generator.py

This does NOT call OpenRouter or use any API quota. It runs the full
pipeline (retriever -> planner -> generator) and prints the exact prompt
that WOULD be sent to the model, so you can review it for correctness
before spending a single API call.

Once you've added your real key to .env, see the bottom of this file for
how to flip one test case to a real call and see an actual response.
"""

import json
from planner import ResponsePlanner
from generator import generate_response

TEST_MESSAGES = [
    "Is it true that PCOS is linked to insulin resistance?",
    "I feel so ugly because of my acne and weight gain",
    "What dosage of metformin should I take for PCOS?",  # should get the not-sure/fallback prompt
]


def run_dry():
    planner = ResponsePlanner()

    for msg in TEST_MESSAGES:
        plan = planner.plan(msg)

        factual_entry = plan["top_factual_match"]["entry"] if plan["top_factual_match"] else None
        empathetic_entries = [plan["top_empathetic_match"]] if plan["top_empathetic_match"] else []

        result = generate_response(msg, plan, factual_entry, empathetic_entries, dry_run=True)

        print("=" * 70)
        print(f"PATIENT MESSAGE: {msg}")
        print(f"PLAN: intent={plan['intent']}, factual_ratio={plan['factual_ratio']}, "
              f"empathetic_ratio={plan['empathetic_ratio']}, "
              f"not_sure_fallback={plan['use_not_sure_fallback']}")
        print("\n--- SYSTEM PROMPT (sent every time, condensed persona/rules) ---")
        print(result["messages"][0]["content"][:200] + " ...[truncated, see PERSONA_AND_RULES in generator.py for full text]")
        print("\n--- USER PROMPT (this is the part that changes per message) ---")
        print(result["messages"][1]["content"])
        print()


if __name__ == "__main__":
    run_dry()

    # --- To test a REAL API call once your .env key is set, uncomment below ---
    # planner = ResponsePlanner()
    # msg = "Is it true that PCOS is linked to insulin resistance?"
    # plan = planner.plan(msg)
    # factual_entry = plan["top_factual_match"]["entry"] if plan["top_factual_match"] else None
    # empathetic_entries = [plan["top_empathetic_match"]] if plan["top_empathetic_match"] else []
    # result = generate_response(msg, plan, factual_entry, empathetic_entries, dry_run=False)
    # print("\nREAL MODEL RESPONSE:\n", result["response_text"])
