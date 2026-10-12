import json
import re
from pathlib import Path

from services.llm_service import generate_response


BASE_DIR = Path(__file__).resolve().parent.parent

EMPLOYEE_FILE = BASE_DIR / "employee_record.json"
PROMPT_FILE = BASE_DIR / "prompts" / "rehearsal_prompt.txt"

# "groq" = Llama 3.3 70B (set GROQ_LLM_MODEL in .env to change). "ollama" = local Mistral.
ROHIT_PROVIDER = "groq"
# Small, fast model used only to label what the manager said.
CLASSIFIER_MODEL = "llama-3.1-8b-instant"

MAX_HISTORY_TURNS = 14
MAX_QUESTIONS_PER_CONVERSATION = 3
FALLBACK_ACCEPTANCE = "Okay, understood."


# =========================================================
# LOAD DATA
# =========================================================

def load_employee_record():
    with open(EMPLOYEE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def load_prompt():
    with open(PROMPT_FILE, "r", encoding="utf-8") as file:
        return file.read()


# =========================================================
# CONVERSATION HISTORY
# =========================================================

def _clean_turns(conversation):
    turns = []
    for turn in conversation:
        speaker = str(turn.get("speaker", "")).strip().lower()
        text = str(turn.get("text", "")).strip()
        if text and speaker in ("manager", "rohit"):
            turns.append((speaker, text))
    return turns


def build_conversation_history(conversation):
    turns = _clean_turns(conversation)

    if not turns:
        return "No previous conversation."

    turns = turns[-MAX_HISTORY_TURNS:]

    return "\n".join(
        f"{'MANAGER' if s == 'manager' else 'ROHIT'}: {t}" for s, t in turns
    )


# =========================================================
# PATTERNS (word-boundary matching everywhere)
# =========================================================

CHANGE_PATTERNS = [
    "from tomorrow", "from now on", "going forward", "moving forward", "onwards",
    "onward", "be on time", "start on time", "arrive on time", "arrive at work",
    "by 9:30", "by 09:30", "by nine thirty", "i need you to", "i'd like you to",
    "i would like you to", "can you commit", "let's agree", "lets agree", "we agree",
    "agree that", "check in", "follow up", "follow-up", "review this", "next week",
    "in two weeks", "in a month", "let's move on", "lets move on",
    "weekly", "one on one", "one-on-one", "1:1", "every week", "every monday",
    "inform you", "inform the", "let me know", "let your team know", "tell your team",
]

CLOSING_PATTERNS = [
    "thanks", "thank you", "that's all", "that is all", "we're done", "we are done",
    "that's it", "anything else", "wrap up", "let's end", "lets end", "appreciate",
]

AGREE_PATTERNS = [
    "i'll be on time", "i will be on time", "i'll make sure", "i will make sure",
    "i can do that", "that works", "sounds fair", "that's fair", "i agree",
    "i'll try", "i will try", "fair enough", "deal", "sounds good",
    "i'll do that", "i will do that", "okay, i'll", "okay i'll", "i'll be in",
    "i will be in", "i'll arrive", "i will arrive", "i'll inform", "i will inform",
    "i'll let", "i will let",
]

APOLOGY_PATTERNS = ["sorry", "apolog"]

EXPLAINED_PATTERNS = [
    "difficult", "struggl", "hard for me", "personal", "at home", "bit much",
    "going through", "rough", "challenging", "going on",
]

QUESTION_STARTS = (
    "why", "what", "how", "when", "where", "who", "could", "can", "would",
    "will", "is", "are", "do", "does", "did", "have", "has", "should",
)

SEVERE = re.compile(
    r"\b(terminat\w*|fired|sacked|let you go|letting you go|let go|dismiss\w*|"
    r"final warning|suspend\w*|show you the door|you'?re out|last day)\b",
    re.I,
)

SMALL_TALK = re.compile(
    r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|how are you|how'?s it going|"
    r"how are things|how have you been|how'?s your (day|week|morning)|what'?s up)\b",
    re.I,
)

CARING = re.compile(
    r"(what'?s (getting|been getting) in the way|what'?s going on|anything (going on|i should know|"
    r"bothering|on your mind)|is (something|everything)|everything (ok|okay|alright)|"
    r"how are you (doing|holding up|feeling) (lately|these days|with)|how have things been|"
    r"is there anything|can i help|how can i support|help you with|what support)",
    re.I,
)

ACCUSE = re.compile(
    r"\b(always|never|lazy|careless|unreliable|unacceptable|not good enough|don'?t care|"
    r"doesn'?t care|disappointed|disrespectful|irresponsible|useless|entitled|attitude|"
    r"what is wrong with you|your fault)\b",
    re.I,
)

LATENESS_WORDS = re.compile(
    r"\b(late|lateness|attendance|on time|9:30|nine thirty|punctual\w*|arriv\w*|mornings?)\b", re.I
)
PERF_WORDS = re.compile(
    r"\b(performance|backlog|csat|goals?|targets?|rating|review|certification|tickets?)\b", re.I
)


def _contains_any(text, patterns):
    text = text.lower()
    return any(re.search(r"\b" + re.escape(p), text) for p in patterns)


def _manager_asked_question(message):
    # speech recognition gives no "?", so also look at the first word
    message = message.strip().lower()
    if "?" in message:
        return True
    first = re.sub(r"^(okay|ok|so|and|well|now|rohit)[,\s]+", "", message).split(" ")[0]
    return first in QUESTION_STARTS


# =========================================================
# INTENT: what did the manager just do?
# =========================================================

INTENT_LABELS = ["small_talk", "caring_question", "severe", "off_topic", "unclear", "other"]

INTENT_GUIDANCE = {
    "small_talk": (
        "Aditi is greeting you or making small talk. Answer like a normal person at work, "
        "in one short, light sentence. Do NOT mention lateness, attendance, goals, tickets or any "
        "work problem. You do not know why she wants to talk yet. You may ask one short, natural "
        "question back."
    ),
    "caring_question": (
        "Aditi asked an open, caring question about you. Answer honestly but briefly and in general "
        "words, as someone who is private. If you are comfortable you may hint that there are a few "
        "things going on outside work, with no details. Do not recite facts or numbers and do not "
        "promise anything."
    ),
    "severe": (
        "Aditi just said something very serious, like firing you or a final warning. React like a "
        "real person: shock, disbelief, maybe anger or a stunned pause. Ask what is going on or why. "
        "Do NOT promise to change anything, do NOT agree, and do NOT talk about being on time."
    ),
    "off_topic": (
        "Aditi said something unrelated to work. React with mild confusion or a short natural answer. "
        "Do not steer the conversation back to any work issue yourself."
    ),
    "unclear": (
        "You did not catch or understand what Aditi said. Say so naturally and briefly, for example "
        "asking her to repeat it. Do not guess what she meant."
    ),
}

# intents where Rohit is allowed to reply with a question
QUESTION_FRIENDLY = {"small_talk", "off_topic"}
QUESTION_ALWAYS = {"severe", "unclear"}


def classify_intent(manager_message):
    words = len(manager_message.split())

    if SEVERE.search(manager_message):
        return "severe"

    if SMALL_TALK.search(manager_message) and words <= 8:
        return "small_talk"

    if CARING.search(manager_message):
        return "caring_question"

    if words <= 2 and not re.search(
        r"\b(thanks|thank|okay|ok|right|sure|yes|no|good|great|fine|alright)\b",
        manager_message, re.I,
    ):
        return "unclear"

    prompt = (
        "Classify the manager's line in a workplace conversation with an employee.\n"
        "Labels: small_talk, caring_question, severe, off_topic, unclear, other\n"
        "- small_talk: greeting or casual chit-chat\n"
        "- caring_question: asks how the employee is really doing or what is getting in the way\n"
        "- severe: announces or threatens termination, suspension or a final warning\n"
        "- off_topic: unrelated to work or to the conversation\n"
        "- unclear: garbled, cut off or meaningless\n"
        "- other: normal feedback discussion, accusation, proposal, agreement or closing\n"
        f'Line: "{manager_message}"\n'
        "Reply with ONE label only."
    )

    try:
        raw = generate_response(
            prompt,
            temperature=0.0,
            max_tokens=8,
            provider=ROHIT_PROVIDER,
            model=CLASSIFIER_MODEL,
        ).lower()
    except Exception as error:
        print("[INTENT] classifier failed:", error)
        return "other"

    return next((label for label in INTENT_LABELS if label in raw), "other")


# =========================================================
# TOPICS AND MOOD
# =========================================================

def topics_raised(manager_message, conversation):
    said = " ".join(t for s, t in _clean_turns(conversation) if s == "manager")
    said = f"{said} {manager_message}"

    return {
        "lateness": bool(LATENESS_WORDS.search(said)),
        "performance": bool(PERF_WORDS.search(said)),
    }


MOOD_AFTER_CARING = {"defensive": "guarded", "guarded": "neutral", "neutral": "open", "open": "open", "shaken": "shaken"}
MOOD_AFTER_ACCUSE = {"neutral": "guarded", "open": "guarded", "guarded": "defensive", "defensive": "defensive", "shaken": "defensive"}

MOOD_GUIDANCE = {
    "neutral": "Rohit is calm and a little reserved. Normal professional tone.",
    "open": "Rohit feels heard and is more relaxed. He answers a bit more openly, but is still private.",
    "guarded": "Rohit feels judged. He gives shorter answers, is a little cold, and shares less.",
    "defensive": "Rohit feels attacked. He objects calmly but firmly and gives very little away.",
    "shaken": "Rohit is rattled by something serious she said. His words are short and a bit unsteady.",
}


def compute_mood(manager_messages, current_intent):
    mood = "neutral"

    for message in manager_messages:
        if SEVERE.search(message):
            mood = "shaken"
        elif ACCUSE.search(message):
            mood = MOOD_AFTER_ACCUSE[mood]
        elif CARING.search(message):
            mood = MOOD_AFTER_CARING[mood]

    # the current line, when only the model-based classifier recognised it
    if current_intent == "caring_question" and not CARING.search(manager_messages[-1]):
        mood = MOOD_AFTER_CARING[mood]

    return mood


# =========================================================
# EMPLOYEE CONTEXT (only what is relevant to what was said)
# =========================================================

def build_safe_employee_context(employee, topics=None):
    topics = topics or {}

    context = {
        "employee": {
            "name": employee["name"],
            "role": employee["role"],
            "tenure_months": employee["tenure_months"],
            "manager_name": employee["manager_name"],
        }
    }

    if topics.get("performance"):
        perf = employee["performance"]
        context["performance"] = {
            "current_cycle_rating": perf["current_cycle_rating"],
            "previous_cycle_rating": perf["previous_cycle_rating"],
            "trend": perf["trend"],
        }
        context["goals"] = employee["goals"]

    if topics.get("lateness"):
        att = employee["attendance"]
        context["attendance"] = {
            "scheduled_start": att["scheduled_start"],
            "late_arrivals_last_90_days": att["late_arrivals_last_90_days"],
            "average_lateness_minutes": att["average_lateness_minutes"],
            "pattern_note": att["pattern_note"],
            "prior_conversation_logged": att["prior_conversation_logged"],
        }

    return context


# =========================================================
# CONVERSATION STATE
# =========================================================

def analyse_conversation(manager_message, conversation):
    turns = _clean_turns(conversation)
    rohit_lines = [t for s, t in turns if s == "rohit"]
    manager_lines = [t for s, t in turns if s == "manager"] + [manager_message]
    rohit_text = " ".join(rohit_lines)

    intent = classify_intent(manager_message)

    state = {
        "turn_number": len(rohit_lines) + 1,
        "intent": intent,
        "topics": topics_raised(manager_message, conversation),
        "mood": compute_mood(manager_lines, intent),
        "manager_proposes_change": _contains_any(manager_message, CHANGE_PATTERNS),
        "manager_closing": _contains_any(manager_message, CLOSING_PATTERNS),
        "manager_asked_question": _manager_asked_question(manager_message),
        "already_apologised": _contains_any(rohit_text, APOLOGY_PATTERNS),
        "already_explained": _contains_any(rohit_text, EXPLAINED_PATTERNS),
        "already_agreed": _contains_any(rohit_text, AGREE_PATTERNS),
        "questions_so_far": sum(1 for t in rohit_lines if "?" in t),
        "last_reply_had_question": bool(rohit_lines and "?" in rohit_lines[-1]),
        "last_rohit_line": rohit_lines[-1] if rohit_lines else "",
    }

    # Questions are rare once things are settled or right after Rohit asked one.
    allow = (
        not state["last_reply_had_question"]
        and state["questions_so_far"] < MAX_QUESTIONS_PER_CONVERSATION
        and not state["already_agreed"]
        and not state["manager_proposes_change"]
        and not state["manager_closing"]
        and not state["manager_asked_question"]
    )

    # A shocked, confused or small-talking person naturally asks something.
    if intent in QUESTION_ALWAYS:
        allow = True
    elif intent in QUESTION_FRIENDLY and not state["last_reply_had_question"]:
        allow = True

    state["allow_question"] = allow
    state["may_hint_personal"] = state["mood"] == "open" or intent == "caring_question"

    return state


def build_stage_guidance(state):
    intent = state["intent"]

    # What she just did decides first.
    if intent in INTENT_GUIDANCE:
        return f"STAGE: {intent.upper()}.\n{INTENT_GUIDANCE[intent]}"

    if state["turn_number"] == 1:
        return (
            "STAGE: OPENING.\n"
            "This is your first reply. Respond only to what the manager just said. "
            "If she already raised a work concern, react like a real person hearing it: "
            "acknowledge one specific thing she said and sound a little surprised or guarded. "
            "Do NOT agree to change anything yet. Do NOT explain your reasons yet."
        )

    if state["already_agreed"]:
        return (
            "STAGE: FOLLOW-UP (you have ALREADY agreed).\n"
            "The main issue is settled. React to what she just said with a short STATEMENT "
            "(3-20 words), like a colleague would.\n"
            "- Do NOT ask a question.\n"
            "- Do NOT repeat her words back to her.\n"
            "- Do NOT restate the agreement in full.\n"
            "- Do NOT apologise again and do NOT explain your difficulties again.\n"
            "- Do NOT go back to the problem or ask to discuss it again."
        )

    if state["manager_proposes_change"]:
        return (
            "STAGE: RESOLUTION.\n"
            "The manager is proposing a change or way forward. Respond to THE PROPOSAL, not the past.\n"
            "If it is reasonable and specific, accept it in ONE short sentence in your own words. "
            "Do NOT copy her wording. Do NOT ask a question. Do NOT apologise again if you already did.\n"
            "If it is vague or unfair, say so politely and ask what exactly she expects."
        )

    if state["manager_closing"]:
        return (
            "STAGE: CLOSING.\n"
            "The manager is closing the conversation. Reply with a short statement (3-12 words). "
            "No question. Do not reopen the issue."
        )

    return (
        "STAGE: DISCUSSION.\n"
        "The manager is still discussing the issue. Respond to exactly what she just said. "
        "If she asked you a question, ANSWER it. Do not answer a question with a question. "
        "You may explain a little or disagree respectfully. "
        "Do not agree to a specific change until she has proposed one."
    )


def build_question_rule(state):
    if state["allow_question"]:
        return (
            "You MAY ask at most one short question if it feels natural. "
            "Most replies should still be statements."
        )
    return "Do NOT ask any question in this reply. Make statements only. Your reply must not contain a question mark."


def build_state_flags(state):
    yes_no = lambda v: "yes" if v else "no"

    return (
        f"- Rohit's mood right now: {state['mood']}. {MOOD_GUIDANCE[state['mood']]}\n"
        f"- May hint at 'some things going on outside work' (no details): {yes_no(state['may_hint_personal'])}\n"
        f"- Rohit has already apologised: {yes_no(state['already_apologised'])}\n"
        f"- Rohit has already explained that mornings are hard: {yes_no(state['already_explained'])}\n"
        f"- Rohit has already agreed to a change: {yes_no(state['already_agreed'])}\n"
        f"- Questions Rohit has already asked: {state['questions_so_far']}\n"
        f"- Rohit's previous reply (do not repeat its wording): "
        f"{state['last_rohit_line'] or 'none'}"
    )


# =========================================================
# BUILD REHEARSAL PROMPT
# =========================================================

def build_rehearsal_prompt(manager_message, conversation, state=None):
    employee = load_employee_record()
    template = load_prompt()

    state = state or analyse_conversation(manager_message, conversation)
    safe_context = build_safe_employee_context(employee, state["topics"])

    prompt = template
    prompt = prompt.replace("{{EMPLOYEE_CONTEXT}}", json.dumps(safe_context, indent=2, ensure_ascii=False))
    prompt = prompt.replace("{{CONVERSATION}}", build_conversation_history(conversation))
    prompt = prompt.replace("{{TURN_NUMBER}}", str(state["turn_number"]))
    prompt = prompt.replace("{{STATE_FLAGS}}", build_state_flags(state))
    prompt = prompt.replace("{{STAGE_GUIDANCE}}", build_stage_guidance(state))
    prompt = prompt.replace("{{QUESTION_RULE}}", build_question_rule(state))
    # manager message LAST
    prompt = prompt.replace("{{MANAGER_MESSAGE}}", manager_message)

    return prompt


# =========================================================
# CLEAN / ENFORCE MODEL RESPONSE
# =========================================================

_PREFIX = re.compile(
    r"^\s*(?:rohit(?:\s*[—-]\s*simulated employee)?|simulated employee(?:\s*[—-]\s*rohit)?|employee)\s*:\s*",
    re.IGNORECASE,
)

_FILLER_OPENING = re.compile(
    r"^\s*(?:i understand|i see|i appreciate|thank you for)\b[^.,!?]*[.,!]\s*", re.IGNORECASE
)

# phrases that mean Rohit is re-opening an issue that is already settled
_REOPEN = re.compile(
    r"\b(talk about (that|it|this) now|address the|discuss (that|it|this) (now|again)|"
    r"i(?:'d| would) like to (address|discuss|talk)|sorry (for|about)|apolog)",
    re.IGNORECASE,
)
SETTLED_FALLBACKS = ["Sounds good.", "Okay, that works for me.", "Alright, fair enough.", "Sure, will do."]

FALLBACK_BY_INTENT = {
    "small_talk": "Doing alright, thanks.",
    "severe": "Wait, what? Why are you saying that?",
    "unclear": "Sorry, I didn't catch that. Can you say it again?",
    "off_topic": "Uh, sorry, what do you mean?",
    "caring_question": "I'm managing. Thanks for asking.",
}


def _split_sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def clean_rohit_response(response, state=None):
    if not response:
        return ""

    response = response.strip().replace("```text", "").replace("```", "").strip()

    while _PREFIX.match(response):
        response = _PREFIX.sub("", response, count=1).strip()

    response = re.split(r"\n\s*(?:MANAGER|ADITI|ROHIT)\s*:", response, flags=re.IGNORECASE)[0]
    response = re.sub(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*", "", response)
    response = re.sub(r"\s+", " ", response).strip()

    if len(response) >= 2 and response[0] == '"' and response[-1] == '"':
        response = response[1:-1].strip()

    intent = state["intent"] if state else "other"
    max_sentences = 3

    if state:
        # nobody says the boss's name in every sentence
        if state["turn_number"] > 1:
            response = re.sub(r",?\s*\bAditi\b(?=\s*[.,!?])", "", response)
            response = re.sub(r"^[\s,.]+", "", response)

            stripped = _FILLER_OPENING.sub("", response, count=1).strip()
            if stripped:
                response = stripped

        if intent == "small_talk":
            max_sentences = 2
        elif state["already_agreed"] or state["manager_proposes_change"]:
            max_sentences = 2

    sentences = _split_sentences(response)

    # ENFORCE: once he has agreed, he must not re-open the issue (normal discussion only)
    if state and state["already_agreed"] and intent == "other":
        kept = [x for x in sentences if not _REOPEN.search(x)]
        if not kept:
            kept = [SETTLED_FALLBACKS[state["turn_number"] % len(SETTLED_FALLBACKS)]]
        sentences = kept

    # ENFORCE: a real employee does not end every turn with a question
    if state and not state["allow_question"]:
        statements = [s for s in sentences if not s.rstrip().endswith("?")]
        sentences = statements if statements else [FALLBACK_ACCEPTANCE]

    return " ".join(sentences[:max_sentences]).strip()


# =========================================================
# GET ROHIT RESPONSE
# =========================================================

def get_rohit_response(manager_message, conversation):
    manager_message = str(manager_message or "").strip()

    if not manager_message:
        raise ValueError("Manager message cannot be empty.")

    if not isinstance(conversation, list):
        raise ValueError("Conversation must be a list.")

    state = analyse_conversation(manager_message, conversation)
    prompt = build_rehearsal_prompt(manager_message, conversation, state)

    print("\n" + "=" * 70)
    print("MANAGER:", manager_message)
    print("STATE:", {k: v for k, v in state.items() if k != "last_rohit_line"})

    response = ""
    for attempt in range(2):
        raw = generate_response(
            prompt,
            temperature=0.8,
            max_tokens=120,
            provider=ROHIT_PROVIDER,
        )
        response = clean_rohit_response(raw, state)
        if response:
            break
        print(f"Empty reply after cleaning (attempt {attempt + 1}), retrying...")

    if not response:
        response = FALLBACK_BY_INTENT.get(state["intent"], FALLBACK_ACCEPTANCE)

    print("ROHIT:", response)
    print("=" * 70)

    return response