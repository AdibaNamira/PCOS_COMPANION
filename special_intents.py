"""
Canned responses for non-medical special intents. The actual
classification now happens in intent_classifier.py (single AI call,
real language understanding). This file just maps a category to its
fixed response text.
"""

CATEGORY_TO_RESPONSE_KEY = {
    "meta_about_app": "meta_about",
    "doc_prep": "doc_prep",
    "doctor_directory_request": "doctor_directory_request",
    # source_followup is handled specially in app.py (needs live session data)
}

SPECIAL_RESPONSES = {
    "doc_prep": (
        "Good thinking to prepare ahead — it really helps to walk in with things written down.\n\n"
        "Here are some areas people commonly bring up with a doctor about PCOS:\n"
        "• Your specific symptoms, and how they connect (periods, skin, hair, weight, mood, etc.)\n"
        "• What led to your diagnosis, or what tests might confirm one\n"
        "• Treatment options available to you, and what to expect from each\n"
        "• Whether/how PCOS might affect fertility, if that's relevant to you\n"
        "• Lifestyle changes that might help, and where to realistically start\n"
        "• Long-term health monitoring (like diabetes or heart health checks)\n"
        "• Mental health support, since PCOS is linked to higher rates of anxiety and low mood\n"
        "• Whatever specific symptom is bothering you most right now\n\n"
        "You don't need to ask all of these — just pick whatever feels most relevant to you today."
    ),
    "meta_about": (
        "Happy to explain! I'm a prototype chatbot built to talk through PCOS-related "
        "questions and feelings with you. The 👍/👎 under my replies just let you rate whether "
        "a response was helpful — it's completely optional and just gets saved for the people "
        "building this to review later, it doesn't change how I respond in the moment.\n\n"
        "I try to only share medical information I can actually verify, and I'll tell you "
        "honestly when I'm not sure about something rather than guess."
    ),
    "doctor_directory_request": (
        "I don't have a verified list of specific doctors or clinics to give you, and I don't "
        "want to guess or make up names — that could send you somewhere unreliable.\n\n"
        "For finding a real gynecologist or endocrinologist, a few solid starting points are: "
        "asking your primary doctor for a referral, checking with a trusted hospital's official "
        "website for their specialist directory, or asking people you trust for a recommendation. "
        "I know that's not as convenient as a direct list, but I'd rather point you somewhere "
        "reliable than guess."
    ),
}


def get_special_response(category):
    key = CATEGORY_TO_RESPONSE_KEY.get(category)
    return SPECIAL_RESPONSES.get(key)