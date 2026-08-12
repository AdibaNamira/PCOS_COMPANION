"""
Part 2 test script.
Run with: python3 test_part2_retrieval.py

This throws a set of realistic patient messages at the retriever and shows
what it finds in each knowledge base, with similarity scores, so you can
eyeball whether retrieval is finding sensible matches.

Look especially at the LAST test case ("something totally outside the KB") —
its low scores are exactly what Part 5 will use to trigger the "I'm not
sure" safety fallback. Nothing to fix there; it's meant to score low.
"""

from retriever import KnowledgeRetriever

TEST_MESSAGES = [
    "How do doctors actually confirm if I have PCOS?",
    "I feel so ugly because of my acne and weight gain, I hate looking in the mirror",
    "My period is really late this month and I'm scared",
    "I've been eating better and working out for months and nothing is changing, I feel like giving up",
    "Should I tell my family about my diagnosis? I don't know if I want to",
    "Is it true that PCOS is linked to insulin resistance?",
    "What's the capital of France?",  # deliberately unrelated, should score low everywhere
]


def run():
    retriever = KnowledgeRetriever()

    for msg in TEST_MESSAGES:
        print("=" * 70)
        print(f"PATIENT MESSAGE: {msg}")

        print("\n  Top factual match(es):")
        for r in retriever.retrieve_factual(msg, top_k=2):
            entry = r["entry"]
            print(f"    [{r['score']:.3f}] {entry['id']} ({entry['topic']}): {entry['content'][:80]}...")

        print("\n  Top empathetic match(es):")
        for r in retriever.retrieve_empathetic(msg, top_k=2):
            entry = r["entry"]
            print(f"    [{r['score']:.3f}] {entry['id']} ({entry['theme']})")
        print()


if __name__ == "__main__":
    run()
