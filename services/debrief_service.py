import json
import re
from pathlib import Path

from services.llm_service import generate_response


BASE_DIR = Path(__file__).resolve().parent.parent

EMPLOYEE_FILE = BASE_DIR / "employee_record.json"
PROMPT_FILE = BASE_DIR / "prompts" / "debrief_prompt.txt"

MAX_ATTEMPTS = 3


def load_employee_record():
    with open(EMPLOYEE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def load_prompt():
    with open(PROMPT_FILE, "r", encoding="utf-8") as file:
        return file.read()


def build_debrief_employee_context(employee):
    """
    Confidential 360 feedback, HR notes and compensation are intentionally excluded.
    """
    return {
        "employee": {
            "name": employee["name"],
            "role": employee["role"],
            "tenure_months": employee["tenure_months"],
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
# TRANSCRIPT HELPERS
# =========================================================

def get_manager_lines(conversation):
    return [
        str(t.get("text", "")).strip()
        for t in conversation
        if t.get("speaker") == "manager" and str(t.get("text", "")).strip()
    ]


def build_transcript_text(conversation):
    if not conversation:
        return "No rehearsal conversation was recorded."

    lines = []
    for turn in conversation:
        speaker = turn.get("speaker", "unknown")
        text = str(turn.get("text", "")).strip()
        if not text:
            continue
        if speaker == "manager":
            label = "MANAGER"
        elif speaker == "rohit":
            label = "ROHIT — SIMULATED EMPLOYEE"
        else:
            label = str(speaker).upper()
        lines.append(f"{label}: {text}")

    return "\n".join(lines)


def build_manager_lines_text(manager_lines):
    return "\n".join(f'{i}. "{line}"' for i, line in enumerate(manager_lines, 1))


def build_debrief_prompt(conversation):
    employee = load_employee_record()
    template = load_prompt()

    safe_context = build_debrief_employee_context(employee)
    manager_lines = get_manager_lines(conversation)

    prompt = template
    prompt = prompt.replace("{{EMPLOYEE_CONTEXT}}", json.dumps(safe_context, indent=2, ensure_ascii=False))
    prompt = prompt.replace("{{MANAGER_LINES}}", build_manager_lines_text(manager_lines))
    # transcript LAST: it is user-generated text
    prompt = prompt.replace("{{TRANSCRIPT}}", build_transcript_text(conversation))

    return prompt


# =========================================================
# QUOTE VALIDATION  (the model must not invent quotations)
# =========================================================

def _norm(text):
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


QUOTE_PATTERN = re.compile(
    r'(?P<head>(?:GOOD MOMENT|MOMENT TO IMPROVE)\s*\n+\s*)["“](?P<quote>.+?)["”]',
    re.DOTALL,
)


def _quote_is_valid(quote, manager_lines):
    q = _norm(quote)
    return bool(q) and any(q in _norm(line) for line in manager_lines)


def _best_matching_line(quote, manager_lines):
    q_words = set(_norm(quote).split())
    best, best_score = manager_lines[0], -1
    for line in manager_lines:
        score = len(q_words & set(_norm(line).split()))
        if score > best_score:
            best, best_score = line, score
    return best


def find_invalid_quotes(text, manager_lines):
    return [
        m.group("quote")
        for m in QUOTE_PATTERN.finditer(text)
        if not _quote_is_valid(m.group("quote"), manager_lines)
    ]


def repair_invalid_quotes(text, manager_lines):
    """Last resort: swap a fabricated quote for the closest REAL manager line."""

    def fix(match):
        quote = match.group("quote")
        if _quote_is_valid(quote, manager_lines):
            return match.group(0)
        return f'{match.group("head")}"{_best_matching_line(quote, manager_lines)}"'

    return QUOTE_PATTERN.sub(fix, text)


# =========================================================
# GENERATE DEBRIEF
# =========================================================

def generate_debrief(conversation):
    if not conversation:
        raise ValueError("Cannot generate a debrief without a rehearsal conversation.")

    manager_lines = get_manager_lines(conversation)

    if not manager_lines:
        raise ValueError("Cannot generate a debrief without manager speech.")

    print("\n[DEBRIEF] transcript used:")
    print(build_transcript_text(conversation))

    base_prompt = build_debrief_prompt(conversation)
    prompt = base_prompt
    result = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = generate_response(prompt, temperature=0.2)

        invalid = find_invalid_quotes(result, manager_lines)
        if not invalid:
            return result

        print(f"[DEBRIEF] attempt {attempt}: invalid quotes {invalid}")

        prompt = (
            base_prompt
            + "\n\nCORRECTION: your previous answer quoted text the manager never said: "
            + "; ".join(f'"{q}"' for q in invalid)
            + "\nQuote ONLY exact words from the allowed manager lines listed above. Try again."
        )

    return repair_invalid_quotes(result, manager_lines)