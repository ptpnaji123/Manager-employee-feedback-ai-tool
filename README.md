# Manager Feedback Coach

Rehearse a difficult feedback conversation with an AI employee before having it for real.
Flask + Ollama (`mistral`), running entirely locally. No data leaves the machine.

```
Context screen  ->  [1] PREPARE  ->  [2] REHEARSE  ->  [3] DEBRIEF
                     coach          simulated        readiness verdict,
                     builds a plan  employee         what worked/didn't,
                     (Situation-     talks back       2 likely objections
                      Behaviour-
                      Impact)
```

**Scenario:** Rohit Menon, Senior Analyst, 34 months. 14 late arrivals in 90 days averaging 38
minutes, mostly Mon/Tue. One prior verbal conversation, no written follow-up. Rating declining,
backlog goal missed — but the record says **nothing about why**, and the app stops anyone
inventing a reason.

---

## Run it

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

ollama serve            # separate terminal
ollama pull mistral     # one-time, ~4GB

python app.py           # http://127.0.0.1:5000
```

Use **Chrome** for voice. Typing works in any browser. `python test.py` checks Ollama is up.

**Stack:** Flask, Jinja2 (one page), `requests`, Ollama/`mistral`, vanilla JS + CSS. No React,
no npm, no build step.

---

## Structure

```
app.py                      1 page route, 3 JSON API routes. No LLM code.
employee_record.json        THE source of truth. Read from disk each request.
test.py                     2-line Ollama connectivity check.

prompts/                    Behaviour lives here — edit text, not code.
  prepare_prompt.txt          Coach. Preamble + MODE/GUARD blocks.
  rehearsal_prompt.txt        Rohit's persona.
  debrief_prompt.txt          Evaluator + quote-fidelity rules.

services/
  llm_service.py              The single Ollama call. Swap providers here.
  llm_service1.py             DEAD. Old Gemini client, nothing imports it.
  prepare_service.py          Mode routing, 4 guards, topic-gating.
  conversation_service.py     Turn state machine + output enforcement.
  debrief_service.py          Quote verification + repair loop.

templates/index.html        SPA shell.
static/js/app.js            The real app: voice loop, turn-taking, TTS, all 3 modes.
static/css/style.css        Hand-written.
config/feedback_framework.json   NOT loaded by any code.
tests/probe_results.md          Empty placeholder.
```

---

## How it works

```
Browser (app.js) --POST--> Flask (app.py) --> prepare_service        --\
  voice loop                 validation       conversation_service --> llm_service --> Ollama
  session state              3 routes         debrief_service      --/
```

**Stateless.** No DB, no sessions, no cookies. The browser holds the conversation and re-posts
it every turn. Memory is a text window of the last N turns.

**Confidentiality is enforced in code, not by prompt.** All three services read the same
`employee_record.json` but each builds a different allow-listed view. `feedback_360` (peer
comments), `hr_notes` (medical leave, a flight-risk flag) and `compensation` are dropped before
any prompt is assembled. Performance data is additionally topic-gated in prepare mode.

**The three modes**

- **Prepare** — routes to `FULL_PLAN` / `FOCUSED` / `REDIRECT` and applies four guards:
  `reveal_360` and `health` and `pip` are refused outright; `label` ("he's lazy") is restated
  in record-supported facts. These four are the project's acceptance criteria.
- **Rehearse** — a state machine picks a stage, then `clean_rohit_response()` enforces the
  contract: 2–3 sentence cap, deletes sentences re-opening a settled issue, and strips every
  question unless allowed (max 2 per conversation).
- **Debrief** — every quote is verified against the real transcript. Fabricated ones trigger a
  re-prompt; after 3 attempts the closest real line is substituted. A bad quote never ships.

**Voice** (all in `app.js`): adaptive silence timeout, barge-in that marks Rohit's turn
`— [interrupted]`, listening starts *before* TTS so no interruption words are lost, and echo
discard. Model output is rendered with `textContent`, never `innerHTML`.

---

## API

All `POST`, JSON body.

| Route | Body | 200 |
|---|---|---|
| `/api/prepare` | `{message, history:[{role,text}]}` | `{response}` |
| `/api/rehearse` | `{message, conversation:[{speaker,text}]}` | `{speaker:"rohit", response}` |
| `/api/debrief` | `{conversation:[...]}` | `{response}` |

---

## Config

No settings module — every knob is a constant where it's used.

| What | Where |
|---|---|
| URL, model | `services/llm_service.py:3-4` |
| temperature | `0.8` prepare · `0.7` rehearse · `0.2` debrief |
| max_tokens | `700` prepare · `90` rehearse (latency) |
| history window | last 6 turns prepare · 14 rehearse |
| voice timings | `CONFIG` in `static/js/app.js` |
| host/port | `app.py:82` — `127.0.0.1:5000`, debug on |

`.env` holds three `GEMINI_*` keys. The running app reads none of them — they exist only for the
dead `llm_service1.py`.

---

## Known gaps

1. `config/feedback_framework.json` is never loaded — the framework is hardcoded prose in the prompts.
2. `services/llm_service1.py` is dead code and the only reason `google-genai`, `python-dotenv` and `.env` exist.
3. The record's numbers are duplicated in the JSON, `index.html` and a prompt file — they drift silently.
4. `.gitignore` lists `llm_service.py` and `test.py` but both are already tracked, so the rules do nothing.
5. No version pins in `requirements.txt`. No tests. 500s leak raw exception text.
6. No caching — the JSON and prompts are re-read on every request.

**Security:** confidential HR data is excluded in code and the LLM is local. But there is no
auth, no sessions, no rate limiting, and debug mode is on. Localhost prototype only.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Could not connect to Ollama` | `ollama serve` in another terminal |
| `HTTP 404` from Ollama | `ollama pull mistral:latest` |
| `No module named 'services'` | Run from the project root |
| Mic disabled | Use Chrome, or type |
| Port 5000 busy | Change `app.py:82` |
