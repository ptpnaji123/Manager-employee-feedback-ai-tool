import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral:latest"


def generate_response(prompt: str) -> str:

    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty.")

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }

    print("\n" + "=" * 60)
    print("OLLAMA REQUEST")
    print("=" * 60)
    print(f"Model: {MODEL_NAME}")
    print(f"URL: {OLLAMA_URL}")

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=120,
        )

    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Could not connect to Ollama. "
            "Make sure Ollama is running."
        )

    except requests.exceptions.Timeout:
        raise RuntimeError(
            "Ollama took too long to respond."
        )

    except requests.exceptions.RequestException as error:
        raise RuntimeError(
            f"Ollama request failed: {error}"
        )

    print(f"Ollama HTTP status: {response.status_code}")

    if response.status_code != 200:
        print("\nOllama returned an error:")
        print(response.text)

        raise RuntimeError(
            f"Ollama returned HTTP {response.status_code}: "
            f"{response.text}"
        )

    try:
        data = response.json()

    except ValueError:
        raise RuntimeError(
            "Ollama returned invalid JSON."
        )

    if "response" not in data:
        raise RuntimeError(
            "Ollama response does not contain a 'response' field."
        )

    result = data["response"].strip()

    if not result:
        raise RuntimeError(
            "Ollama returned an empty response."
        )

    print("\nMistral response received.")
    print("=" * 60 + "\n")

    return result