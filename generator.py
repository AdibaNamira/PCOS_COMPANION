"""
Generator: builds the constrained prompt and calls OpenRouter.

FIXES (found via testing):
- "reasoning": {"exclude": true} stops reasoning-capable models from
  leaking their internal chain-of-thought into the visible response (a
  real bug: a patient once saw raw planning text like "Let's craft...
  Potential reply:" instead of an actual answer).
- Default model changed from the unpredictable "openrouter/free" auto-
  router back to a specific, tested model, since the auto-router's
  unpredictability was the likely cause of the reasoning leak.
- Added retry-with-backoff and a fallback model, since repeated 429 rate
  limit errors were interrupting real conversations.
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
print("[generator.py] LOADED — retry/fallback version, build check OK")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
FALLBACK_MODEL = os.getenv("OPENROUTER_FALLBACK_MODEL", "google/gemma-4-31b-it:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PERSONA_AND_RULES = """You are an empathetic companion chatbot for people with PCOS (Polycystic Ovary Syndrome). You are a friend who listens and a guide who gives information, not a doctor.

TONE: Gentle, soft, calm, and encouraging by default. Be more straightforward if the patient is being straightforward with you. Never sound robotic, generic, or artificial.

STRUCTURE: Always acknowledge the patient's feelings first. Only after that, offer information, options, or questions. Never lead with a fix or a list before acknowledging how they feel.

CRITICAL OUTPUT RULE: Output ONLY the final message you want the patient to read. Never include your reasoning process, planning notes, meta-commentary about how you're constructing the response (e.g. "We need to...", "Let's craft...", "Potential reply:", "Now structure:"), or any analysis of the instructions themselves. If you notice yourself writing about the response instead of directly to the patient, stop and start over with only the actual message.

NEVER:
- Never imply a symptom is the patient's fault or a discipline failure.
- Never state or guess a medical diagnosis.
- Never pressure or insist the patient disclose their condition to others.
- Never use empty, dismissive positivity when the patient is expressing real pain.
- Never compare the patient to other people's experiences or outcomes.
- Never simply agree with everything the patient says - gentle honest input is fine, pure flattery is not.
- Never use a scolding, preachy, or "aunty" tone.
- Never give medical advice that could cause harm.
- Never describe your own knowledge base, your context, "the materials I'm given," or what topics your information "focuses on." If you don't know something, just say plainly that you're not sure about that specific detail - do not explain why.

MOST IMPORTANT RULE - GROUNDING:
You may ONLY state medical/factual claims that appear in the "FACTUAL CONTEXT" section given to you in this prompt. Do NOT add any medical fact, statistic, treatment detail, or claim from your own general knowledge, even if you believe it to be true. If the FACTUAL CONTEXT section says there is no reliable information, you MUST tell the patient clearly and warmly that you're not sure about that specific detail, without describing what your knowledge base does or doesn't cover. You may offer one very general, clearly-labeled possible direction (e.g. "this is usually worth discussing with a doctor"), and you should recommend seeing a doctor or gynecologist. Never guess a dosage, medication name, or diagnosis under any circumstances - always defer to a doctor for those."""


def build_messages(patient_message, plan, factual_entry=None, empathetic_entries=None, cycle_context=None):
    empathetic_entries = empathetic_entries or []

    factual_ratio_pct = int(round(plan["factual_ratio"] * 100))
    empathetic_ratio_pct = int(round(plan["empathetic_ratio"] * 100))

    if plan.get("use_not_sure_fallback") or plan.get("high_risk_override"):
        factual_context = (
            "No reliable, verified information is available for this specific question. "
            "Do not guess. Say clearly and simply that you are not sure about this specific "
            "detail (without describing your knowledge base or what it covers), optionally "
            "offer one very general and clearly-labeled possible direction, and recommend "
            "seeing a doctor or gynecologist."
        )
    elif factual_entry:
        factual_context = f"{factual_entry['content']}\n(Source note: {factual_entry.get('source_note', 'internal knowledge base')})"
        if plan.get("factual_confidence") == "low":
            factual_context += (
                "\n\nIMPORTANT: This match is only weakly related to the patient's exact question. "
                "Do not add any extra facts, examples, named conditions, or statistics beyond what is "
                "written above. If the patient's question goes beyond this specific content, simply "
                "and plainly say you're not certain about that particular detail and suggest a doctor."
            )
    else:
        factual_context = "No factual context retrieved for this message — this appears to be a purely emotional/supportive message, not a factual question."

    if empathetic_entries:
        style_examples = "\n".join(f"- {p}" for e in empathetic_entries for p in e["entry"].get("phrases", [])[:2])
    else:
        style_examples = "(use your default gentle, warm tone)"

    cycle_section = ""
    if cycle_context:
        cycle_section = f"\n\nCYCLE CONTEXT (tone guidance only, never state this as a diagnosis or state the phase as fact to the patient unless they ask): {cycle_context}"

    has_emotion_signal = plan.get("signals", {}).get("has_emotion_keyword", False)
    if has_emotion_signal:
        ack_instruction = "This message carries real emotional weight - acknowledge the patient's feelings warmly before anything else, as usual."
    else:
        ack_instruction = "This message reads as a neutral, factual question with no strong emotional language. Keep any opening acknowledgment brief and natural (a sentence at most, or none at all) - do NOT manufacture emotional concern that isn't actually there. Get to the useful information promptly while staying warm, not clinical."

    user_prompt = f"""RESPONSE PLAN: Aim for roughly {factual_ratio_pct}% factual/informational content and {empathetic_ratio_pct}% empathetic/supportive content in your reply. {ack_instruction}{cycle_section}

FACTUAL CONTEXT (only use this — do not add outside medical facts, and do not describe this context or your knowledge base to the patient):
{factual_context}

EMPATHETIC STYLE EXAMPLES (tone reference only — adapt naturally, don't copy verbatim):
{style_examples}

PATIENT MESSAGE:
{patient_message}"""

    return [
        {"role": "system", "content": PERSONA_AND_RULES},
        {"role": "user", "content": user_prompt},
    ]


def _call_openrouter(messages, model, timeout=60):
    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "reasoning": {"exclude": True},  # suppress visible chain-of-thought leaking into content
        },
        timeout=timeout,
    )
    return response


def generate_response(patient_message, plan, factual_entry=None, empathetic_entries=None, dry_run=False, cycle_context=None):
    messages = build_messages(patient_message, plan, factual_entry, empathetic_entries, cycle_context)

    if dry_run:
        return {"dry_run": True, "messages": messages, "response_text": None}

    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_actual_openrouter_key_here":
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and paste your real key in."
        )

    models_to_try = [OPENROUTER_MODEL, FALLBACK_MODEL, "openai/gpt-oss-20b:free"]
    last_error = None

    for attempt_model in models_to_try:
        for retry in range(2):  # try each model up to twice (handles transient 429s)
            try:
                response = _call_openrouter(messages, attempt_model)
                if response.status_code == 429:
                    last_error = f"Rate limited on {attempt_model}"
                    time.sleep(1.5)
                    continue
                response.raise_for_status()
                data = response.json()

                if "error" in data:
                    last_error = f"OpenRouter error on {attempt_model}: {data['error']}"
                    break
                if "choices" not in data or not data["choices"]:
                    last_error = f"No choices returned from {attempt_model}"
                    break

                text = data["choices"][0]["message"]["content"]
                return {"dry_run": False, "messages": messages, "response_text": text, "raw": data, "model_used": attempt_model}
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                time.sleep(1)
                continue

    raise RuntimeError(f"All models failed. Last error: {last_error}")