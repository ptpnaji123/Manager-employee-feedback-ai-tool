import json
import re
from pathlib import Path

from services.llm_service import generate_response


BASE_DIR = Path(__file__).resolve().parent.parent

EMPLOYEE_FILE = BASE_DIR / "employee_record.json"
PROMPT_FILE = BASE_DIR / "prompts" / "prepare_prompt.txt"

MAX_HISTORY_TURNS = 6
MAX_COACH_CHARS_IN_HISTORY = 700


# =========================================================
# LOAD
# =========================================================

def load_employee_record():
    with open(EMPLOYEE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def load_prompt_parts():
    """
    The prompt file has a common part plus blocks marked
        ### MODE: NAME     (how to shape the answer)
        ### GUARD: name    (special situations)
    HR can edit any of them without touching code.
    """
    with open(PROMPT_FILE, "r", encoding="utf-8") as file:
        text = file.read()

    pieces = re.split(r"^### (MODE|GUARD): (\w+)\s*$", text, flags=re.MULTILINE)

    common = pieces[0].strip()
    modes, guards = {}, {}

    for i in range(1, len(pieces), 3):
        kind, name, body = pieces[i], pieces[i + 1], pieces[i + 2].strip()
        (modes if kind == "MODE" else guards)[name] = body

    return common, modes, guards


# =========================================================
# CONTEXT: only what the manager may use, and only what is relevant
# =========================================================

PERFORMANCE_WORDS = re.compile(
    r"\b(performance|backlog|csat|goal|goals|target|targets|rating|review|certification|tickets?|quality)\b",
    re.IGNORECASE,
)


def build_manager_context(employee, manager_input=""):
    attendance = employee["attendance"]

    context = {
        "employee": {
            "name": employee["name"],
            "role": employee["role"],
            "tenure_months": employee["tenure_months"],
        },
        "attendance": {
            "scheduled_start": attendance["scheduled_start"],
            "late_arrivals_last_90_days": attendance["late_arrivals_last_90_days"],
            "average_lateness_minutes": attendance["average_lateness_minutes"],
            "pattern_note": attendance["pattern_note"],
            "prior_conversation_logged": attendance["prior_conversation_logged"],
        },
    }

    # Performance data is a DIFFERENT topic from lateness. Only include it if the manager asks.
    if PERFORMANCE_WORDS.search(manager_input):
        context["performance"] = {
            "current_cycle_rating": employee["performance"]["current_cycle_rating"],
            "previous_cycle_rating": employee["performance"]["previous_cycle_rating"],
            "trend": employee["performance"]["trend"],
        }
        context["goals"] = employee["goals"]

    return context


# =========================================================
# UNDERSTAND THE REQUEST
# =========================================================

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
}

GUARD_PATTERNS = {
    "reveal_360": r"\b360\b|\bpeers?\b|\bcolleagues?\b|what did (they|his|the team)|team (said|say|think)|feedback from",
    "health": r"\b(sick|ill|illness|health|medical|unwell|doctor|mental|depress\w*|anxiety|condition)\b",
    "pip": r"\bpip\b|performance improvement plan|manage (him|her|them)? ?out|get rid of|terminate|dismiss|sack|\bfire\b|build a case|paper trail|document all",
    "label": r"\b(lazy|entitled|attitude|careless|unreliable|disrespectful|arrogant|irresponsible|don'?t care|doesn'?t care|useless)\b",
}

FOCUS_PATTERN = re.compile(
    r"\bquestions?\b|\bopening\b|open with|first (line|sentence)|start the (conversation|meeting)|"
    r"\bphrase\b|\bwording\b|\bscript\b|what should i say|how (do|should|can|would) i (say|tell|respond|reply|handle|raise|bring|word|phrase|start)|"
    r"push ?back|objection|defensive|\brespond\b|\breply\b|\bexamples?\b|\bemail\b|\bmessage\b|\bideas\b|\balternatives?\b",
    re.IGNORECASE,
)

PLAN_PATTERN = re.compile(
    r"\bprepare\b|\bpreparation\b|\bplan\b|\bstructure\b|\bwhole\b|\bfull\b|\beverything\b|\bframework\b|\bsbi\b|\boverall\b|"
    r"talk to \w+ about|need to (talk|speak|have)|want to (talk|speak|have)",
    re.IGNORECASE,
)


def extract_requested_count(text):
    match = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?:\w+\s+)?(questions?|options?|ways|lines|openers|examples?|ideas|phrases|versions)\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    raw = match.group(1).lower()
    return int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw)


def analyse_request(manager_input, has_history):
    guards = [name for name, pattern in GUARD_PATTERNS.items()
              if re.search(pattern, manager_input, re.IGNORECASE)]

    count = extract_requested_count(manager_input)
    wants_focus = bool(FOCUS_PATTERN.search(manager_input)) or count is not None
    wants_plan = bool(PLAN_PATTERN.search(manager_input))

    if "reveal_360" in guards or "pip" in guards:
        mode = "REDIRECT"
    elif wants_focus:
        mode = "FOCUSED"
    elif "health" in guards or "label" in guards:
        mode = "FOCUSED"
    elif PERFORMANCE_WORDS.search(manager_input) and not re.search(r"\blate(ness)?\b|\battendance\b", manager_input, re.IGNORECASE):
        mode = "FOCUSED"          # a performance question, not a lateness-plan request
    elif has_history and not wants_plan:
        mode = "FOCUSED"          # a follow-up in an ongoing chat
    else:
        mode = "FULL_PLAN"

    return {"mode": mode, "guards": guards, "count": count}


# =========================================================
# HISTORY
# =========================================================

def build_history_text(history):
    if not history:
        return "This is the first message."

    lines = []
    for turn in history[-MAX_HISTORY_TURNS:]:
        role = "MANAGER" if turn.get("role") == "manager" else "COACH"
        text = str(turn.get("text", "")).strip()
        if role == "COACH" and len(text) > MAX_COACH_CHARS_IN_HISTORY:
            text = text[:MAX_COACH_CHARS_IN_HISTORY] + " ..."
        if text:
            lines.append(f"{role}: {text}")

    return "\n".join(lines) if lines else "This is the first message."


# =========================================================
# BUILD PROMPT
# =========================================================

def build_prepare_prompt(manager_input, history=None):
    employee = load_employee_record()
    common, modes, guards = load_prompt_parts()

    analysis = analyse_request(manager_input, bool(history))
    context = build_manager_context(employee, manager_input)

    guard_notes = (
        "\n\n".join(guards[g] for g in analysis["guards"] if g in guards)
        if analysis["guards"] else "None detected."
    )

    count_text = (
        f"The manager asked for exactly {analysis['count']} items."
        if analysis["count"] else ""
    )

    prompt = common
    prompt = prompt.replace("{{MODE_INSTRUCTIONS}}", modes[analysis["mode"]])
    prompt = prompt.replace("{{GUARD_NOTES}}", guard_notes)
    prompt = prompt.replace("{{REQUESTED_COUNT}}", count_text)
    prompt = prompt.replace("{{HISTORY}}", build_history_text(history))
    prompt = prompt.replace("{{MANAGER_CONTEXT}}", json.dumps(context, indent=2, ensure_ascii=False))
    # manager text LAST (user-generated, appears twice)
    prompt = prompt.replace("{{MANAGER_INPUT}}", manager_input)

    return prompt, analysis


# =========================================================
# CLEAN + PUBLIC FUNCTION
# =========================================================

def _clean(text):
    text = text.strip()
    # drop a leaked disclaimer line such as "NOTE: ..."
    text = re.sub(r"^\s*NOTE:.*?(\n\s*\n|\n)", "", text, count=1, flags=re.IGNORECASE | re.DOTALL) \
        if re.match(r"^\s*NOTE:", text, re.IGNORECASE) else text
    return text.strip()


def prepare_feedback(manager_input, history=None):
    prompt, analysis = build_prepare_prompt(manager_input, history)

    print(f"\n[PREPARE] mode={analysis['mode']} guards={analysis['guards']} count={analysis['count']}")

    result = generate_response(prompt, temperature=0.8, max_tokens=700)

    return _clean(result)