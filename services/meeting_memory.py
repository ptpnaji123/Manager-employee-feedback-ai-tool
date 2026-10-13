import json
import re
import threading
import time

from services.llm_service import generate_response

MEMORY_PROVIDER = "groq"
MEMORY_MODEL = "llama-3.1-8b-instant"
SESSION_TTL_SECONDS = 2 * 60 * 60   # safety net if the meeting is never ended explicitly
MAX_FACTS = 12

DEFAULT_FEELING = "Calm. Does not yet know why the meeting was called."

_lock = threading.Lock()
_sessions = {}


def _blank():
    return {
        "facts": [],
        "feeling": DEFAULT_FEELING,
        "turns": 0,
        "updated": time.time(),
        "thread": None,
    }


def _purge_expired():
    now = time.time()
    for sid in [s for s, m in _sessions.items() if now - m["updated"] > SESSION_TTL_SECONDS]:
        del _sessions[sid]


# ---------- lifecycle ----------

def end_session(session_id):
    """Delete everything remembered about this meeting."""
    with _lock:
        return _sessions.pop(session_id, None) is not None


def get_snapshot(session_id, create=True):
    with _lock:
        _purge_expired()
        mem = _sessions.get(session_id)

        if mem is None:
            if not create:
                return None
            mem = _sessions[session_id] = _blank()

        return {"facts": list(mem["facts"]), "feeling": mem["feeling"], "turns": mem["turns"]}


def wait_for_update(session_id, timeout=6.0):
    """The background update from the previous turn is normally finished already."""
    with _lock:
        mem = _sessions.get(session_id)
        thread = mem["thread"] if mem else None

    if thread is not None and thread.is_alive():
        thread.join(timeout)


# ---------- extraction ----------

def _extract(facts, feeling, new_text):
    facts_text = "\n".join(f"- {f}" for f in facts) or "- (nothing yet)"

    prompt = (
        "You keep the shared memory of a live workplace conversation between a manager (Aditi) "
        "and an employee (Rohit).\n\n"
        f"Known facts so far:\n{facts_text}\n"
        f"Rohit's current feeling: {feeling}\n\n"
        f"New part of the conversation:\n{new_text}\n\n"
        "Update the memory.\n"
        "- facts: short, plain sentences about what has actually happened: what Aditi announced, "
        "decided, claimed, asked or proposed; the REASON she gave for any serious decision; and what "
        "Rohit said, admitted, disputed or agreed to. If something new changes, corrects or cancels an "
        "earlier fact, UPDATE that fact so the list shows the current truth and the history "
        '(for example "Aditi first said X, then said it was not true").\n'
        "- Speech recognition makes mistakes. Ignore garbled, meaningless or clearly misheard "
        "fragments. Never record them as facts.\n"
        "- Do not invent anything. Use only what was said.\n"
        f"- Merge duplicates. At most {MAX_FACTS} facts.\n"
        "- feeling: ONE short sentence on how Rohit would realistically feel right now, given "
        "everything that has happened.\n"
        'Return ONLY JSON: {"facts": ["..."], "feeling": "..."}'
    )

    raw = generate_response(
        prompt,
        temperature=0.0,
        max_tokens=500,
        provider=MEMORY_PROVIDER,
        model=MEMORY_MODEL,
    )

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    data = json.loads(match.group(0))

    new_facts = [str(f).strip() for f in data.get("facts", []) if str(f).strip()]
    new_feeling = str(data.get("feeling", "")).strip() or feeling

    return new_facts[:MAX_FACTS], new_feeling


def _apply_update(session_id, new_text, fallback_fact, turns_added=1):
    with _lock:
        mem = _sessions.get(session_id)
        if mem is None:           # meeting ended while we were working
            return
        facts, feeling = list(mem["facts"]), mem["feeling"]

    try:
        facts, feeling = _extract(facts, feeling, new_text)
    except Exception as error:
        print("[MEMORY] extraction failed, keeping a raw note instead:", error)
        facts = (facts + [fallback_fact])[-MAX_FACTS:]

    with _lock:
        mem = _sessions.get(session_id)
        if mem is None:
            return
        mem["facts"], mem["feeling"] = facts, feeling
        mem["turns"] += turns_added
        mem["updated"] = time.time()


def update_async(session_id, manager_line, rohit_line):
    """Runs in the background so Rohit's reply is not delayed."""
    new_text = f"ADITI: {manager_line}\nROHIT: {rohit_line}"
    fallback = f"Aditi said: {manager_line[:160]}"

    thread = threading.Thread(
        target=_apply_update, args=(session_id, new_text, fallback), daemon=True
    )

    with _lock:
        mem = _sessions.get(session_id)
        if mem is None:
            return
        mem["thread"] = thread
        thread.start()            # started under the lock, so wait_for_update always sees it running


def rebuild_from_conversation(session_id, conversation):
    """Used when the server has no memory yet (restart, second worker) but the browser has a transcript."""
    lines, rohit_turns = [], 0

    for turn in conversation:
        text = str(turn.get("text", "")).strip()
        speaker = str(turn.get("speaker", "")).strip().lower()
        if not text:
            continue
        if speaker == "manager":
            lines.append(f"ADITI: {text}")
        elif speaker == "rohit":
            lines.append(f"ROHIT: {text}")
            rohit_turns += 1

    if not lines:
        return

    _apply_update(
        session_id,
        "\n".join(lines),
        "Earlier parts of the conversation could not be summarised.",
        turns_added=max(rohit_turns, 1),
    )


# ---------- for the prompt ----------

def format_for_prompt(snapshot):
    facts = "\n".join(f"- {f}" for f in snapshot["facts"]) or "- Nothing has been established yet."
    return (
        f"Facts established in this meeting so far:\n{facts}\n"
        f"How Rohit feels right now: {snapshot['feeling']}"
    )