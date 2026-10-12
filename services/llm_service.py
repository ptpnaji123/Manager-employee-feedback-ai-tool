import os

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------- Ollama ----------
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral:latest"

# ---------- Groq ----------
GROQ_MODEL = os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile")
GROQ_TIMEOUT = 60

# Default provider for callers that don't choose one (debrief, prepare).
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

_groq_key = os.getenv("GROQ_API_KEY")
_groq_client = None

if _groq_key:
    try:
        from groq import Groq

        _groq_client = Groq(api_key=_groq_key, timeout=GROQ_TIMEOUT)
    except Exception as error:  # library missing or bad setup
        print("[LLM] Groq client could not be created:", error)


def _call_ollama(prompt, temperature, max_tokens):
    options = {"temperature": temperature}
    if max_tokens:
        options["num_predict"] = max_tokens

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": options,
        "keep_alive": "30m",
    }

    print(f"\n[OLLAMA] model={OLLAMA_MODEL} temperature={temperature} max_tokens={max_tokens}")

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=180)
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not connect to Ollama. Make sure Ollama is running.")
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama took too long to respond.")
    except requests.exceptions.RequestException as error:
        raise RuntimeError(f"Ollama request failed: {error}")

    if response.status_code != 200:
        print(response.text)
        raise RuntimeError(f"Ollama returned HTTP {response.status_code}: {response.text}")

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError("Ollama returned invalid JSON.")

    if "response" not in data:
        raise RuntimeError("Ollama response does not contain a 'response' field.")

    result = data["response"].strip()

    if not result:
        raise RuntimeError("Ollama returned an empty response.")

    return result


def _call_groq(prompt, temperature, max_tokens, model=None):
    if _groq_client is None:
        raise RuntimeError("Groq is not available. Check GROQ_API_KEY in .env.")

    model = model or GROQ_MODEL

    print(f"\n[GROQ] model={model} temperature={temperature} max_tokens={max_tokens}")

    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    try:
        completion = _groq_client.chat.completions.create(**kwargs)
    except Exception as error:
        raise RuntimeError(f"Groq request failed: {error}") from error

    result = (completion.choices[0].message.content or "").strip()

    if not result:
        raise RuntimeError("Groq returned an empty response.")

    return result


def generate_response(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    fallback: bool = True,
) -> str:
    """
    provider : "groq" or "ollama". Defaults to LLM_PROVIDER from .env (ollama if unset).
    model    : optional model override for Groq (ignored by Ollama).
    fallback : if Groq fails (rate limit, network), retry once with Ollama.
    """

    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty.")

    provider = (provider or DEFAULT_PROVIDER).lower()

    if provider == "groq":
        try:
            return _call_groq(prompt, temperature, max_tokens, model)
        except Exception as error:
            print("[LLM] Groq failed:", error)
            if not fallback:
                raise
            print("[LLM] Falling back to Ollama...")
            return _call_ollama(prompt, temperature, max_tokens)

    return _call_ollama(prompt, temperature, max_tokens)