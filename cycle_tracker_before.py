"""
Part 12: Cycle tracker.

Computes an approximate menstrual cycle phase from a last-period-start date
and average cycle length, and turns that into tone guidance for the
generator - NOT a medical fact to state to the patient, just context that
shapes how gently/directly the bot responds.

PRIVACY NOTE: this deliberately does NOT require any account or login.
The last period date is stored only in the patient's own browser
(localStorage) and sent along with each message - nothing is tied to an
identity, nothing persists on the server. This keeps the anonymous-by-
default design intact while still enabling phase-aware responses.

ACCURACY NOTE: PCOS very often causes irregular or longer cycles, so this
is an approximation, not precise tracking - the guidance text reflects
that a phase estimate, not a guarantee.
"""

from datetime import date

LUTEAL_PHASE_LENGTH = 14  # relatively constant across cycle lengths
GRACE_DAYS_BEFORE_LATE = 5

GUIDANCE_BY_PHASE = {
    "menstrual": (
        "The patient is currently tracked to be in the menstrual phase (on their period). "
        "Physical discomfort like cramps, fatigue, and low energy is common here, and mood can "
        "still be low as hormone levels are at their lowest point in the cycle. Keep responses "
        "gentle and low-pressure - don't push a lot of information at once unless asked, and "
        "check in warmly rather than energetically."
    ),
    "follicular": (
        "The patient is currently tracked to be in the follicular phase (after their period, "
        "before ovulation). For many people, rising estrogen in this phase is linked to more "
        "energy, optimism, and sociability compared to other phases. You can be a bit more "
        "upbeat and engaging here if the conversation calls for it, while still following your "
        "normal acknowledge-first structure - this isn't a phase to be extra cautious about, "
        "just don't assume everyone feels this lift equally."
    ),
    "ovulation": (
        "The patient is currently tracked to be near ovulation, when estrogen typically peaks. "
        "Many people report feeling more confident and energetic around this time. Match that "
        "energy where appropriate, but don't assume it - some people notice little change, and "
        "a small subset feel a brief dip right around ovulation itself as estrogen shifts."
    ),
    "luteal": (
        "The patient is currently tracked to be in the luteal phase (after ovulation, before "
        "their next period). For many people, rising progesterone and shifting estrogen in this "
        "phase are linked to increased emotional sensitivity, irritability, or lower mood, "
        "similar to PMS - though this varies a lot person to person and isn't universal. Lean "
        "extra gentle and validating in your tone, and be patient with more emotionally-loaded "
        "messages. Do not assume this explains whatever the patient is feeling, and don't bring "
        "it up unprompted - just let it inform how softly you respond."
    ),
}


def compute_cycle_context(last_period_start_str, avg_cycle_length=28):
    """
    last_period_start_str: ISO date string like "2026-08-01", or None/invalid.
    avg_cycle_length: int, clamped to a sane range (PCOS cycles can be long).
    Returns None if no valid date was given, otherwise a dict with phase,
    cycle_day, days_late, and guidance_text.
    """
    if not last_period_start_str:
        return None
    try:
        last_start = date.fromisoformat(last_period_start_str)
    except (ValueError, TypeError):
        return None

    try:
        avg_cycle_length = int(avg_cycle_length)
    except (ValueError, TypeError):
        avg_cycle_length = 28
    avg_cycle_length = max(21, min(avg_cycle_length, 60))  # PCOS cycles can run long

    today = date.today()
    days_since = (today - last_start).days
    if days_since < 0:
        return None  # future date entered by mistake, ignore

    cycle_day = (days_since % avg_cycle_length) + 1
    ovulation_day = max(10, avg_cycle_length - LUTEAL_PHASE_LENGTH)

    if cycle_day <= 5:
        phase = "menstrual"
    elif cycle_day < ovulation_day - 1:
        phase = "follicular"
    elif cycle_day <= ovulation_day + 1:
        phase = "ovulation"
    else:
        phase = "luteal"

    cycles_passed = days_since // avg_cycle_length
    expected_next_period_day_count = (cycles_passed + 1) * avg_cycle_length
    days_late = 0
    if days_since > expected_next_period_day_count + GRACE_DAYS_BEFORE_LATE:
        days_late = days_since - expected_next_period_day_count

    guidance_text = GUIDANCE_BY_PHASE[phase]
    if days_late > 0:
        guidance_text += (
            f" Additionally, based on their tracked cycle, their period appears to be about "
            f"{days_late} day(s) later than expected. Late or irregular periods are common with "
            f"PCOS, but that doesn't make the worry about it any less real - validate this concern "
            f"warmly. Do not speculate on causes or diagnose. If the delay is significant, gently "
            f"suggest mentioning it to a doctor without alarming them."
        )

    from datetime import timedelta
    next_expected = last_start + timedelta(days=avg_cycle_length * (cycles_passed + 1))

    guidance_text += (
        f" For factual reference ONLY if the patient directly asks about their tracked dates: "
        f"their last logged period start was {last_start.isoformat()}, and their next period is "
        f"estimated around {next_expected.isoformat()} (day {cycle_day} of an estimated "
        f"{avg_cycle_length}-day cycle). This is only an estimate based on their own logged "
        f"history, not a medical prediction - make that clear if you state it."
    )

    return {
        "phase": phase,
        "cycle_day": cycle_day,
        "days_late": days_late,
        "last_period_date": last_start.isoformat(),
        "next_expected_date": next_expected.isoformat(),
        "guidance_text": guidance_text,
    }