import json
from pathlib import Path

from services.llm_service import generate_response


BASE_DIR = Path(__file__).resolve().parent.parent

EMPLOYEE_FILE = BASE_DIR / "employee_record.json"
PROMPT_FILE = BASE_DIR / "prompts" / "prepare_prompt.txt"


def load_employee_record():
    with open(EMPLOYEE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def load_prompt():
    with open(PROMPT_FILE, "r", encoding="utf-8") as file:
        return file.read()


def build_manager_context(employee):
    """
    Return only information appropriate for the manager
    to use when preparing the feedback conversation.
    """

    return {
        "employee": {
            "name": employee["name"],
            "role": employee["role"],
            "tenure_months": employee["tenure_months"]
        },

        "performance": {
            "current_cycle_rating": employee["performance"]["current_cycle_rating"],
            "previous_cycle_rating": employee["performance"]["previous_cycle_rating"],
            "trend": employee["performance"]["trend"],
            "last_reviewed": employee["performance"]["last_reviewed"]
        },

        "goals": employee["goals"],

        "attendance": {
            "scheduled_start": employee["attendance"]["scheduled_start"],
            "late_arrivals_last_90_days": employee["attendance"]["late_arrivals_last_90_days"],
            "average_lateness_minutes": employee["attendance"]["average_lateness_minutes"],
            "pattern_note": employee["attendance"]["pattern_note"],
            "prior_conversation_logged": employee["attendance"]["prior_conversation_logged"]
        }
    }


def build_prepare_prompt(manager_input):
    employee = load_employee_record()
    template = load_prompt()

    manager_context = build_manager_context(employee)

    manager_context_text = json.dumps(
        manager_context,
        indent=2,
        ensure_ascii=False
    )

    prompt = template.replace(
        "{{MANAGER_CONTEXT}}",
        manager_context_text
    )

    prompt = prompt.replace(
        "{{MANAGER_INPUT}}",
        manager_input
    )

    return prompt


def prepare_feedback(manager_input):
    prompt = build_prepare_prompt(manager_input)

    return generate_response(prompt)
