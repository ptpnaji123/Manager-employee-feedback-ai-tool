from flask import Flask, render_template, request, jsonify

from services.prepare_service import prepare_feedback
from services.conversation_service import get_rohit_response
from services.debrief_service import generate_debrief


app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/prepare", methods=["POST"])
def prepare():

    data = request.get_json(
        silent=True
    ) or {}

    manager_input = str(
        data.get("message", "")
    ).strip()

    if not manager_input:
        return jsonify({
            "error": "Manager request cannot be empty."
        }), 400

    try:

        response = prepare_feedback(
            manager_input
        )

        return jsonify({
            "response": response
        })

    except Exception as error:

        print("\nPrepare error:")
        print(error)

        return jsonify({
            "error": str(error)
        }), 500


@app.route("/api/rehearse", methods=["POST"])
def rehearse():

    data = request.get_json(
        silent=True
    ) or {}

    manager_message = str(
        data.get("message", "")
    ).strip()

    conversation = data.get(
        "conversation",
        []
    )

    if not manager_message:
        return jsonify({
            "error": "Manager message cannot be empty."
        }), 400

    if not isinstance(conversation, list):
        return jsonify({
            "error": "Conversation must be a list."
        }), 400

    try:

        response = get_rohit_response(
            manager_message,
            conversation
        )

        return jsonify({
            "speaker": "rohit",
            "response": response
        })

    except Exception as error:

        print("\nRehearse error:")
        print(error)

        return jsonify({
            "error": str(error)
        }), 500


@app.route("/api/debrief", methods=["POST"])
def debrief():

    data = request.get_json(
        silent=True
    ) or {}

    conversation = data.get(
        "conversation",
        []
    )

    if not conversation:
        return jsonify({
            "error": "No rehearsal conversation was provided."
        }), 400

    try:

        response = generate_debrief(
            conversation
        )

        return jsonify({
            "response": response
        })

    except Exception as error:

        print("\nDebrief error:")
        print(error)

        return jsonify({
            "error": str(error)
        }), 500


if __name__ == "__main__":

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )