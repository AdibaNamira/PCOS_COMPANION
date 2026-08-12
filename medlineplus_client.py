"""
Part 9: MedlinePlus integration (tier-2 retrieval source).

If the local, hand-curated knowledge base doesn't have a confident match
for a factual question, this queries MedlinePlus (a free, public API run
by the U.S. National Library of Medicine / NIH) as a second, still-trusted
source before giving up and saying "I'm not sure."

This does NOT replace the "not sure" fallback - it just gives it one more
real, authoritative place to check first. If MedlinePlus also has nothing
relevant, the system still falls back to being honest about not knowing.
High-risk questions (dosages, medications) NEVER use this - those stay on
the strict "always say not sure" path regardless of what any source says.
"""

import html
import re
import requests
import xml.etree.ElementTree as ET

MEDLINEPLUS_URL = "https://wsearch.nlm.nih.gov/ws/query"


def _strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def search_medlineplus(query, max_results=1, timeout=6):
    """
    Queries the MedlinePlus health topics web service.
    Returns a list of dicts: [{"title": ..., "summary": ..., "url": ...}, ...]
    Returns an empty list on any failure (network issue, no results, bad
    response) - this must NEVER crash the conversation, worst case is just
    "no extra info found."
    """
    try:
        response = requests.get(
            MEDLINEPLUS_URL,
            params={"db": "healthTopics", "term": query, "rettype": "brief"},
            timeout=timeout,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)

        results = []
        for doc in root.findall(".//document")[:max_results]:
            title, summary = "", ""
            for content in doc.findall("content"):
                name = content.get("name", "")
                if name == "title":
                    title = _strip_html("".join(content.itertext()))
                elif name in ("FullSummary", "snippet") and not summary:
                    summary = _strip_html("".join(content.itertext()))
            url = doc.get("url", "")
            if title and summary:
                results.append({"title": title, "summary": summary, "url": url})
        return results
    except Exception as e:
        print(f"[warning] MedlinePlus lookup failed: {e}")
        return []


def try_augment_plan_with_medlineplus(patient_message, plan):
    """
    If the local KB wasn't confident enough (and this isn't a high-risk
    question), try pulling one grounded snippet from MedlinePlus.

    Returns (updated_plan, factual_entry):
      - If nothing useful was found, or this is a high-risk question, or
        the local KB was already confident: returns (plan, None) unchanged.
      - If MedlinePlus provided something: returns an updated plan (with
        factual_confidence bumped to "medium" and a sensible ratio) plus a
        factual_entry-shaped dict the generator can use exactly like a
        local KB entry, clearly labeled as coming from MedlinePlus.
    """
    if plan.get("high_risk_override"):
        return plan, None
    if plan.get("factual_confidence") == "high":
        return plan, None
    if not plan.get("signals", {}).get("has_question_keyword"):
        return plan, None

    results = search_medlineplus(f"PCOS {patient_message}", max_results=1)
    if not results:
        return plan, None

    result = results[0]
    factual_entry = {
        "content": result["summary"],
        "source_note": f'MedlinePlus (U.S. National Library of Medicine) - "{result["title"]}" ({result["url"]})',
    }

    updated_plan = dict(plan)
    updated_plan["factual_confidence"] = "medium"
    updated_plan["use_not_sure_fallback"] = False
    updated_plan["factual_ratio"] = max(plan.get("factual_ratio", 0), 0.4)
    updated_plan["empathetic_ratio"] = round(1 - updated_plan["factual_ratio"], 2)

    return updated_plan, factual_entry