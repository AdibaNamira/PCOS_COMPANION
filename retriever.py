"""
Part 2: Retrieval.

Given a patient's message, this finds the most relevant entries from the
factual KB and the empathetic KB, using TF-IDF (keyword-overlap) matching.

KNOWN LIMITATION (documented on purpose, not hidden): TF-IDF is
keyword-based, not semantic - it doesn't understand synonyms or paraphrasing
on its own. The SYNONYM_MAP below patches the most common cases found
through testing, but this list will never be fully complete. When a
message doesn't match anything, the system does NOT guess - it reports low/
no confidence, which triggers MedlinePlus as a second check, and finally an
honest "I'm not sure" if neither source has anything. A retrieval miss
never becomes a wrong answer, only an honest one - that's the actual safety
property this design guarantees, not "the bot always finds the right fact."
"""

import json
import os
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACTUAL_PATH = os.path.join(BASE_DIR, "knowledge_base", "factual", "pcos_basics.json")
EMPATHETIC_PATH = os.path.join(BASE_DIR, "knowledge_base", "empathetic", "support_phrases.json")

# "pcos" and close variants appear in nearly every KB entry, so left alone
# they dominate similarity scores without actually distinguishing topics -
# this caused a real false-confidence bug (e.g. "does pcos cause bloating"
# scored as confidently matched, when no fact actually covers bloating).
# Treating them as extra stop words fixes that.
CUSTOM_STOP_WORDS = list(ENGLISH_STOP_WORDS.union({"pcos", "polycystic", "ovary", "ovaries", "ovarian", "syndrome"}))


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class KnowledgeRetriever:
    # Common alternate terms/spellings mapped to the word actually used in
    # the knowledge base. This is a real, ongoing limitation of keyword-based
    # matching (no built-in synonym understanding), not a one-off patch -
    # add to it as new alternate phrasings come up in testing.
    SYNONYM_MAP = {
        # NOTE: "pcos"/"polycystic"/"ovary"/"syndrome" are custom stop
        # words (see CUSTOM_STOP_WORDS above), so mapping "pcod" to those
        # words alone does nothing - they'd just get filtered right back
        # out. Map to words that actually survive filtering and match
        # fact_015's real content instead.
        "pcod": "meaning definition full form what stands",
        "poly cystic": "polycystic",
        "diagnose": "diagnosed diagnosis",
        "diagnosing": "diagnosed diagnosis",
        "tests": "test diagnosed diagnosis",
    }

    def __init__(self, factual_path=FACTUAL_PATH, empathetic_path=EMPATHETIC_PATH):
        factual_data = _load_json(factual_path)
        empathetic_data = _load_json(empathetic_path)

        self.factual_entries = factual_data["entries"]
        self.empathetic_entries = empathetic_data["entries"]

        self._factual_texts = [self._factual_entry_text(e) for e in self.factual_entries]
        self._empathetic_texts = [self._empathetic_entry_text(e) for e in self.empathetic_entries]

        self._factual_vectorizer = TfidfVectorizer(stop_words=CUSTOM_STOP_WORDS)
        self._factual_matrix = self._factual_vectorizer.fit_transform(self._factual_texts)

        self._empathetic_vectorizer = TfidfVectorizer(stop_words=CUSTOM_STOP_WORDS)
        self._empathetic_matrix = self._empathetic_vectorizer.fit_transform(self._empathetic_texts)

    @staticmethod
    def _normalize_query(text):
        text_lower = text.lower()
        for term, replacement in KnowledgeRetriever.SYNONYM_MAP.items():
            if term in text_lower:
                text_lower = text_lower + " " + replacement
        return text_lower

    @staticmethod
    def _detag(text):
        # Topic/theme fields use underscores (e.g. "common_symptoms") which
        # TF-IDF would otherwise treat as one single odd token instead of
        # two real, matchable words.
        return text.replace("_", " ")

    @staticmethod
    def _factual_entry_text(entry):
        parts = [KnowledgeRetriever._detag(entry.get("topic", ""))]
        parts += entry.get("question_examples", [])
        parts.append(entry.get("content", ""))
        return " ".join(parts)

    @staticmethod
    def _empathetic_entry_text(entry):
        parts = [KnowledgeRetriever._detag(entry.get("theme", "")), entry.get("trigger_context", "")]
        parts += entry.get("phrases", [])
        return " ".join(parts)

    def retrieve_factual(self, query, top_k=2):
        return self._retrieve(query, self.factual_entries, self._factual_vectorizer, self._factual_matrix, top_k)

    def retrieve_empathetic(self, query, top_k=2):
        return self._retrieve(query, self.empathetic_entries, self._empathetic_vectorizer, self._empathetic_matrix, top_k)

    @staticmethod
    def _retrieve(query, entries, vectorizer, matrix, top_k):
        query = KnowledgeRetriever._normalize_query(query)
        query_vec = vectorizer.transform([query])
        scores = cosine_similarity(query_vec, matrix)[0]
        ranked = sorted(range(len(entries)), key=lambda i: scores[i], reverse=True)
        results = []
        for i in ranked[:top_k]:
            results.append({"entry": entries[i], "score": float(scores[i])})
        return results


if __name__ == "__main__":
    r = KnowledgeRetriever()
    print(r.retrieve_factual("what are the common symptoms of pcod", top_k=1))