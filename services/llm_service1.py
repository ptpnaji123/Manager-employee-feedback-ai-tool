import os
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

PRIMARY_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)

FALLBACK_MODEL = os.getenv(
    "GEMINI_FALLBACK_MODEL",
    "gemini-3.5-flash"
)

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is missing. "
        "Create a .env file in the project root."
    )

client = genai.Client(api_key=GEMINI_API_KEY)


def is_retryable_error(error):
    """
    Gemini 503/5xx and temporary availability errors
    should be retried.
    """

    error_text = str(error).upper()

    retryable_codes = [
        "503",
        "UNAVAILABLE",
        "INTERNAL",
        "500",
        "504",
        "DEADLINE_EXCEEDED"
    ]

    return any(code in error_text for code in retryable_codes)


def call_gemini(model, prompt, max_retries=3):
    """
    Call Gemini with exponential backoff.
    """

    for attempt in range(max_retries + 1):

        try:
            print("\n" + "=" * 60)
            print("GEMINI REQUEST")
            print("=" * 60)
            print(f"Model: {model}")
            print(f"Attempt: {attempt + 1}/{max_retries + 1}")

            response = client.models.generate_content(
                model=model,
                contents=prompt
            )

            if not response:
                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            text = getattr(response, "text", None)

            if not text:
                raise RuntimeError(
                    "Gemini response did not contain text."
                )

            text = text.strip()

            if not text:
                raise RuntimeError(
                    "Gemini returned empty text."
                )

            print("\nGemini response received.")
            print("=" * 60 + "\n")

            return text

        except Exception as error:

            print("\nGemini error:")
            print(error)

            if not is_retryable_error(error):
                raise RuntimeError(
                    f"Gemini API request failed: {error}"
                )

            if attempt >= max_retries:
                raise

            # 2, 4, 8 seconds
            delay = 2 ** (attempt + 1)

            print(
                f"\nTemporary Gemini availability problem."
                f"\nRetrying in {delay} seconds..."
            )

            time.sleep(delay)


def generate_response(prompt: str) -> str:

    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty.")

    # First try the primary model
    try:

        return call_gemini(
            PRIMARY_MODEL,
            prompt,
            max_retries=2
        )

    except Exception as primary_error:

        print("\n" + "=" * 60)
        print("PRIMARY GEMINI MODEL FAILED")
        print("=" * 60)
        print(primary_error)

        # Don't use fallback if primary failed because of
        # authentication / invalid request / permissions.
        if not is_retryable_error(primary_error):
            raise RuntimeError(
                f"Gemini API request failed: {primary_error}"
            )

        print("\nTrying fallback model...")
        print(f"Fallback model: {FALLBACK_MODEL}")

        try:

            return call_gemini(
                FALLBACK_MODEL,
                prompt,
                max_retries=1
            )

        except Exception as fallback_error:

            raise RuntimeError(
                "Gemini is temporarily unavailable. "
                f"Primary model: {PRIMARY_MODEL}. "
                f"Fallback model: {FALLBACK_MODEL}. "
                f"Last error: {fallback_error}"
            )