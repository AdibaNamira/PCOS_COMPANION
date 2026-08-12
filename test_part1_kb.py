"""
Part 1 test script.
This just checks that both knowledge bases load correctly and are formatted right.
Run this with: python3 test_part1_kb.py
You should see "ALL GOOD" at the bottom if everything works.
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACTUAL_PATH = os.path.join(BASE_DIR, "knowledge_base", "factual", "pcos_basics.json")
EMPATHETIC_PATH = os.path.join(BASE_DIR, "knowledge_base", "empathetic", "support_phrases.json")


def load_kb(path, kb_name):
    print(f"\nChecking {kb_name} knowledge base at:\n  {path}")
    if not os.path.exists(path):
        print(f"  ERROR: file not found.")
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("entries", [])
    print(f"  Loaded OK. Found {len(entries)} entries.")
    for e in entries:
        eid = e.get("id", "MISSING_ID")
        topic_or_theme = e.get("topic") or e.get("theme") or "MISSING"
        print(f"    - {eid}: {topic_or_theme}")
    return data


if __name__ == "__main__":
    factual = load_kb(FACTUAL_PATH, "FACTUAL")
    empathetic = load_kb(EMPATHETIC_PATH, "EMPATHETIC")

    if factual and empathetic:
        print("\nALL GOOD — both knowledge bases loaded successfully.")
    else:
        print("\nSomething is missing — check the errors above.")
