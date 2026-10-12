from flask import Flask, render_template, request, jsonify

from services.prepare_service import prepare_feedback
from services.conversation_service import get_rohit_response
from services.debrief_service import generate_debrief

from flask import request, jsonify
from services.transcription_service import transcribe_audio
from services.tts_service import generate_speech
app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/prepare", methods=["POST"])
def prepare():
    data = request.get_json(silent=True) or {}

    manager_input = str(data.get("message", "")).strip()
    history = data.get("history", [])

    if not manager_input:
        return jsonify({"error": "Manager request cannot be empty."}), 400

    if not isinstance(history, list):
        history = []

    try:
        response = prepare_feedback(manager_input, history)
        return jsonify({"response": response})

    except Exception as error:
        print("\nPrepare error:")
        print(error)
        return jsonify({"error": str(error)}), 500


@app.route("/api/rehearse", methods=["POST"])
def rehearse():
    data = request.get_json(silent=True) or {}

    manager_message = str(data.get("message", "")).strip()
    conversation = data.get("conversation", [])

    if not manager_message:
        return jsonify({"error": "Manager message cannot be empty."}), 400

    if not isinstance(conversation, list):
        return jsonify({"error": "Conversation must be a list."}), 400

    try:
        response = get_rohit_response(manager_message, conversation)
        return jsonify({"speaker": "rohit", "response": response})

    except Exception as error:
        print("\nRehearse error:")
        print(error)
        return jsonify({"error": str(error)}), 500


@app.route("/api/debrief", methods=["POST"])
def debrief():
    data = request.get_json(silent=True) or {}

    conversation = data.get("conversation", [])

    if not conversation:
        return jsonify({"error": "No rehearsal conversation was provided."}), 400

    try:
        response = generate_debrief(conversation)
        return jsonify({"response": response})

    except Exception as error:
        print("\nDebrief error:")
        print(error)
        return jsonify({"error": str(error)}), 500

@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file received."}), 400

    audio = request.files["audio"]

    try:
        text = transcribe_audio(
            audio.read(),
            audio.filename or "recording.webm",
        )
        return jsonify({"text": text})
    except Exception as error:
        print("Transcription error:", error)
        return jsonify({"error": str(error)}), 500

@app.route("/api/tts", methods=["POST"])
def text_to_speech():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"error": "Text is required."}), 400

    try:
        audio = generate_speech(text)

        return (
            audio,
            200,
            {"Content-Type": "audio/wav"}
        )

    except Exception as error:
        app.logger.exception("Orpheus TTS failed")
        return jsonify({"error": str(error)}), 500
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)