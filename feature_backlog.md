# Feature Backlog

Features participants asked for that go beyond the core RAG/empathy/factual
pipeline (Parts 1–7). Not blocking the core build — but don't forget these.

## Likely feasible within the week, as later additions
- **Doctor-visit question list**: given a symptom/topic the patient mentions,
  generate a short list of questions to bring to their doctor. This can reuse
  the factual KB + generator once Part 4 exists — it's really just a
  different output format, not a new subsystem.
- **Low-mood distraction suggestions**: a small curated list of gentle
  activity suggestions (offered as an option, not forced) — can live as a
  third, small knowledge base or just extra entries in the empathetic KB.

## Needs its own design decision — discuss before building
- **Cycle-phase-aware tone**: chatbot remembers what phase of the cycle the
  patient is in and adjusts tone accordingly (e.g. gentler in luteal phase).
  This requires the patient to log/track their cycle somewhere the bot can
  read from — i.e. it depends on the period-tracking feature existing first,
  plus a rule set mapping cycle phase to tone adjustment. Worth a short
  conversation on how much of this is realistic in a week vs. a "phase 2"
  item for the paper.

## Explicitly out of scope for now (per participant note, low priority)
- **Period/medication reminders**: one respondent noted they don't want this
  if it adds much implementation work. Treat as optional, not core.

## UI / non-backend notes (for whoever builds the interface)
- Soft, warm, "feminine touch" visual design (pink accents mentioned)
- Voice input in Bangla and English (one respondent's request)
