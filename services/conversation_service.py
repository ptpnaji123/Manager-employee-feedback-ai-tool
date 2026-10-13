import json
import re
from pathlib import Path

from services.llm_service import generate_response
from services.meeting_memory import (
    format_for_prompt,
    get_snapshot,
    rebuild_from_conversation,
    update_async,
    wait_for_update,
)


BASE_DIR = Path(__file__).resolve().parent.parent

EMPLOYEE_FILE = BASE_DIR / "employee_record.json"
PROMPT_FILE = BASE_DIR / "prompts" / "rehearsal_prompt.txt"

# "groq" = Llama 3.3 70B (set GROQ_LLM_MODEL in .env to change). "ollama" = local Mistral.
ROHIT_PROVIDER = "groq"
# Small, fast model used only to label ambiguous manager lines.
CLASSIFIER_MODEL = "llama-3.1-8b-instant"

MAX_HISTORY_TURNS = 20
MAX_QUESTIONS_PER_CONVERSATION = 3
NEUTRAL_FALLBACK = "Give me a second, let me think about that."


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


def _format_turns(turns):
    return "\n".join(
        f"{'MANAGER' if s == 'manager' else 'ROHIT'}: {t}" for s, t in turns
    )


def build_conversation_history(conversation):
    turns = _clean_turns(conversation)

    if not turns:
        return "No previous conversation."

    return _format_turns(turns[-MAX_HISTORY_TURNS:])


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
    "going through", "rough", "challenging", "going on", "outside work", "tough",
]

QUESTION_STARTS = (
    "why", "what", "how", "when", "where", "who", "could", "can", "would",
    "will", "is", "are", "do", "does", "did", "have", "has", "should",
)

# Serious consequences for his job: dismissal, suspension, final warning.
SEVERE = re.compile(
    r"\b(terminat\w*|fired|sacked|let you go|letting you go|let go|dismiss\w*|suspend\w*|"
    r"show you the door|you(?:'re| are) out|out of the company|your last day|"
    r"last warning|final warning|written warning|start the process|"
    r"pack your (things|stuff|bags)|all the best for your future)\b",
    re.I,
)

# "you have not been fired", "you're not being terminated": these must not count as severe news.
_TERMS = r"(?:terminat\w*|fired|sacked|let go|dismiss\w*|suspend\w*)"
NEGATED = re.compile(
    rf"\b(?:not|never|no|isn'?t|aren'?t|wasn'?t|weren'?t|haven'?t|hasn'?t|won'?t|don'?t)\b"
    rf"(?:\s+\w+){{0,3}}\s+{_TERMS}",
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
    r"is there anything|can i help|how can i (help|support)|help you with|what support)",
    re.I,
)

# She asks HIM for a way forward.
ASKS_INPUT = re.compile(
    r"\b(how (can|do|should|could|would) we (solve|fix|resolve|handle|address|improve|move|sort)|"
    r"what (can|do|should|would) we do|what do you (suggest|propose|think|recommend)|"
    r"any (suggestions|ideas)|what would help|what (do|would) you (need|like)|"
    r"your (thoughts|view|suggestion|plan)|how do you plan|what('s| is) your plan|"
    r"how (will|are) you (fix|solve|make sure|going to))\b",
    re.I,
)

# She asks whether he remembers / heard what she said.
RECALL = re.compile(
    r"\b(what (i|did i) (said|say|told|mention\w*)|do you (know|remember) what i|"
    r"did you (hear|catch|get) what i|as i (said|mentioned) (earlier|before)|"
    r"what i (said|told you) (earlier|before)|just before this (talk|conversation|meeting))\b",
    re.I,
)

ACCUSE = re.compile(
    r"\b(always|never|lazy|careless|unreliable|unacceptable|not good enough|don'?t care|"
    r"doesn'?t care|disappointed|disrespectful|irresponsible|useless|entitled|attitude|"
    r"what is wrong with you|your fault|dig your own (hole|grave))\b",
    re.I,
)

LATENESS_WORDS = re.compile(
    r"\b(late|lateness|attendance|on time|9:30|nine thirty|punctual\w*|arriv\w*|mornings?)\b", re.I
)
PERF_WORDS = re.compile(
    r"\b(performance|backlog|csat|goals?|targets?|rating|review|certification|tickets?)\b", re.I
)

SHORT_OK = re.compile(
    r"\b(thanks|thank|okay|ok|right|sure|yes|yeah|no|good|great|fine|alright|sorry|hello|hi|hey)\b", re.I
)


def is_heavy(text):
    """True if the line announces or threatens serious consequences (ignoring negated mentions)."""
    return bool(SEVERE.search(NEGATED.sub(" ", text)))


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

INTENT_LABELS = ["small_talk", "caring_question", "off_topic", "unclear", "other"]

HEAVY_BASE = (
    "Aditi just told you something with serious consequences for your job (for example dismissal, "
    "suspension or a final warning). Do NOT promise to change anything and do NOT agree to anything "
    "you are not being asked to agree to. Do not argue about rules or rights (no 'you can't do this').\n"
)

HEAVY_PHASES = {
    1: "This is the FIRST time you hear it. React with stunned disbelief in a few words, and ask "
       "what has happened or why. Do not defend yourself yet.",
    2: "It is sinking in. Do not repeat your earlier shocked words. If the reason she gave is partly "
       "true, admit that part honestly in one short clause. Then say it feels out of proportion and "
       "mention something you have done well (use only the facts you know above). Do not beg.",
    3: "You are past the shock. Go flat and quiet, or a bit bitter, or ask something practical "
       "(is it final, notice, handover). Never repeat an earlier reaction.",
}

INTENT_GUIDANCE = {
    "small_talk": (
        "Aditi is greeting you or making small talk. Answer like a normal person at work, "
        "in one short, light sentence. Do NOT mention lateness, attendance, goals, tickets or any "
        "work problem. You do not know why she wants to talk yet. Do not comment on her mood or "
        "schedule. You may ask one short, natural question back."
    ),
    "caring_question": (
        "Aditi asked an open, caring question about you. Answer honestly but briefly and in general "
        "words, as someone who is private. Only if the state below says you may, hint that there are "
        "a few things going on outside work, with no details. Do not recite facts or numbers and do "
        "not promise anything."
    ),
    "off_topic": (
        "Aditi said something unrelated to work. React with mild confusion or a short natural answer. "
        "Do not steer the conversation back to any work issue yourself."
    ),
    "unclear": (
        "You did not catch or understand what Aditi said. Say so naturally and briefly, for example "
        "asking her to repeat it. Do not guess what she meant."
    ),
    "asks_input": (
        "Aditi is asking YOU for a way forward. Answer with statements, not a question. Offer one "
        "realistic, modest step you could take, in your own words, or say what would make it easier "
        "for you without giving private details. Stay consistent with the facts above. If something "
        "serious about your job was said earlier, that changes how willing you are."
    ),
    "recall": (
        "Aditi is checking whether you remember what she said earlier. Answer from the conversation "
        "so far, in your own words, and stay accurate. Do not invent anything she did not say."
    ),
}

AFTER_HEAVY_NEWS = (
    "Something serious about your job was said earlier in this meeting. Check the facts above to see "
    "whether it still stands. React to her new line in that light and with the feelings listed above. "
    "If she blames or insults you, respond to that (hurt, bitter or calm pushback), never ignore it. "
    "If the reason she gave is partly true, admit that part honestly, but say if the consequence feels "
    "out of proportion and mention what you have done well (only facts you know above). "
    "Do not beg and do not promise to change anything unless she clearly proposes a concrete plan. "
    "Do not repeat an earlier reaction."
)

# intents where Rohit may reply with a question
QUESTION_FRIENDLY = {"small_talk", "off_topic"}
QUESTION_ALWAYS = {"heavy_news", "unclear"}


def classify_intent(manager_message, prior_manager_lines, work_topic_raised, conversation_tail):
    words = len(manager_message.split())

    if is_heavy(manager_message):
        return "heavy_news"

    if RECALL.search(manager_message):
        return "recall"

    # Small talk only counts at the start, before any work topic or serious news.
    if (
        SMALL_TALK.search(manager_message)
        and words <= 8
        and not work_topic_raised
        and not any(is_heavy(m) for m in prior_manager_lines)
    ):
        return "small_talk"

    if CARING.search(manager_message):
        return "caring_question"

    if ASKS_INPUT.search(manager_message):
        return "asks_input"

    if words <= 2 and not SHORT_OK.search(manager_message):
        return "unclear"

    prompt = (
        "Classify the manager's LAST line in a workplace conversation with an employee.\n"
        "Labels: small_talk, caring_question, off_topic, unclear, other\n"
        "- small_talk: a greeting or casual chit-chat at the very start, unrelated to the topic\n"
        "- caring_question: asks how the employee is really doing or what is getting in the way\n"
        "- off_topic: clearly unrelated to work and to the conversation\n"
        "- unclear: garbled, cut off or meaningless\n"
        "- other: anything else, including follow-ups, questions, feedback, accusations, proposals, "
        "answers and closing\n"
        "If the line continues the ongoing discussion it is other, even if it begins with a greeting "
        "or the employee's name. When unsure, answer other.\n\n"
        f"Conversation so far:\n{conversation_tail or '(start of conversation)'}\n\n"
        f'Last line: "{manager_message}"\n'
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
        "strengths": False,
    }


MOOD_AFTER_CARING = {"defensive": "guarded", "guarded": "neutral", "neutral": "open", "open": "open"}
MOOD_AFTER_ACCUSE = {"neutral": "guarded", "open": "guarded", "guarded": "defensive", "defensive": "defensive"}

MOOD_GUIDANCE = {
    "neutral": "Calm and a little reserved. Normal professional tone.",
    "open": "Feels heard and is more relaxed. Answers a bit more openly, but is still private.",
    "guarded": "Feels judged. Gives shorter answers, is a little cold, and shares less.",
    "defensive": "Feels attacked. Objects calmly but firmly and gives very little away.",
}


def compute_mood(manager_messages, current_intent):
    mood = "neutral"

    for message in manager_messages:
        if ACCUSE.search(message):
            mood = MOOD_AFTER_ACCUSE[mood]
        elif CARING.search(message):
            mood = MOOD_AFTER_CARING[mood]

    # the current line, when only the model-based classifier recognised it as caring
    if current_intent == "caring_question" and not CARING.search(manager_messages[-1]):
        mood = MOOD_AFTER_CARING[mood]

    if any(is_heavy(m) for m in manager_messages) and mood in ("neutral", "open"):
        mood = "guarded"

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
    elif topics.get("strengths"):
        # He knows what he has done well, and may use it to defend himself.
        # Missed goals stay hidden unless Aditi raises performance herself.
        context["things_you_have_done_well"] = [
            g for g in employee["goals"] if g.get("status") != "missed"
        ]

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
    prior_manager = manager_lines[:-1]
    rohit_text = " ".join(rohit_lines)

    topics = topics_raised(manager_message, conversation)
    work_topic_raised = topics["lateness"] or topics["performance"]
    tail = _format_turns(turns[-4:])

    intent = classify_intent(manager_message, prior_manager, work_topic_raised, tail)
    severe_count = sum(1 for m in prior_manager if is_heavy(m))

    # Once his job is on the line he knows his own record and may defend himself with it.
    if severe_count > 0 or intent == "heavy_news":
        topics["strengths"] = True
        topics["lateness"] = True

    state = {
        "turn_number": len(rohit_lines) + 1,
        "intent": intent,
        "topics": topics,
        "mood": compute_mood(manager_lines, intent),
        "severe_count": severe_count,
        "manager_proposes_change": _contains_any(manager_message, CHANGE_PATTERNS),
        "manager_closing": _contains_any(manager_message, CLOSING_PATTERNS),
        "manager_asked_question": _manager_asked_question(manager_message),
        "already_apologised": _contains_any(rohit_text, APOLOGY_PATTERNS),
        "already_explained": _contains_any(rohit_text, EXPLAINED_PATTERNS),
        "already_agreed": _contains_any(rohit_text, AGREE_PATTERNS),
        "questions_so_far": sum(1 for t in rohit_lines if "?" in t),
        "last_reply_had_question": bool(rohit_lines and "?" in rohit_lines[-1]),
        "last_rohit_line": rohit_lines[-1] if rohit_lines else "",
        "recent_rohit": rohit_lines[-3:],
        "previous_manager_line": prior_manager[-1] if prior_manager else "",
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
    elif state["severe_count"] > 0 and not state["last_reply_had_question"] \
            and not state["manager_asked_question"]:
        allow = True

    # When she asks him something, he answers; he does not ask back.
    if intent in ("asks_input", "recall"):
        allow = False

    state["allow_question"] = allow

    state["may_hint_personal"] = (
        (state["mood"] == "open" or intent == "caring_question")
        and not state["already_explained"]
        and state["severe_count"] == 0
        and intent != "heavy_news"
    )

    return state


def build_stage_guidance(state):
    intent = state["intent"]

    if intent == "heavy_news":
        phase = min(state["severe_count"] + 1, 3)
        return f"STAGE: HEAVY NEWS (time {phase}).\n{HEAVY_BASE}{HEAVY_PHASES[phase]}"

    if intent == "recall":
        previous = state["previous_manager_line"]
        extra = (
            f'\nThe last thing she said before this line was: "{previous}"\n'
            "If that line was garbled or meaningless, say you did not quite catch it."
            if previous else
            "\nShe has not said anything substantial yet, so say so honestly."
        )
        return f"STAGE: RECALL.\n{INTENT_GUIDANCE['recall']}{extra}"

    if intent in INTENT_GUIDANCE:
        return f"STAGE: {intent.upper()}.\n{INTENT_GUIDANCE[intent]}"

    if state["severe_count"] > 0:
        return f"STAGE: AFTER SERIOUS NEWS.\n{AFTER_HEAVY_NEWS}"

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
        "The manager is still discussing the issue. Respond to exactly what she just said, "
        "consistent with the facts above. If she asked you a question, ANSWER it with a statement. "
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
        f"- Tone towards Aditi: {state['mood']}. {MOOD_GUIDANCE[state['mood']]}\n"
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

def build_rehearsal_prompt(manager_message, conversation, state, situation):
    employee = load_employee_record()
    template = load_prompt()

    safe_context = build_safe_employee_context(employee, state["topics"])

    prompt = template
    prompt = prompt.replace("{{EMPLOYEE_CONTEXT}}", json.dumps(safe_context, indent=2, ensure_ascii=False))
    prompt = prompt.replace("{{SITUATION}}", situation)
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

# the vague personal hint, only allowed when the state says so
_PERSONAL_HINT = re.compile(
    r"outside (of )?work|things (going on|at home)|take my drift", re.IGNORECASE
)

SETTLED_FALLBACKS = ["Sounds good.", "Okay, that works for me.", "Alright, fair enough.", "Sure, will do."]

FALLBACK_BY_INTENT = {
    "small_talk": "Doing alright, thanks.",
    "heavy_news": "Sorry, can you explain that? I'm not following.",
    "unclear": "Sorry, I didn't catch that. Can you say it again?",
    "off_topic": "Uh, sorry, what do you mean?",
    "caring_question": "I'm managing. Thanks for asking.",
    "asks_input": "Honestly, I need a moment to think about what would actually help.",
    "recall": "Sorry, I'm not sure I caught that properly.",
}


def _split_sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def clean_rohit_response(response, state=None):
    """Returns "" when nothing usable is left, so the caller can ask the model again."""
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

        if intent in ("small_talk", "heavy_news"):
            max_sentences = 2
        elif state["already_agreed"] or state["manager_proposes_change"]:
            max_sentences = 2

    sentences = _split_sentences(response)

    # ENFORCE: once he has agreed, he must not re-open the issue (normal discussion only)
    if state and state["already_agreed"] and intent == "other" and state["severe_count"] == 0:
        kept = [x for x in sentences if not _REOPEN.search(x)]
        if not kept:
            kept = [SETTLED_FALLBACKS[state["turn_number"] % len(SETTLED_FALLBACKS)]]
        sentences = kept

    # ENFORCE: the vague "things outside work" hint is only allowed when the state says so
    if state and not state["may_hint_personal"]:
        no_hint = [s for s in sentences if not _PERSONAL_HINT.search(s)]
        if no_hint:
            sentences = no_hint

    # ENFORCE: a real employee does not end every turn with a question
    if state and not state["allow_question"]:
        statements = [s for s in sentences if not s.rstrip().endswith("?")]
        if not statements:
            return ""          # only questions: let the caller try again instead of using a canned line
        sentences = statements

    return " ".join(sentences[:max_sentences]).strip()


# =========================================================
# REPEAT CHECK
# =========================================================

def _words(text):
    return re.findall(r"[a-z']+", text.lower())


def too_similar(new, recent):
    nw = _words(new)

    for old in recent:
        ow = _words(old)
        if not nw or not ow:
            continue
        if nw[:2] == ow[:2]:
            return True
        a, b = set(nw), set(ow)
        if len(a & b) / len(a | b) > 0.6:
            return True

    return False


def pick_fallback(state):
    if state["intent"] in FALLBACK_BY_INTENT:
        return FALLBACK_BY_INTENT[state["intent"]]
    if state["severe_count"] > 0:
        return "I need a minute to take this in."
    return NEUTRAL_FALLBACK


# =========================================================
# GET ROHIT RESPONSE
# =========================================================

def get_rohit_response(manager_message, conversation, session_id=None):
    manager_message = str(manager_message or "").strip()

    if not manager_message:
        raise ValueError("Manager message cannot be empty.")

    if not isinstance(conversation, list):
        raise ValueError("Conversation must be a list.")

    # ---- meeting memory (lives only while this meeting is running) ----
    situation = "Nothing has been established yet."

    if session_id:
        wait_for_update(session_id)
        snapshot = get_snapshot(session_id)

        if snapshot["turns"] == 0 and conversation:
            rebuild_from_conversation(session_id, conversation)
            snapshot = get_snapshot(session_id)

        situation = format_for_prompt(snapshot)

    state = analyse_conversation(manager_message, conversation)
    prompt = build_rehearsal_prompt(manager_message, conversation, state, situation)

    print("\n" + "=" * 70)
    print("MANAGER:", manager_message)
    print("STATE:", {k: v for k, v in state.items()
                     if k not in ("last_rohit_line", "recent_rohit", "previous_manager_line")})
    print("MEMORY:", situation.replace("\n", " | "))

    response = ""
    retry_note = ""

    for attempt in range(3):
        raw = generate_response(
            prompt + retry_note,
            temperature=0.8 if attempt == 0 else 0.9,
            max_tokens=120,
            provider=ROHIT_PROVIDER,
        )

        candidate = clean_rohit_response(raw, state)

        if not candidate:
            print(f"Unusable reply (attempt {attempt + 1}), retrying...")
            retry_note = (
                "\n\nIMPORTANT: your last attempt was unusable (empty, or only a question where a "
                "question is not allowed). Reply with one or two plain statements that answer what "
                "she just said."
            )
            continue

        response = candidate

        if not too_similar(candidate, state["recent_rohit"]):
            break

        print(f"Reply too similar to a recent one (attempt {attempt + 1}), retrying...")
        retry_note = (
            "\n\nIMPORTANT: your last attempt repeated wording you already used. "
            "Say something clearly different, with a different opening."
        )

    if not response:
        response = pick_fallback(state)

    print("ROHIT:", response)
    print("=" * 70)

    if session_id:
        update_async(session_id, manager_message, response)

    return response