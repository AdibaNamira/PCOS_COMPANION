# PCOS Chatbot — Part 1: Project Skeleton + Knowledge Bases

## What's in this part

```
pcos-chatbot/
├── knowledge_base/
│   ├── factual/
│   │   └── pcos_basics.json      <- medical facts (starter set, 5 entries)
│   └── empathetic/
│       └── support_phrases.json  <- supportive phrasing (starter set, 6 entries)
├── feedback/                     <- (empty for now) will hold participant feedback data
├── logs/                         <- (empty for now) will hold conversation logs
└── test_part1_kb.py              <- a script to check everything loads correctly
```

## Why two separate JSON files instead of one

Keeping facts and empathy completely separate is what lets the Response Planner
(coming in Part 3) control the *ratio* between them later, and it's what lets a
"not sure" fallback trigger cleanly on the factual side without losing the
supportive tone on the empathetic side.

## What each factual entry looks like

Every fact has:
- `content` — the actual information
- `source_note` — where it's grounded (so nothing is made up)
- `confidence` — how solid the fact is
- `requires_clinician_review: true` — **every single entry is flagged for your
  clinical advisor to check before this touches a real patient.** I pulled these
  from current clinical literature (Rotterdam criteria, AAFP, recent PCOS
  guidelines) but I'm not a substitute for a clinician's sign-off, especially
  since you mentioned this might reach real patients.

## What each empathetic entry looks like

Organized by emotional theme (body image, period anxiety, privacy/disclosure,
treatment frustration, feeling unseen, low mood, general). **This is now built
from your actual workshop data** (8 respondents from the design form + 9 from
Energy Orbit), not placeholders. Each entry notes which scenario/question it
came from. There's also a new `design_principles.md` file with the tone rules,
"always/never" list, and trust factors extracted from that same data — this
will directly shape the Response Planner and Generator in later parts.

See `feature_backlog.md` for feature requests from participants (doctor
question list, cycle-phase tone, distraction suggestions) that go beyond the
core pipeline — logged so they aren't lost, to revisit after the core system
works.

## How to test it yourself

```bash
cd pcos-chatbot
python3 test_part1_kb.py
```

You should see `ALL GOOD` at the end. This just proves the files are readable —
it doesn't call any AI model yet, so it costs nothing and needs no API key.

## What's NOT in this part yet (coming next)

- The Response Planner (deciding the factual/empathetic mix)
- The AI generation + "not sure" fallback safety layer
- OpenRouter connection

---

# Part 2: Retrieval

## What's new

- `retriever.py` — finds the most relevant KB entries for a patient message
- `test_part2_retrieval.py` — a script with realistic sample messages so you
  can see retrieval working

## How it works (plain language)

When a patient sends a message, we can't just hand the whole knowledge base
to the AI model every time — we need to find the *specific* facts and
empathy phrases that are actually relevant to what they said. That's what
retrieval does.

**Method used:** TF-IDF (keyword-overlap scoring), not AI embeddings. This
was a deliberate choice: your knowledge bases are still small, TF-IDF needs
no model download or API key, and it's fully testable right now, offline.
If you expand the KBs a lot later, this can be swapped for semantic
embeddings without changing how the rest of the system talks to it.

## How to test it yourself

```bash
cd pcos-chatbot
pip install -r requirements.txt
python3 test_part2_retrieval.py
```

You'll see 7 sample patient messages, and for each one, the top matching
facts and empathy entries with a similarity score (0 to 1). Notice the last
test message ("What's the capital of France?") scores 0.000 everywhere —
that's intentional. It shows the retriever honestly reporting "nothing here
matches," which is exactly the signal Part 5 will use to make the bot say
"I'm not sure" instead of guessing.

## Before you move on, please check

Skim the test output — do the top matches for each sample message look
sensible to you? If yes, I'll move to Part 3 (the Response Planner).

---

# Part 3: Response Planner

## What's new

- `planner_config.json` — editable thresholds and keyword lists (no code
  changes needed to tune these later)
- `planner.py` — decides intent (factual / emotional / mixed) and the
  factual:empathetic ratio for a response
- `test_part3_planner.py` — 7 sample messages with expected behavior noted

## How it works (plain language)

The planner reuses Part 2's similarity scores instead of making another AI
call to "figure out intent" — a message that matches the empathy KB well and
the factual KB poorly is, by definition, emotional in nature, and vice versa.
This keeps things fast, free, and avoids adding another place a model could
misjudge the situation.

It outputs, for every message: the intent, a factual/empathetic percentage
split, a confidence label for the factual side, and a flag for whether the
"not sure" safety fallback (built properly in Part 5) should kick in.

## A real bug I found and fixed while testing this

Testing with "What dosage of metformin should I take?" showed the retriever
scoring it as if we had a confident answer (0.353, above the "confident"
threshold) — just because words like "PCOS" overlapped with an unrelated KB
entry about lifestyle. We do not have any dosage information in the KB at
all. That's a real false-confidence risk, so I added a **hard safety
override**: certain high-risk categories (dosage, specific medication
questions, drug interactions) always force the "not sure" fallback,
regardless of similarity score, until a clinician-reviewed entry exists for
that exact topic. This list lives in `planner_config.json` under
`high_risk_keywords` — add to it any time you think of another category
that should never be guessed at.

## How to test it yourself

```bash
cd pcos-chatbot
python3 test_part3_planner.py
```

Each of the 7 messages prints its expected behavior next to what the
planner actually decided — check they match. The dosage question and the
"capital of France" question should both show `use_not_sure_fallback: True`.

## Before you move on, please check

1. Do the factual/empathetic ratios look reasonable for each sample message?
2. Can you think of other "high-risk" categories (beyond dosage/medication)
   that should always force the not-sure fallback, regardless of score?

If this looks right, I'll move to **Part 4: the Generator** — the piece
that actually calls the OpenRouter model to write the response, constrained
to only use what's been retrieved.

---

# Part 4: Generator

## What's new

- `.env.example` — copy to `.env` and add your real OpenRouter key
- `generator.py` — builds the constrained prompt and calls OpenRouter
- `test_part4_generator.py` — dry-run test, no API calls needed

## How it works (plain language)

This is where the retrieved facts, the empathetic tone examples, and the
planner's factual/empathetic ratio all get assembled into one prompt and
sent to an AI model. The system prompt (in `generator.py`, `PERSONA_AND_RULES`)
is a condensed version of `design_principles.md` — your workshop rules,
in force on every single message.

**The one rule this file exists to enforce:** the model is told, explicitly,
that it may only state medical facts that appear in the "FACTUAL CONTEXT"
section — nothing from its own general knowledge. When Part 3 flagged
`use_not_sure_fallback`, the FACTUAL CONTEXT section says exactly that, and
instructs the model to say it isn't sure rather than guess.

## Important: I could not test the real API call myself

This sandbox can't reach openrouter.ai, so unlike Parts 1–3, I could not run
a live call and see a real response. What I *did* verify (dry-run, no API
usage) is that the full pipeline — retrieve → plan → build the prompt —
assembles correctly for three cases: a confident factual question, a purely
emotional message, and the metformin dosage question (which correctly
produces the "don't guess" instruction instead of any factual content).

**You need to do the live test.** Here's how:

## How to test it yourself

1. Get your OpenRouter key ready (openrouter.ai → Keys)
2. In the `pcos-chatbot` folder, copy `.env.example` to a new file named `.env`
3. Open `.env` and replace `your_actual_openrouter_key_here` with your real key
4. Install the new dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. First, run the dry-run test (uses no API calls) to double check everything
   still looks right on your machine:
   ```bash
   python3 test_part4_generator.py
   ```
6. Then open `test_part4_generator.py`, scroll to the bottom, and uncomment
   the block under `# --- To test a REAL API call ---`. Run the file again —
   this time it will actually call OpenRouter and print a real response.

## Before you move on, please tell me

Paste me the real response text you get back from step 6 (or the exact
error, if something fails). I need to see what the live model actually
says before I build Part 5 (the hallucination-safety verifier), since that
part has to catch cases where the model doesn't follow these instructions
perfectly.

---

# Part 5: Verifier (hallucination-safety net)

## What's new

- `verifier.py` — checks the generator's output *after* it's produced,
  independent of whether the model followed instructions correctly
- `test_part5_verifier.py` — fully offline test, no API calls needed
- `logs/interactions.jsonl` — every conversation gets logged here once
  this is wired into the full pipeline (Part 7), useful both for debugging
  and as data for your research paper

## How it works (plain language)

Part 4's prompt tells the model what to do. This part checks whether it
actually did it. Two hard, non-negotiable rules:

1. **No specific dosages or medication amounts, ever** — checked with a
   pattern match (numbers + mg/pills/tablets/etc.), not a confidence score.
   This isn't about whether we think the number is right or wrong — the
   bot should never state one at all, full stop, since there's no
   clinician reviewing this content.
2. **If Part 3 said "we don't have reliable knowledge," the response must
   actually say so** — checked against a list of honest/uncertain phrases
   ("I don't have reliable information," "worth seeing a doctor," etc).

If either rule is broken, the response is thrown out and replaced with a
fixed, pre-written, always-safe fallback message — not patched or
re-worded, replaced entirely, so there's no chance of a partial hallucination
slipping through.

There's also a **soft** check (grounding score) that compares a confident
factual answer against the actual retrieved text, using the same
TF-IDF approach as Part 2. If the score is unusually low, it gets logged as
a flag for you to review later — it does NOT auto-replace the response,
because a low similarity score often just means the model paraphrased
well, not that it made something up. Auto-blocking on that alone would
cause more false alarms than real catches.

## What I tested (I could run this myself, no API needed)

Four cases, including a copy of your actual real model response from
Part 4:
1. Your real "not sure" response about metformin dosage → **passed**
2. A made-up response simulating a model that ignored instructions and
   guessed "500mg twice a day" anyway → **correctly blocked and replaced**
3. A made-up response that forgot to say "I'm not sure" at all → **correctly
   blocked and replaced**
4. A realistic grounded factual answer about insulin resistance →
   **passed**, with a high grounding score (0.74)

## How to test it yourself

```bash
python test_part5_verifier.py
```

No API key or internet needed for this one — it's pure pattern-checking on
text you already have.

## Before you move on, please check

Does the fixed fallback message (`FALLBACK_MESSAGE` in `verifier.py`) sound
right in tone to you? It's the one thing every patient would see if
something goes wrong, so it's worth reading carefully.

If it's good, I'll move to **Part 6: feedback logging** — capturing
participant reactions (thumbs up/down or similar) tied to the interaction
log this part just created, so you have real data for your paper on how
well the planner/verifier combination performs.
