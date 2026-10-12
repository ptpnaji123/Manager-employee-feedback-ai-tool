import os
from io import BytesIO

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

MODEL_NAME = "whisper-large-v3-turbo"


def transcribe_audio(audio_bytes: bytes, filename: str = "recording.webm") -> str:
    if client is None:
        raise RuntimeError("GROQ_API_KEY is missing. Check your .env file.")

    if not audio_bytes:
        raise ValueError("No audio was received.")

    try:
        result = client.audio.transcriptions.create(
            file=(filename, BytesIO(audio_bytes)),
            model=MODEL_NAME,
            language="en",
            response_format="json",
            temperature=0.0,
        )
    except Exception as error:
        raise RuntimeError(f"Whisper transcription failed: {error}") from error

    return result.text.strip()
