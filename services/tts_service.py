import os
import re
import wave
from io import BytesIO

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

MODEL_NAME = "canopylabs/orpheus-v1-english"
VOICE = "daniel"  # male voice for Rohit (alternatives: "austin", "troy")


def split_into_chunks(text: str, limit: int = 200) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, current = [], ""

    for sentence in sentences:
        if len(sentence) > limit:  # very long sentence: fall back to word split
            if current:
                chunks.append(current)
                current = ""
            while len(sentence) > limit:
                cut = sentence.rfind(" ", 0, limit)
                cut = cut if cut > 0 else limit
                chunks.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            current = sentence
        elif len(current) + len(sentence) + 1 <= limit:
            current = f"{current} {sentence}".strip()
        else:
            chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)

    return chunks


def generate_speech(text: str) -> bytes:
    if client is None:
        raise RuntimeError("GROQ_API_KEY is missing from .env")

    text = " ".join(text.split())

    if not text:
        raise ValueError("No text provided for speech generation.")

    chunks = split_into_chunks(text)
    audio_parts = []

    for chunk in chunks:
        try:
            response = client.audio.speech.create(
                model=MODEL_NAME,
                voice=VOICE,
                input=chunk,
                response_format="wav",
            )
        except Exception as error:
            print("[TTS ERROR]", error)
            raise

        audio_parts.append(response.read())

    if len(audio_parts) == 1:
        return audio_parts[0]

    # WAV files cannot be concatenated as raw bytes; combine with the wave module.
    output = BytesIO()

    with wave.open(output, "wb") as combined:
        for index, part in enumerate(audio_parts):
            with wave.open(BytesIO(part), "rb") as segment:
                params = segment.getparams()
                frames = segment.readframes(segment.getnframes())

                if index == 0:
                    combined.setparams(params)
                elif (
                    params.nchannels != combined.getnchannels()
                    or params.sampwidth != combined.getsampwidth()
                    or params.framerate != combined.getframerate()
                ):
                    raise RuntimeError("Orpheus returned incompatible WAV audio.")

                combined.writeframes(frames)

    return output.getvalue()