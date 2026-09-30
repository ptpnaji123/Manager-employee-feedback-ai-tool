# =========================================================
# CONVERSATION SIGNALS (tell the model where we are)
# =========================================================
import re 
CLOSING_PATTERNS = [
    r"\bfrom tomorrow\b", r"\bfrom (now|today|monday|next week)\b",
    r"\bonwards?\b", r"\b(going|moving) forward\b", r"\bmove on\b",
    r"\blet'?s (wrap|finish|end|leave it)\b", r"\bthat'?s (all|it)\b",
    r"\bsounds good\b", r"\bwe'?re (good|done)\b",
    r"\bthank(s| you)\b.*\b(time|talking|listening|meeting|understanding)\b",
]
PROPOSAL_PATTERNS = [
    r"\bfrom tomorrow\b", r"\b(going|moving) forward\b", r"\bon time\b",
    r"\b(9[:.]?30|nine thirty)\b", r"\bi need you to\b", r"\bi'?d like you to\b",
    r"\b(can|could) you (please )?(make sure|be|start|come|arrive)\b",
    r"\blet'?s agree\b", r"\bplease (be|start|come|arrive)\b",
]
FOLLOWUP_PATTERNS = [
    r"\bcheck[- ]?in\b", r"\bfollow[- ]?up\b", r"\bnext (week|month)\b",
    r"\bin (a|one|two|2|1) weeks?\b", r"\bcatch up\b", r"\breview\b",
]
AGREEMENT_PATTERNS = [
    r"\bunderstood\b", r"\bagreed?\b", r"\bfair enough\b", r"\bsounds fair\b",
    r"\bi'?ll (be|start|make sure|try|do)\b", r"\bi will (be|start|make sure|try|do)\b",
]
EXPLANATION_WORDS = ("because", "difficult", "struggl", "personal", "hard for me")


def _matches(patterns, text):
    return any(re.search(p, text) for p in patterns)


def detect_signals(manager_message, conversation):
    msg = manager_message.lower().strip()
    rohit_lines = [
        str(t.get("text", "")).lower()
        for t in conversation
        if str(t.get("speaker", "")).lower() == "rohit"
    ]
    rohit_text = " ".join(rohit_lines)

    return {
        "first_turn": len(rohit_lines) == 0,
        # closing only makes sense after some discussion, and not for a question
        "closing": len(rohit_lines) >= 2 and not msg.endswith("?") and _matches(CLOSING_PATTERNS, msg),
        "proposal": _matches(PROPOSAL_PATTERNS, msg),
        "followup": _matches(FOLLOWUP_PATTERNS, msg),
        "already_agreed": _matches(AGREEMENT_PATTERNS, rohit_text),
        "already_apologised": "sorry" in rohit_text or "apologi" in rohit_text,
        "already_explained": any(w in rohit_text for w in EXPLANATION_WORDS),
    }


def build_state_notes(s):
    notes = []

    if s["first_turn"]:
        notes.append("This is the start of the meeting. Reply naturally to what Aditi said. Do NOT bring up lateness yourself.")

    if s["closing"]:
        notes.append(
            "Aditi is closing the topic or stating the final way forward. The issue is now SETTLED. "
            "Reply with ONE short sentence confirming what she proposed (or a brief thanks). "
            "Do NOT apologise again, do NOT explain, do NOT bring up lateness or any earlier topic."
        )
    elif s["proposal"]:
        if s["already_agreed"]:
            notes.append("A change has already been agreed. Confirm briefly and do not reopen it.")
        else:
            notes.append(
                "Aditi is proposing a specific change. Respond to that exact proposal. "
                "You may raise ONE practical concern or ask for one small adjustment. "
                "If she has already answered a concern from you, accept clearly now."
            )

    if s["followup"] and not s["closing"]:
        notes.append("Aditi mentioned a follow-up. Respond briefly and agree if it seems fair.")
    if s["already_apologised"]:
        notes.append("You have ALREADY apologised. Do not apologise again.")
    if s["already_explained"]:
        notes.append("You have ALREADY given a reason. Do not repeat it.")

    if not notes:
        notes.append("Respond only to the latest thing Aditi said, in character.")

    return "\n".join(f"- {n}" for n in notes)


# =========================================================
# BUILD REHEARSAL PROMPT
# =========================================================

def build_rehearsal_prompt(manager_message, conversation):
    employee = load_employee_record()
    template = load_prompt()

    context = json.dumps(build_safe_employee_context(employee), indent=2, ensure_ascii=False)
    notes = build_state_notes(detect_signals(manager_message, conversation))

    prompt = template.replace("{{EMPLOYEE_CONTEXT}}", context)
    prompt = prompt.replace("{{CONVERSATION}}", build_conversation_history(conversation))
    prompt = prompt.replace("{{STATE_NOTES}}", notes)
    prompt = prompt.replace("{{MANAGER_MESSAGE}}", manager_message)
    return prompt


# =========================================================
# CLEAN MODEL RESPONSE
# =========================================================

def first_sentence(text):
    return re.split(r"(?<=[.?!])\s+", text.strip())[0]


def clean_rohit_response(response):
    if not response:
        return ""

    response = response.replace("```text", "").replace("```", "")
    # remove stage directions: (sighs) [nervous] *pauses*
    response = re.sub(r"\([^)]*\)|\[[^\]]*\]|\*[^*]*\*", "", response)
    # cut off if the model started writing the next speaker's line
    response = re.split(r"\n\s*(?:MANAGER|ADITI|ROHIT)[^\n:]*:", response, flags=re.I)[0]
    # strip a leading speaker label
    response = re.sub(
        r"^\s*(?:rohit(?:\s*[—-]\s*simulated employee)?|simulated employee|employee)\s*:\s*",
        "", response.strip(), flags=re.I)

    response = re.sub(r"\s+", " ", response).strip()
    if len(response) >= 2 and response[0] == response[-1] and response[0] in "\"'":
        response = response[1:-1].strip()

    # if the token cap cut a sentence in half, keep the last complete sentence
    if response and response[-1] not in ".?!":
        cut = max(response.rfind("."), response.rfind("?"), response.rfind("!"))
        if cut > 20:
            response = response[: cut + 1]

    return response


# =========================================================
# GET ROHIT RESPONSE
# =========================================================

def get_rohit_response(manager_message, conversation):
    manager_message = str(manager_message or "").strip()
    if not manager_message:
        raise ValueError("Manager message cannot be empty.")
    if not isinstance(conversation, list):
        raise ValueError("Conversation must be a list.")

    prompt = build_rehearsal_prompt(manager_message, conversation)

    response = generate_response(
        prompt,
        temperature=0.75,
        max_tokens=140,
        stop=["\nMANAGER:", "\nROHIT:", "\nADITI:"],
    )
    response = clean_rohit_response(response)

    # Hard guarantee: a closing turn gets a one-sentence reply
    if detect_signals(manager_message, conversation)["closing"]:
        response = first_sentence(response)

    if not response:
        raise RuntimeError("Ollama returned an empty employee response.")

    print(f"\nMANAGER: {manager_message}\nROHIT:   {response}\n")
    return response