import difflib
import json
import re
from pathlib import Path

from services.llm_service import generate_response

BASE_DIR = Path(__file__).resolve().parent.parent
EMPLOYEE_FILE = BASE_DIR / "employee_record.json"
PROMPT_FILE = BASE_DIR / "prompts" / "debrief_prompt.txt"

READINESS_LABELS = {
    "READY": "You are ready for this conversation.",
    "REHEARSE_AGAIN": "Rehearse once more before the real conversation.",
    "TALK_TO_HR": "Do not have this conversation yet. Speak to your HR partner first.",
}

MIN_MANAGER_TURNS_FOR_READY = 4


# ---------- data ----------

def load_employee_record():
    with open(EMPLOYEE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt():
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def build_debrief_employee_context(employee):
    perf, att = employee["performance"], employee["attendance"]
    return {
        "employee": {
            "name": employee["name"],
            "role": employee["role"],
            "tenure_months": employee["tenure_months"],
        },
        "performance": {k: perf[k] for k in (
            "current_cycle_rating", "previous_cycle_rating", "trend", "last_reviewed")},
        "goals": employee["goals"],
        "attendance": {k: att[k] for k in (
            "scheduled_start", "late_arrivals_last_90_days", "average_lateness_minutes",
            "pattern_note", "prior_conversation_logged")},
    }


def build_transcript_text(conversation):
    lines = []
    for turn in conversation:
        text = str(turn.get("text", "")).strip()
        if not text:
            continue
        speaker = turn.get("speaker")
        label = "MANAGER" if speaker == "manager" else "ROHIT (simulated)" if speaker == "rohit" else None
        if label:
            lines.append(f"{label}: {text}")
    return "\n".join(lines)


def build_debrief_prompt(conversation):
    context = json.dumps(
        build_debrief_employee_context(load_employee_record()), indent=2, ensure_ascii=False)
    prompt = load_prompt()
    prompt = prompt.replace("{{EMPLOYEE_CONTEXT}}", context)
    prompt = prompt.replace("{{TRANSCRIPT}}", build_transcript_text(conversation))
    return prompt


# ---------- validation ----------

def _norm(text):
    text = re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def manager_turns(conversation):
    return [
        str(t.get("text", "")).strip()
        for t in conversation
        if t.get("speaker") == "manager" and str(t.get("text", "")).strip()
    ]


def quote_is_valid(quote, turns):
    q = _norm(quote)
    return len(q) >= 3 and any(q in _norm(t) for t in turns)


def closest_turn(quote, turns):
    normed = [_norm(t) for t in turns]
    match = difflib.get_close_matches(_norm(quote), normed, n=1, cutoff=0.4)
    return turns[normed.index(match[0])] if match else None


def parse_json(raw):
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except ValueError:
            pass
    return {}


def find_problems(data, turns):
    if not isinstance(data, dict) or not data:
        return ["The answer was not valid JSON with the required keys."]

    problems, quotes = [], []
    for key in ("worked", "did_not_work"):
        block = data.get(key) if isinstance(data.get(key), dict) else {}
        quote = block.get("quote", "")
        quotes.append(_norm(quote))
        if not quote_is_valid(quote, turns):
            problems.append(f'"{key}.quote" is not copied word for word from a MANAGER line: {quote!r}')

    if len(turns) > 1 and quotes[0] == quotes[1]:
        problems.append("worked and did_not_work must quote two different manager lines.")
    if not str(data.get("opening_line", "")).strip():
        problems.append('"opening_line" is missing.')
    return problems


# ---------- result ----------

def finalize_debrief(data, turns, warnings):
    if not isinstance(data, dict) or not data:
        raise RuntimeError("The model did not return a usable debrief. Please try again.")

    def moment(key):
        block = data.get(key) if isinstance(data.get(key), dict) else {}
        quote = str(block.get("quote", "")).strip()
        if not quote_is_valid(quote, turns):
            repaired = closest_turn(quote, turns)
            if repaired:
                warnings.append("A quote was replaced with the closest line the manager actually said.")
            quote = repaired or ""
        return {"quote": quote, "why": str(block.get("why", "")).strip()}

    objections = []
    for item in (data.get("objections") or [])[:2]:
        if isinstance(item, dict) and str(item.get("objection", "")).strip():
            objections.append({
                "objection": str(item["objection"]).strip(),
                "response": str(item.get("response", "")).strip(),
            })
    while len(objections) < 2:
        objections.append({
            "objection": "No clear objection was raised in this rehearsal.",
            "response": "Ask an open question, then listen before you respond.",
        })

    readiness = re.sub(r"[^A-Z]+", "_", str(data.get("readiness", "")).upper()).strip("_")
    if readiness not in READINESS_LABELS:
        readiness = "REHEARSE_AGAIN"

    reason = str(data.get("readiness_reason", "")).strip()

    # Small models are generous: a very short rehearsal cannot be "READY".
    if readiness == "READY" and len(turns) < MIN_MANAGER_TURNS_FOR_READY:
        readiness = "REHEARSE_AGAIN"
        reason = "This rehearsal was too short to show the full conversation (opening, listening, agreement, follow-up)."

    return {
        "readiness": readiness,
        "readiness_label": READINESS_LABELS[readiness],
        "readiness_reason": reason,
        "worked": moment("worked"),
        "did_not_work": moment("did_not_work"),
        "opening_line": str(data.get("opening_line", "")).strip(),
        "objections": objections,
        "summary": str(data.get("summary", "")).strip(),
        "warnings": sorted(set(warnings)),
    }


def generate_debrief(conversation):
    turns = manager_turns(conversation)
    if not turns:
        raise ValueError("Cannot generate a debrief without manager speech.")

    prompt = build_debrief_prompt(conversation)
    problems, data = [], {}

    for _ in range(2):  # one retry with corrections
        extra = ""
        if problems:
            extra = (
                "\n\nYOUR PREVIOUS ANSWER HAD PROBLEMS:\n- " + "\n- ".join(problems) +
                "\nFix them. Quotes must be copied word for word from one of these MANAGER lines:\n" +
                "\n".join(f"- {t}" for t in turns)
            )
        raw = generate_response(prompt + extra, json_mode=True, temperature=0.2, max_tokens=900)
        data = parse_json(raw)
        problems = find_problems(data, turns)
        if not problems:
            break

    return finalize_debrief(data, turns, [])