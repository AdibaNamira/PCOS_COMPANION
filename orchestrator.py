"""
Part 7: Orchestrator.

Run with: python orchestrator.py
Type "exit" or "quit" to end.

Feedback is now optional and unobtrusive: at any point, type "up" or "down"
(with an optional comment after it) to rate the PREVIOUS response. Normal
chatting never gets interrupted by a feedback prompt.
"""

from planner import ResponsePlanner
from generator import generate_response
from verifier import verify, log_interaction
from feedback import log_feedback

EXIT_WORDS = {"exit", "quit", "bye", "goodbye"}


def run():
    planner = ResponsePlanner()
    last_interaction_id = None

    print("=" * 70)
    print("PCOS Companion Chatbot (prototype) — type 'exit' to stop")
    print("(Tip: type 'up' or 'down', optionally with a comment after it,")
    print(" anytime to rate my last response. Totally optional.)")
    print("=" * 70)
    print()

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in EXIT_WORDS:
            print("\nBot: Take care of yourself. I'm here whenever you need me.")
            break

        # --- Optional, unobtrusive feedback on the PREVIOUS response ---
        lowered = user_input.lower()
        if lowered.startswith("up") or lowered.startswith("down"):
            rating = "up" if lowered.startswith("up") else "down"
            comment = user_input[len(rating):].strip(" :-") or None
            if last_interaction_id:
                log_feedback(last_interaction_id, rating, comment)
                print("(Thanks — feedback logged.)\n")
            else:
                print("(No response yet to rate — go ahead and ask something first.)\n")
            continue

        # --- Part 2 + 3: retrieve + plan ---
        plan = planner.plan(user_input)
        factual_entry = plan["top_factual_match"]["entry"] if plan["top_factual_match"] else None
        empathetic_entries = [plan["top_empathetic_match"]] if plan["top_empathetic_match"] else []

        # --- Part 4: generate ---
        try:
            result = generate_response(user_input, plan, factual_entry, empathetic_entries, dry_run=False)
            raw_response = result["response_text"]
        except Exception as e:
            print(f"\n[error calling the model: {e}]")
            print("(Check your .env file has a valid OPENROUTER_API_KEY and OPENROUTER_MODEL)\n")
            continue

        # --- Part 5: verify ---
        verification = verify(raw_response, plan, factual_entry)
        final_response = verification["safe_response"]

        print(f"\nBot: {final_response}\n")

        # --- Part 6: log (feedback is now opt-in via typing up/down later) ---
        last_interaction_id = log_interaction(user_input, plan, final_response, verification)


if __name__ == "__main__":
    run()