# Manager Feedback Coach

A local AI-powered coaching tool that helps managers prepare for and rehearse difficult employee feedback conversations.

The prototype focuses on one scenario: repeated lateness.

## Features

### 1. Prepare

Helps the manager structure the conversation using the Situation–Behaviour–Impact (SBI) framework.

It provides:

* Specific situation
* Observable behaviour
* Work impact
* Suggested opening line
* Questions to ask
* Agreed change
* Follow-up plan
* Coaching guidance

Sensitive employee information is handled through restricted context and is not unnecessarily exposed to the simulated employee.

### 2. Rehearse

A voice-based role-play between the manager and a simulated employee.

* Manager speaks through the microphone
* Browser Speech Recognition converts speech to text
* The conversation is sent to a local Mistral model through Ollama
* Mistral generates the employee's response
* Browser Speech Synthesis speaks the response
* Previous conversation turns are passed as context
* Supports interruption/barge-in while the employee is speaking
* Displays the conversation transcript

### 3. Debrief

Analyzes the actual rehearsal conversation and provides:

* Readiness call
* A specific good moment
* A specific moment to improve
* A usable opening line
* Two likely employee objections
* Practical coaching summary

The transcript is treated as the source of truth for conversation-specific feedback.

## Architecture

```text
Manager
   │
   ▼
Browser Speech Recognition
   │
   ▼
JavaScript / Transcript
   │
   ▼
Flask Backend
   │
   ├── Prepare Service
   ├── Rehearsal Service
   └── Debrief Service
            │
            ▼
      Ollama + Mistral
            │
            ▼
      Generated Response
            │
            ▼
Browser Speech Synthesis
```

## Technology Stack

* Python
* Flask
* JavaScript
* HTML / CSS
* Web Speech API

  * SpeechRecognition
  * SpeechSynthesis
* Ollama
* Mistral
* Requests
* JSON

## Project Structure

```text
manager-feedback-coach/
│
├── app.py
├── employee_record.json
├── requirements.txt
│
├── config/
│   └── feedback_framework.json
│
├── prompts/
│   ├── prepare_prompt.txt
│   ├── rehearsal_prompt.txt
│   └── debrief_prompt.txt
│
├── services/
│   ├── llm_service.py
│   ├── conversation_service.py
│   ├── prepare_service.py
│   └── debrief_service.py
│
├── templates/
│   └── index.html
│
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
│
└── tests/
    └── probe_results.md
```

## Requirements

* Python 3.10+
* Ollama
* Mistral model
* A modern browser with microphone access
* Microphone

## Setup

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd manager-feedback-coach
```

### 2. Create a virtual environment

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Install and start Ollama

Install Ollama from:

https://ollama.com/

Then download the Mistral model:

```powershell
ollama pull mistral
```

Make sure Ollama is running.

You can verify it with:

```powershell
ollama list
```

You should see `mistral` / `mistral:latest`.

### 5. Start the application

```powershell
python app.py
```

Open the local URL shown by Flask, typically:

```text
http://127.0.0.1:5000
```

Allow microphone access when the browser asks.

## How to Use

1. Open the application.
2. Review the employee context.
3. Use Prepare to plan the conversation.
4. Switch to Rehearse.
5. Speak as the manager.
6. The simulated employee responds using Mistral.
7. Practise the conversation naturally, including interruptions or objections.
8. Switch to Debrief.
9. Review the coaching generated from the actual transcript.

## Privacy / Data Handling

This is a local prototype.

* The synthetic employee record is stored locally in `employee_record.json`.
* Mistral runs locally through Ollama.
* The rehearsal transcript is maintained as application state and is not stored in a database.
* Sensitive employee information is selectively filtered before being included in prompts.
* The included employee data is synthetic and fictional.

For a production system, additional access control, encryption, retention policies, audit logging, and privacy controls would be required.

## Important Note

The SpeechRecognition implementation is browser-dependent. Depending on the browser and configuration, speech recognition may rely on an online recognition service. The LLM itself is local through Ollama.

## Future Improvements

* Fully offline speech-to-text using local Whisper
* Local/offline text-to-speech
* Stronger deterministic transcript/quote validation
* Persistent but controlled conversation history
* Authentication and role-based access
* Encryption and retention controls
* Automated evaluation tests
* Streaming LLM responses for lower latency

## License

This project was created as a technical prototype / take-home project.
