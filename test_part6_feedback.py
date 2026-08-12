"""
Part 6 test script.
Run with: python test_part6_feedback.py

Simulates two full interactions (plan -> pretend response -> verify ->
log interaction -> log feedback) so you can see the whole chain linking
a bot response to participant feedback via interaction_id. No API calls
needed - the "response text" here is hand-written to stand in for what
the generator would have produced.
"""

from planner import ResponsePlanner
from verifier import verify, log_interaction
from feedback import log_feedback

planner = ResponsePlanner()

# --- Interaction 1: a good, grounded factual answer, patient found it helpful ---
msg1 = "Is it true that PCOS is linked to insulin resistance?"
plan1 = planner.plan(msg1)
factual_entry1 = plan1["top_factual_match"]["entry"] if plan1["top_factual_match"] else None
response1 = (
    "Yes, there is a well-established link. Many people with PCOS have some degree of insulin "
    "resistance, where the body's cells don't respond to insulin as effectively. That's part of "
    "why diet and physical activity often come up in managing PCOS, alongside medical treatment."
)
verification1 = verify(response1, plan1, factual_entry1)
interaction_id_1 = log_interaction(msg1, plan1, verification1["safe_response"], verification1)
feedback1 = log_feedback(interaction_id_1, "up", "This actually explained it clearly, thank you")

print("=" * 70)
print(f"Interaction 1 ID: {interaction_id_1}")
print(f"Verification passed: {verification1['passed']}")
print(f"Feedback logged: {feedback1}")

# --- Interaction 2: the not-sure fallback, patient wasn't happy about it ---
msg2 = "What dosage of metformin should I take for PCOS?"
plan2 = planner.plan(msg2)
response2 = (
    "I don't have reliable, verified information on metformin dosages for PCOS in my knowledge "
    "base, so I can't give you any specific numbers. This is worth bringing to a doctor."
)
verification2 = verify(response2, plan2, None)
interaction_id_2 = log_interaction(msg2, plan2, verification2["safe_response"], verification2)
feedback2 = log_feedback(interaction_id_2, "down", "I wish it could just tell me the dosage")

print("=" * 70)
print(f"Interaction 2 ID: {interaction_id_2}")
print(f"Verification passed: {verification2['passed']}")
print(f"Feedback logged: {feedback2}")

print("=" * 70)
print("Check logs/interactions.jsonl and feedback/feedback.jsonl - each")
print("feedback entry's interaction_id should match one of the interaction")
print("log entries, linking them together.")