import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral:latest"


def generate_response(prompt: str, temperature: float = 0.7, max_tokens: int | None = None) -> str:
    """
    Call Ollama.

    temperature : low (0.1-0.3) for the debrief (factual), higher (0.7-0.8) for Rohit (natural).
    max_tokens  : caps the reply length. A short cap = faster first sound for Rohit.
    """

    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty.")

    options = {"temperature": temperature}
    if max_tokens:
        options["num_predict"] = max_tokens

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": options,
        # keep the model loaded in memory -> avoids a multi-second reload between turns
        "keep_alive": "30m",
    }

    print(f"\n[OLLAMA] model={MODEL_NAME} temperature={temperature} max_tokens={max_tokens}")

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