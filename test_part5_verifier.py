"""
Part 5 test script.
Run with: python3 test_part5_verifier.py

This is fully offline - no API calls, no internet needed. It feeds the
verifier some response texts (including the REAL response you got back
from Part 4 for the insulin resistance question, and a made-up "bad" model
response simulating one that ignored instructions) and checks it reacts
correctly.
"""

from verifier import verify

# This is the actual response your model gave for the metformin dosage
# question - it correctly said it wasn't sure. Should PASS.
GOOD_NOT_SURE_RESPONSE = (
    "It's completely understandable to want clear, specific answers when it comes to medication "
    "- especially when you're trying to manage something as complex as PCOS. It can feel frustrating "
    "when the information isn't straightforward.\n\n"
    "I don't have reliable, verified information on metformin dosages for PCOS in my knowledge base, "
    "so I can't give you any specific numbers or guidelines. Medication dosing is highly individual "
    "and depends on many factors only a healthcare provider can assess.\n\n"
    "A general direction that might be helpful: this is exactly the kind of question worth bringing "
    "to a doctor or gynecologist who knows your history."
)
GOOD_PLAN = {"use_not_sure_fallback": True, "high_risk_override": True, "factual_ratio": 0.0}

# A made-up example simulating a model that IGNORED the not-sure instruction
# and guessed a dosage anyway. Should HARD FAIL and get replaced.
BAD_HALLUCINATED_RESPONSE = (
    "For PCOS, doctors typically start metformin at 500mg twice a day, "
    "increasing gradually. You should take 2 tablets daily with food."
)
BAD_PLAN = {"use_not_sure_fallback": True, "high_risk_override": True, "factual_ratio": 0.0}

# A made-up example where the model was allowed to answer confidently but
# forgot to say it's unsure - should also HARD FAIL even without a dosage.
MISSING_HEDGE_RESPONSE = (
    "PCOS is very common and quite manageable with the right approach, so try not to worry too much!"
)
MISSING_HEDGE_PLAN = {"use_not_sure_fallback": True, "high_risk_override": False, "factual_ratio": 0.0}

# A real, grounded factual answer with a matching factual entry - should
# PASS with a decent grounding score.
GOOD_FACTUAL_RESPONSE = (
    "Yes, there is a well-established link. Many people with PCOS have some degree of insulin "
    "resistance, where the body's cells don't respond to insulin as effectively. That's part of "
    "why diet and physical activity often come up in managing PCOS, alongside medical treatment. "
    "It doesn't mean everyone with PCOS will develop diabetes, but it's worth monitoring with a doctor."
)
GOOD_FACTUAL_PLAN = {"use_not_sure_fallback": False, "high_risk_override": False, "factual_ratio": 0.45}
GOOD_FACTUAL_ENTRY = {
    "content": (
        "Many people with PCOS also have some degree of insulin resistance, where the body's cells "
        "don't respond to insulin as effectively. This is very common in PCOS and is part of why diet "
        "and physical activity are often discussed as part of managing it, alongside any medical "
        "treatment. It does not mean every person with PCOS will develop diabetes, but it is a "
        "recognized risk factor worth monitoring with a doctor."
    )
}

CASES = [
    ("REAL response you got (dosage question, model said not sure)", GOOD_NOT_SURE_RESPONSE, GOOD_PLAN, None, True),
    ("Simulated BAD response (model guessed a dosage anyway)", BAD_HALLUCINATED_RESPONSE, BAD_PLAN, None, False),
    ("Simulated response missing the required hedge", MISSING_HEDGE_RESPONSE, MISSING_HEDGE_PLAN, None, False),
    ("Real-style grounded factual answer", GOOD_FACTUAL_RESPONSE, GOOD_FACTUAL_PLAN, GOOD_FACTUAL_ENTRY, True),
]


def run():
    for label, response_text, plan, factual_entry, expected_pass in CASES:
        result = verify(response_text, plan, factual_entry)
        status = "PASS" if result["passed"] else "BLOCKED (replaced with fallback)"
        correct = "correct" if result["passed"] == expected_pass else "!!! UNEXPECTED !!!"
        print("=" * 70)
        print(f"CASE: {label}")
        print(f"  expected passed={expected_pass}, got passed={result['passed']}  [{correct}]")
        print(f"  issues: {result['issues']}")
        print(f"  grounding_score: {result['grounding_score']}")
        if not result["passed"]:
            print(f"  --> response shown to patient would instead be:\n      {result['safe_response']}")
        print()


if __name__ == "__main__":
    run()
