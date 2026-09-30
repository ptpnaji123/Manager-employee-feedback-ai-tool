import json
import re
from pathlib import Path

from services.llm_service import generate_response


BASE_DIR = Path(__file__).resolve().parent.parent

EMPLOYEE_FILE = BASE_DIR / "employee_record.json"
PROMPT_FILE = BASE_DIR / "prompts" / "rehearsal_prompt.txt"

MAX_HISTORY_TURNS = 14
MAX_QUESTIONS_PER_CONVERSATION = 2   # a real employee asks very few questions
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
# SAFE EMPLOYEE CONTEXT
# =========================================================

def build_safe_employee_context(employee):
    return {
        "employee": {
            "name": employee["name"],
            "role": employee["role"],
            "tenure_months": employee["tenure_months"],
            "manager_name": employee["manager_name"],
        },
        "performance": {
            "current_cycle_rating": employee["performance"]["current_cycle_rating"],
            "previous_cycle_rating": employee["performance"]["previous_cycle_rating"],
            "trend": employee["performance"]["trend"],
            "last_reviewed": employee["performance"]["last_reviewed"],
        },
        "goals": employee["goals"],
        "attendance": {
            "scheduled_start": employee["attendance"]["scheduled_start"],
            "late_arrivals_last_90_days": employee["attendance"]["late_arrivals_last_90_days"],
            "average_lateness_minutes": employee["attendance"]["average_lateness_minutes"],
            "pattern_note": employee["attendance"]["pattern_note"],
            "prior_conversation_logged": employee["attendance"]["prior_conversation_logged"],
        },
    }


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
# CONVERSATION STATE
# =========================================================

CHANGE_PATTERNS = [
    "from tomorrow", "from now on", "going forward", "moving forward", "onwards",
    "onward", "be on time", "start on time", "arrive on time", "arrive at work",
    "by 9:30", "by 09:30", "by nine thirty", "i need you to", "i'd like you to",
    "i would like you to", "can you commit", "let's agree", "lets agree", "we agree",
    "agree that", "check in", "follow up", "follow-up", "review this", "next week",
    "in two weeks", "in a month", "let's move on", "lets move on", "move on",
    "weekly", "one on one", "one-on-one", "1:1", "every week", "every monday",
    "inform", "let me know", "let your team know", "tell your team",
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
    "going through", "rough", "challenging",
]

QUESTION_STARTS = (
    "why", "what", "how", "when", "where", "who", "could", "can", "would",
    "will", "is", "are", "do", "does", "did", "have", "has", "should",
)


def _contains_any(text, patterns):
    text = text.lower()
    return any(p in text for p in patterns)


def _manager_asked_question(message):
    # speech recognition gives no "?", so also look at the first word
    message = message.strip().lower()
    if "?" in message:
        return True
    first = re.sub(r"^(okay|ok|so|and|well|now|rohit)[,\s]+", "", message).split(" ")[0]
    return first in QUESTION_STARTS


def analyse_conversation(manager_message, conversation):
    turns = _clean_turns(conversation)
    rohit_lines = [t for s, t in turns if s == "rohit"]
    rohit_text = " ".join(rohit_lines)

    state = {
        "turn_number": len(rohit_lines) + 1,
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

    # A question from Rohit is only allowed rarely, and never once things are settled,
    # never right after he asked one, and never when he has just been asked something.
    state["allow_question"] = (
        not state["last_reply_had_question"]
        and state["questions_so_far"] < MAX_QUESTIONS_PER_CONVERSATION
        and not state["already_agreed"]
        and not state["manager_proposes_change"]
        and not state["manager_closing"]
        and not state["manager_asked_question"]
    )

    return state


def build_stage_guidance(state):
    if state["turn_number"] == 1:
        return (
            "STAGE: OPENING.\n"
            "This is your first reply. Respond only to what the manager just said. "
            "If she only greeted you, greet her back briefly and wait. "
            "If she already raised lateness, react like a real person hearing it: "
            "acknowledge one specific thing she said and sound a little surprised or guarded. "
            "Do NOT agree to change anything yet. Do NOT explain your reasons yet."
        )

    if state["already_agreed"]:
        return (
            "STAGE: FOLLOW-UP (you have ALREADY agreed).\n"
            "The main issue is settled. React to what she just said with a short STATEMENT "
            "(3-20 words), like a colleague would: 'Sure, that works.' / 'Okay, I'll do that.' / "
            "'Fine by me.' / 'Alright, thanks.'\n"
            "- Do NOT ask a question.\n"
            "- Do NOT repeat her words back to her.\n"
            "- Do NOT restate the agreement again in full.\n"
            "- Do NOT apologise again and do NOT explain your difficulties again.\n"
            "- Do NOT go back to the lateness problem or ask to discuss it again."
        )

    if state["manager_proposes_change"]:
        return (
            "STAGE: RESOLUTION.\n"
            "The manager is proposing a change or way forward. Respond to THE PROPOSAL, not the past.\n"
            "If it is reasonable, accept it in ONE short natural sentence in your own words "
            "(for example: 'Okay, fair. I'll be in by 9:30.'). Do NOT copy her wording. "
            "Do NOT ask a question. Do NOT apologise again if you already did. "
            "Do NOT explain again why mornings are hard.\n"
            "Only push back if the proposal is vague or unfair."
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
        "If she asked you a question, ANSWER it - do not answer a question with a question. "
        "You may explain a little or disagree respectfully. "
        "Do not agree to a specific change until she has proposed one."
    )


def build_question_rule(state):
    if state["allow_question"]:
        return (
            "You MAY ask at most one short question, but only if you genuinely need something clarified. "
            "Most of your replies should be statements."
        )
    return "Do NOT ask any question in this reply. Make statements only. Your reply must not contain a question mark."


def build_state_flags(state):
    yes_no = lambda v: "yes" if v else "no"
    return (
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

    safe_context = build_safe_employee_context(employee)
    state = state or analyse_conversation(manager_message, conversation)

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

_FILLER_OPENING = re.compile(r"^\s*(?:i understand|i see|i appreciate|thank you for)\b[^.,!?]*[.,!]\s*", re.IGNORECASE)

# phrases that mean Rohit is re-opening an issue that is already settled
_REOPEN = re.compile(
    r"\b(talk about (that|it|this) now|address the|discuss (that|it|this) (now|again)|"
    r"i(?:'d| would) like to (address|discuss|talk)|sorry (for|about)|apolog)",
    re.IGNORECASE,
)
SETTLED_FALLBACKS = ["Sounds good.", "Okay, that works for me.", "Alright, fair enough.", "Sure, will do."]


def _split_sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def clean_rohit_response(response, state=None):
    if not response:
        return ""

    response = response.strip().replace("```text", "").replace("```", "").strip()

    while _PREFIX.match(response):
        response = _PREFIX.sub("", response, count=1).strip()

    response = re.split(r"\n\s*(?:MANAGER|ADITI|ROHIT)\s*:", response, flags=re.IGNORECASE)[0]
    response = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", response)
    response = re.sub(r"\s+", " ", response).strip()

    if len(response) >= 2 and response[0] == '"' and response[-1] == '"':
        response = response[1:-1].strip()

    if state:
        # nobody says the boss's name in every sentence
        if state["turn_number"] > 1:
            response = re.sub(r",?\s*\bAditi\b(?=\s*[.,!?])", "", response)
            response = re.sub(r"^[\s,.]+", "", response)

        # remove the robotic "I understand, ..." opener
        if state["turn_number"] > 1:
            stripped = _FILLER_OPENING.sub("", response, count=1).strip()
            if stripped:
                response = stripped

        # settled conversation -> keep it short (max 2 sentences)
        max_sentences = 2 if (state["already_agreed"] or state["manager_proposes_change"]) else 3
    else:
        max_sentences = 3

    sentences = _split_sentences(response)

    # ENFORCE: once he has agreed, he must not re-open the issue
    if state and state["already_agreed"]:
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
        raw = generate_response(prompt, temperature=0.7, max_tokens=90)
        response = clean_rohit_response(raw, state)
        if response:
            break
        print(f"Empty reply after cleaning (attempt {attempt + 1}), retrying...")

    if not response:
        raise RuntimeError("Ollama returned an empty employee response.")

    print("ROHIT:", response)
    print("=" * 70)

    return response