"use strict";

// =========================================================
// MANAGER FEEDBACK COACH - main application JavaScript
// =========================================================

// ---------------------------------------------------------
// CONFIG  (tune turn-taking here)
// ---------------------------------------------------------

const CONFIG = {
    RECOGNITION_LANG: "en-IN",

    // true  = one long recognition session (no gaps between phrases, best for pauses)
    // false = short sessions (use this if you see duplicated / repeating text)
    CONTINUOUS: true,

    // How long the manager must be silent before the turn is sent.
    SILENCE_MS: 2000,             // normal finished-sounding sentence
    SILENCE_MS_SHORT: 3000,       // very short utterance (probably still thinking)
    SILENCE_MS_UNFINISHED: 3500,  // sentence ends on "and", "but", "because", ...
    SHORT_TURN_WORDS: 5,

    // Words needed before speech counts as an interruption (ignores tiny noises / echo)
    BARGE_IN_MIN_WORDS: 2,

    RESTART_DELAY_MS: 80
};

const UNFINISHED_ENDINGS = new Set([
    "and", "but", "so", "because", "the", "a", "an", "to", "of", "um", "uh", "like",
    "that", "which", "if", "or", "then", "with", "for", "i", "you", "is", "are", "we",
    "it", "was", "in", "on", "at", "my", "your", "about"
]);


// ---------------------------------------------------------
// STATE
// ---------------------------------------------------------

let conversation = [];
let currentMode = "prepare";

let meetingActive = false;
let isGeneratingResponse = false;
let meetingSessionId = 0;     // changes on every start / end -> stale responses are dropped
let debriefRequestId = 0;

// speech recognition
let recognition = null;
let recognitionSupported = false;
let recognitionRunning = false;
let recognitionShouldRun = false;
let recognitionSessionId = 0;
let activeRecognitionSession = 0;
let recognitionRestartTimer = null;

let committedText = "";   // finished recognition sessions of the current manager turn
let sessionText = "";     // text of the recognition session that is running now

let managerIsSpeaking = false;
let silenceTimer = null;

// employee speech
let employeeSpeechStarted = false;
let speechGenerationId = 0;
let currentRohit = null;  // { turn, el, full }
let spokenIndex = 0;

// timing
let sendStartedAt = null;
let llmFinishedAt = null;

// voices
let coachVoice = null;
let rohitVoice = null;


// ---------------------------------------------------------
// DOM
// ---------------------------------------------------------

const $ = (id) => document.getElementById(id);

const contextScreen = $("contextScreen");
const workspace = $("workspace");

const startPrepareButton = $("startPrepare");

const preparePanel = $("preparePanel");
const rehearsePanel = $("rehearsePanel");
const debriefPanel = $("debriefPanel");

const currentModeTitle = $("currentModeTitle");
const currentModeDescription = $("currentModeDescription");
const voiceStatusDot = $("voiceStatusDot");
const voiceStatus = $("voiceStatus");

const prepareInput = $("prepareInput");
const prepareButton = $("prepareButton");
const prepareResponse = $("prepareResult");

const managerInput = $("managerInput");
const sendButton = $("sendButton");
const micButton = $("micButton");
const transcript = $("transcript");

const startMeetingButton = $("startMeeting");
const endMeetingButton = $("endMeeting");
const stopSpeakingButton = $("stopSpeakingButton");
const turnStatus = $("turnStatus");
const turnDescription = $("turnDescription");
const liveMeetingCard = $("liveMeetingCard");
const timeToFirstSound = $("timeToFirstSound");

const debriefButton = $("debriefButton");
const debriefResponse = $("debriefResult");
const debriefTranscript = $("debriefTranscript");
const modeBanner = $("modeBanner");
const backToRehearseButton = $("backToRehearse");


// =========================================================
// INIT
// =========================================================

document.addEventListener("DOMContentLoaded", () => {
    setupModeButtons();
    setupPrepare();
    setupRehearsal();
    setupMeetingControls();
    setupDebrief();
    setupSpeechRecognition();
    setupVoices();
    showContextScreen();
    updateWorkspaceHeader("rehearse");
    updateRecognitionUI();
});


// =========================================================
// SCREENS / MODES
// =========================================================

function showContextScreen() {
    currentMode = "rehearse";
    contextScreen.classList.remove("hidden");
    workspace.classList.add("hidden");
}

function startWorkspace() {
    contextScreen.classList.add("hidden");
    workspace.classList.remove("hidden");
    showMode("rehearse");
    prepareInput?.focus();
}

/**
 * Prepare (left) is always visible.
 * The right side shows either the Rehearse view or the Debrief view.
 */
function showMode(mode) {
    currentMode = mode === "debrief" ? "debrief" : "rehearse";

    rehearsePanel.classList.toggle("hidden", currentMode === "debrief");
    debriefPanel.classList.toggle("hidden", currentMode !== "debrief");

    updateWorkspaceHeader(currentMode);

    if (currentMode === "debrief") updateDebriefTranscript();
}

function updateWorkspaceHeader(mode) {
    const debrief = mode === "debrief";

    modeBanner.className = `mode-banner ${debrief ? "debrief" : "rehearse"}`;
    currentModeTitle.textContent = debrief ? "DEBRIEF" : "REHEARSE";
    currentModeDescription.textContent = debrief
        ? "Rohit has left. This is the coach, based only on what you said."
        : "You are talking to Rohit (simulated).";
}

function setupModeButtons() {
    startPrepareButton?.addEventListener("click", startWorkspace);

    backToRehearseButton?.addEventListener("click", () => {
        if (meetingActive) return;
        showMode("rehearse");
        updateTurnStatus("Ready to start", "Press Start, then speak.");
    });
}


// =========================================================
// PREPARE
// =========================================================

// Prepare is a short chat: the coach remembers earlier messages, so the manager can follow up.
let prepareHistory = [];

const PREPARE_SUGGESTIONS = [
    "Plan the conversation",
    "Write my opening line",
    "Give me 5 questions to ask",
    "What if he gets defensive?"
];

function setupPrepare() {
    if (!prepareButton || !prepareInput) return;

    // quick-start buttons (click, then edit the text and add your own details)
    const chips = document.createElement("div");
    chips.className = "chips";

    PREPARE_SUGGESTIONS.forEach((label) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "secondary-button";
        chip.style.cssText = "min-height:28px;padding:0 10px;font-size:12px;font-weight:500;";
        chip.textContent = label;
        chip.addEventListener("click", () => {
            prepareInput.value = label;
            prepareInput.focus();
        });
        chips.appendChild(chip);
    });

    prepareInput.parentNode.insertBefore(chips, prepareInput);

    // "start over" button
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "secondary-button";
    reset.textContent = "Start over";
    reset.addEventListener("click", () => {
        prepareHistory = [];
        prepareResponse.innerHTML = "";
        prepareInput.value = "";
    });
    prepareButton.parentNode.insertBefore(reset, prepareButton);
    
    prepareButton.addEventListener("click", sendPrepareMessage);

    prepareInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            sendPrepareMessage();
        }
    });
}

async function sendPrepareMessage() {
    const message = prepareInput.value.trim();

    if (!message) {
        appendPrepareEntry("coach", "Please describe what you want help with, or pick one of the buttons above.");
        return;
    }

    const historyForRequest = prepareHistory.slice();

    prepareButton.disabled = true;
    appendPrepareEntry("manager", message);
    const pending = appendPrepareEntry("coach", "Thinking...");
    prepareInput.value = "";

    try {
        const response = await fetch("/api/prepare", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message, history: historyForRequest })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Prepare request failed.");

        const answer = data.response || "No preparation response returned.";
        pending.textContent = answer;

        prepareHistory.push({ role: "manager", text: message });
        prepareHistory.push({ role: "coach", text: answer });

    } catch (error) {
        console.error("Prepare error:", error);
        pending.textContent = `Error: ${error.message}`;
        prepareInput.value = message; // give the text back so nothing is lost
    } finally {
        prepareButton.disabled = false;
    }
}

function appendPrepareEntry(who, text) {
    const block = document.createElement("div");
    block.className = `chat-entry ${who}`;

    const label = document.createElement("div");
    label.className = "chat-who";
    label.textContent = who === "manager" ? "You" : "Coach";

    const body = document.createElement("div");
    body.className = "chat-text";
    body.textContent = text;

    block.appendChild(label);
    block.appendChild(body);
    prepareResponse.appendChild(block);
    prepareResponse.scrollTop = prepareResponse.scrollHeight;

    return body;
}


// =========================================================
// TEXT HELPERS
// =========================================================

function normalizeSpeechText(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
}

function wordCount(text) {
    const t = normalizeSpeechText(text);
    return t ? t.split(" ").length : 0;
}

/** Joins two pieces of text, removing an overlap at the seam (protects against repeated phrases). */
function mergeWithoutDuplication(existing, incoming) {
    existing = normalizeSpeechText(existing);
    incoming = normalizeSpeechText(incoming);

    if (!existing) return incoming;
    if (!incoming) return existing;

    const e = existing.toLowerCase();
    const i = incoming.toLowerCase();

    if (e === i || e.includes(i)) return existing;
    if (i.includes(e)) return incoming;

    const ew = existing.split(" ");
    const iw = incoming.split(" ");
    const max = Math.min(ew.length, iw.length);

    for (let size = max; size >= 1; size--) {
        const end = ew.slice(ew.length - size).join(" ").toLowerCase();
        const start = iw.slice(0, size).join(" ").toLowerCase();
        if (end === start) {
            const rest = iw.slice(size).join(" ");
            return rest ? `${existing} ${rest}` : existing;
        }
    }
    return `${existing} ${incoming}`;
}

function currentSpeech() {
    return normalizeSpeechText(mergeWithoutDuplication(committedText, sessionText));
}


// =========================================================
// SPEECH RECOGNITION
// =========================================================

function setupSpeechRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SR) {
        recognitionSupported = false;
        micButton.disabled = true;
        micButton.textContent = "Mic unavailable";
        updateVoiceStatus("Voice unavailable");
        return;
    }

    recognitionSupported = true;
    micButton.addEventListener("click", toggleMicrophone);
}

function toggleMicrophone() {
    if (!recognitionSupported) return;

    if (recognitionRunning) {
        stopRecognition();
        updateTurnStatus("Microphone paused", "Press Speak to listen again.");
        updateVoiceStatus("Ready");
        return;
    }

    if (!meetingActive) {
        updateTurnStatus("Start the meeting first", "Press Start Meeting before using the microphone.");
        return;
    }

    startManagerListening(true);
}

function createRecognitionInstance() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return null;

    const instance = new SR();
    instance.continuous = CONFIG.CONTINUOUS;
    instance.interimResults = true;
    instance.maxAlternatives = 1;
    instance.lang = CONFIG.RECOGNITION_LANG;

    const id = ++recognitionSessionId;
    activeRecognitionSession = id;
    const live = () => id === activeRecognitionSession;

    instance.onstart = () => {
        if (!live()) return;
        recognitionRunning = true;
        updateRecognitionUI();
    };

    // The manager is making sound again -> they are NOT finished. Cancel the pending send.
    instance.onspeechstart = () => {
        if (!live()) return;
        clearSilenceTimer();
    };

    // Sound stopped -> start counting silence.
    instance.onspeechend = () => {
        if (!live()) return;
        armSilenceTimer();
    };

    instance.onresult = (event) => {
        if (!live()) return;
        handleRecognitionResult(event);
    };

    instance.onerror = (event) => {
        if (!live()) return;

        console.warn("Speech recognition error:", event.error);
        recognitionRunning = false;
        commitSession();
        updateRecognitionUI();

        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
            recognitionShouldRun = false;
            updateVoiceStatus("Microphone permission required");
            updateTurnStatus("Microphone permission required", "Allow microphone access in your browser.");
            return;
        }

        if (recognitionShouldRun && meetingActive) scheduleRecognitionRestart();
    };

    instance.onend = () => {
        if (!live()) return;
        recognitionRunning = false;
        commitSession();
        updateRecognitionUI();

        if (recognitionShouldRun && meetingActive) scheduleRecognitionRestart();
    };

    return instance;
}

/** A recognition session finished: keep its text, start the next session with an empty buffer. */
function commitSession() {
    committedText = mergeWithoutDuplication(committedText, sessionText);
    sessionText = "";
}

function startRecognition() {
    if (!recognitionSupported || !recognitionShouldRun || !meetingActive || recognitionRunning) return;

    if (recognitionRestartTimer) {
        clearTimeout(recognitionRestartTimer);
        recognitionRestartTimer = null;
    }

    recognition = createRecognitionInstance();
    if (!recognition) return;

    try {
        recognition.start();
    } catch (error) {
        console.warn("Recognition start error:", error.message);
        recognitionRunning = false;
        scheduleRecognitionRestart();
    }
}

function stopRecognition() {
    recognitionShouldRun = false;

    if (recognitionRestartTimer) {
        clearTimeout(recognitionRestartTimer);
        recognitionRestartTimer = null;
    }

    // invalidate the current session so late events cannot leak into the next turn
    activeRecognitionSession = ++recognitionSessionId;

    if (recognition) {
        try { recognition.abort(); } catch (error) { /* ignore */ }
    }

    recognitionRunning = false;
    updateRecognitionUI();
}

function scheduleRecognitionRestart() {
    if (!recognitionShouldRun || !meetingActive || recognitionRestartTimer) return;

    recognitionRestartTimer = setTimeout(() => {
        recognitionRestartTimer = null;
        if (!recognitionShouldRun || !meetingActive || recognitionRunning) return;
        startRecognition();
    }, CONFIG.RESTART_DELAY_MS);
}

/** Throw away everything heard so far (e.g. Rohit's voice picked up by the mic) and listen fresh. */
function restartRecognitionFresh() {
    stopRecognition();
    clearManagerSpeechState();
    recognitionShouldRun = true;
    scheduleRecognitionRestart();
}

function handleRecognitionResult(event) {
    if (!event.results) return;

    sessionText = normalizeSpeechText(
        Array.from(event.results).map((r) => (r[0] ? r[0].transcript : "")).join(" ")
    );

    const text = currentSpeech();
    if (!text) return;

    // ---- barge-in ----
    if (employeeSpeechStarted) {
        if (wordCount(text) < CONFIG.BARGE_IN_MIN_WORDS) return;
        handleManagerInterruption();
    }

    managerIsSpeaking = true;
    updateManagerInput(text);
    updateTurnStatus("You're speaking", "Rohit is listening. He replies after you pause (or press Send).");
    updateVoiceStatus("Listening");

    armSilenceTimer();
}


// =========================================================
// TURN-TAKING  (silence detection with an adaptive delay)
// =========================================================

function silenceDelay(text) {
    const words = normalizeSpeechText(text).toLowerCase().split(" ").filter(Boolean);
    const last = (words[words.length - 1] || "").replace(/[^a-z']/g, "");

    if (UNFINISHED_ENDINGS.has(last)) return CONFIG.SILENCE_MS_UNFINISHED; // sentence obviously unfinished
    if (words.length < CONFIG.SHORT_TURN_WORDS) return CONFIG.SILENCE_MS_SHORT;
    return CONFIG.SILENCE_MS;
}

function clearSilenceTimer() {
    if (silenceTimer) {
        clearTimeout(silenceTimer);
        silenceTimer = null;
    }
}

function armSilenceTimer() {
    clearSilenceTimer();

    if (!meetingActive || !managerIsSpeaking) return;

    silenceTimer = setTimeout(() => {
        silenceTimer = null;
        if (managerIsSpeaking && !employeeSpeechStarted && !isGeneratingResponse && meetingActive) {
            finishManagerTurn();
        }
    }, silenceDelay(currentSpeech()));
}

function finishManagerTurn() {
    if (isGeneratingResponse) return;

    const message = currentSpeech();
    if (!message) return;

    console.log("FINAL MANAGER TURN:", message);

    // stop the mic BEFORE sending so late events cannot change the message
    stopRecognition();
    clearManagerSpeechState();
    sendManagerMessage(message);
}

function clearManagerSpeechState() {
    committedText = "";
    sessionText = "";
    managerIsSpeaking = false;
    clearSilenceTimer();
    updateManagerInput("");
}

function updateManagerInput(text) {
    if (!managerInput) return;
    managerInput.value = text;
    managerInput.scrollTop = managerInput.scrollHeight;
}


// =========================================================
// INTERRUPTION / BARGE-IN
// =========================================================

function handleManagerInterruption() {
    if (!employeeSpeechStarted) return;

    console.log("BARGE-IN: manager interrupted Rohit.");

    markRohitInterrupted();
    stopRohitSpeaking();

    liveMeetingCard.classList.remove("rohit-speaking");
    liveMeetingCard.classList.add("interruption-active");

    updateTurnStatus("You interrupted Rohit", "His voice has stopped. Finish what you want to say.");
    updateVoiceStatus("Listening");
}

/** Rohit's turn is kept in the conversation, cut at the point where he was actually stopped. */
function markRohitInterrupted() {
    if (!currentRohit) return;

    const { turn, el, full } = currentRohit;
    if (spokenIndex >= full.length - 1) return; // he had effectively finished

    const heard = full.slice(0, spokenIndex).trim();
    const marked = heard ? `${heard}— [interrupted]` : "[interrupted]";

    turn.text = marked;
    if (el) el.textContent = marked;
}

function stopRohitSpeaking() {
    speechGenerationId++;
    employeeSpeechStarted = false;

    if ("speechSynthesis" in window) window.speechSynthesis.cancel();

    liveMeetingCard?.classList.remove("rohit-speaking");
}


// =========================================================
// VOICES  (two different voices so the speakers are never confused)
// =========================================================

function setupVoices() {
    if (!("speechSynthesis" in window)) return;
    pickVoices();
    window.speechSynthesis.onvoiceschanged = pickVoices;
}

function pickVoices() {
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) return;

    const english = voices.filter((v) => /^en/i.test(v.lang));
    const male = english.find((v) => /(ravi|david|mark|james|daniel|male|rishi|guy|george|alex)/i.test(v.name));
    const female = english.find((v) => /(zira|heera|samantha|female|susan|karen|aria|jenny|libby|veena)/i.test(v.name));

    rohitVoice = male || english[0] || null;
    coachVoice = female || english.find((v) => v !== rohitVoice) || null;
}


// =========================================================
// REHEARSAL CONTROLS
// =========================================================

function setupRehearsal() {
    sendButton?.addEventListener("click", () => {
        const message = managerInput ? managerInput.value.trim() : "";
        if (!message) return;

        if (employeeSpeechStarted) handleManagerInterruption();

        stopRecognition();
        clearManagerSpeechState();
        sendManagerMessage(message);
    });

    stopSpeakingButton?.addEventListener("click", () => {
        markRohitInterrupted();
        stopRohitSpeaking();
        updateTurnStatus("Rohit stopped", "You can speak now.");
        updateVoiceStatus("Listening");
        if (meetingActive) startManagerListening(true);
    });

    managerInput?.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && event.ctrlKey) {
            event.preventDefault();
            sendButton?.click();
        }
    });
}


// =========================================================
// SEND MANAGER MESSAGE -> ROHIT
// =========================================================

function cleanRohitResponse(text) {
    let response = normalizeSpeechText(text);
    if (!response) return "";

    response = response.replace(/^```(?:text)?/i, "").replace(/```$/i, "").trim();
    response = response.replace(/\[[^\]]*\]|\([^)]*\)/g, "").trim();

    const prefixes = ["rohit — simulated employee:", "simulated employee:", "employee:", "rohit:"];
    let changed = true;
    while (changed) {
        changed = false;
        for (const prefix of prefixes) {
            if (response.toLowerCase().startsWith(prefix)) {
                response = response.slice(prefix.length).trim();
                changed = true;
            }
        }
    }

    if (response.length >= 2 && /^["'].*["']$/.test(response)) {
        response = response.slice(1, -1).trim();
    }
    return response;
}

async function sendManagerMessage(message) {
    message = normalizeSpeechText(message);
    if (!message || isGeneratingResponse) return;

    const session = meetingSessionId;

    stopRohitSpeaking();
    managerIsSpeaking = false;
    isGeneratingResponse = true;

    updateTurnStatus("Rohit is thinking", "Preparing his response...");
    updateVoiceStatus("Thinking");

    sendButton.disabled = true;
    micButton.disabled = true;

    // history BEFORE this message (the backend adds the latest message itself)
    const previousConversation = conversation.map((t) => ({ speaker: t.speaker, text: t.text }));

    // The manager's turn is stored immediately, so it is never lost - even if the meeting
    // is ended while Rohit is still "thinking".
    conversation.push({ speaker: "manager", text: message });
    addTranscriptMessage("manager", message);

    sendStartedAt = performance.now();

    try {
        const response = await fetch("/api/rehearse", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message, conversation: previousConversation })
        });
        const data = await response.json();

        // the rehearsal was ended / restarted while waiting -> discard this stale reply
        if (session !== meetingSessionId) return;

        if (!response.ok) throw new Error(data.error || "Rehearsal request failed.");

        const rohitResponse = cleanRohitResponse(data.response);
        if (!rohitResponse) throw new Error("Rohit returned an empty response.");

        llmFinishedAt = performance.now();

        const turn = { speaker: "rohit", text: rohitResponse };
        conversation.push(turn);
        const el = addTranscriptMessage("rohit", rohitResponse);

        speakEmployeeResponse(rohitResponse, turn, el);

    } catch (error) {
        if (session !== meetingSessionId) return;

        console.error("Rehearsal error:", error);
        addTranscriptMessage("system", `Error: ${error.message}`);
        updateTurnStatus("Something went wrong", "Check that Flask and Ollama are running.");
        updateVoiceStatus("Error");

    } finally {
        if (session === meetingSessionId) {
            isGeneratingResponse = false;
            sendButton.disabled = false;
            micButton.disabled = false;
        }
    }
}


// =========================================================
// ROHIT TEXT-TO-SPEECH
// =========================================================

function speakEmployeeResponse(text, turn, el) {
    if (!("speechSynthesis" in window)) {
        updateTurnStatus("Rohit responded", "Browser speech synthesis is unavailable.");
        updateVoiceStatus("Voice unavailable");
        if (meetingActive) startManagerListening(true);
        return;
    }

    window.speechSynthesis.cancel();

    const generationId = ++speechGenerationId;
    currentRohit = { turn, el, full: text };
    spokenIndex = 0;

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-IN";
    utterance.rate = 0.98;
    utterance.pitch = 0.9;
    if (rohitVoice) utterance.voice = rohitVoice;

    utterance.onstart = () => {
        if (generationId !== speechGenerationId) return;

        employeeSpeechStarted = true;

        const total = Math.round(performance.now() - (sendStartedAt || performance.now()));
        const llm = Math.round((llmFinishedAt || performance.now()) - (sendStartedAt || performance.now()));
        timeToFirstSound.textContent = `${total} ms (model ${llm} ms)`;

        updateTurnStatus("Rohit is speaking (simulated)", "You can interrupt him at any time.");
        updateVoiceStatus("Rohit speaking");

        liveMeetingCard.classList.add("rohit-speaking");
        liveMeetingCard.classList.remove("interruption-active");
    };

    utterance.onboundary = (event) => {
        if (generationId !== speechGenerationId) return;
        if (typeof event.charIndex === "number") spokenIndex = event.charIndex;
    };

    utterance.onend = () => {
        if (generationId !== speechGenerationId) return;

        employeeSpeechStarted = false;
        currentRohit = null;
        liveMeetingCard.classList.remove("rohit-speaking");

        if (meetingActive) {
            // discard anything the mic heard while Rohit was talking (his own voice / echo)
            restartRecognitionFresh();
            updateTurnStatus("Your turn", "Speak naturally. Rohit is listening.");
            updateVoiceStatus("Listening");
        } else {
            updateTurnStatus("Response complete", "Start the meeting to continue.");
            updateVoiceStatus("Ready");
        }
    };

    utterance.onerror = (event) => {
        if (event.error === "canceled" || event.error === "interrupted") return;

        console.warn("Speech synthesis error:", event.error);
        employeeSpeechStarted = false;
        liveMeetingCard.classList.remove("rohit-speaking");
        if (meetingActive) startManagerListening(true);
    };

    // Start listening BEFORE Rohit speaks, so the first words of an interruption are not lost.
    if (meetingActive) {
        recognitionShouldRun = true;
        startRecognition();
    }

    window.speechSynthesis.speak(utterance);
}


// =========================================================
// MEETING CONTROLS
// =========================================================

function setupMeetingControls() {
    startMeetingButton?.addEventListener("click", startMeeting);
    endMeetingButton?.addEventListener("click", endMeeting);
}

function startMeeting() {
    if (meetingActive) return;

    // new rehearsal = completely fresh state
    showMode("rehearse");
    meetingSessionId++;
    debriefRequestId++;
    meetingActive = true;
    isGeneratingResponse = false;
    conversation = [];
    currentRohit = null;

    stopRohitSpeaking();
    stopRecognition();
    clearManagerSpeechState();

    transcript.innerHTML = "";
    debriefTranscript.textContent = "Rehearsal in progress.";
    debriefResponse.textContent = "";
    debriefResponse.style.display = "none";
    timeToFirstSound.textContent = "—";
    managerInput.value = "";

    startMeetingButton.disabled = true;
    endMeetingButton.disabled = false;
    sendButton.disabled = false;
    micButton.disabled = false;

    liveMeetingCard.classList.add("meeting-active");
    liveMeetingCard.classList.remove("rohit-speaking", "interruption-active");

    updateTurnStatus("Meeting started", "You have the floor. Start the conversation.");
    updateVoiceStatus("Listening");

    speakMeetingAnnouncement();
}

/** The coach (a different voice from Rohit) announces the start. */
function speakMeetingAnnouncement() {
    if (!("speechSynthesis" in window)) {
        startManagerListening(true);
        return;
    }

    const utterance = new SpeechSynthesisUtterance(
        "Coach here. The rehearsal has started. Rohit is simulated. You can begin when you're ready."
    );
    utterance.lang = "en-IN";
    utterance.rate = 1.0;
    utterance.pitch = 1.15;
    if (coachVoice) utterance.voice = coachVoice;

    const done = () => { if (meetingActive) startManagerListening(true); };
    utterance.onend = done;
    utterance.onerror = done;

    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
}

function speakCoach(text) {
    if (!("speechSynthesis" in window)) return;

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-IN";
    utterance.pitch = 1.15;
    if (coachVoice) utterance.voice = coachVoice;

    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
}

/** fresh = true: start a clean recognition session with an empty buffer. */
function startManagerListening(fresh = false) {
    if (!meetingActive) return;

    employeeSpeechStarted = false;

    updateTurnStatus("Your turn", "Speak naturally. Rohit is listening.");
    updateVoiceStatus("Listening");

    if (fresh && !recognitionRunning) clearManagerSpeechState();

    recognitionShouldRun = true;
    startRecognition();
}

function endMeeting() {
    if (!meetingActive) {
        showMode("debrief");
        return;
    }

    meetingSessionId++;          // any Rohit reply still in flight is now stale and ignored
    meetingActive = false;
    isGeneratingResponse = false;
    currentRohit = null;

    markRohitInterrupted();
    stopRohitSpeaking();
    stopRecognition();
    clearManagerSpeechState();

    startMeetingButton.disabled = false;
    endMeetingButton.disabled = true;
    sendButton.disabled = false;
    micButton.disabled = false;

    liveMeetingCard.classList.remove("meeting-active", "rohit-speaking", "interruption-active");

    updateTurnStatus("Meeting ended", "Generating your debrief...");
    speakCoach("Rehearsal over. Rohit has left. Here is your debrief.");
    updateVoiceStatus("Ready");

    // clear the previous debrief immediately so an old result can never be shown for a new rehearsal
    debriefResponse.textContent = "";
    debriefResponse.style.display = "none";

    showMode("debrief");
    generateDebrief();
}


// =========================================================
// DEBRIEF
// =========================================================

function setupDebrief() {
    debriefButton?.addEventListener("click", generateDebrief);
}

async function generateDebrief() {
    const snapshot = conversation.map((t) => ({ speaker: t.speaker, text: t.text }));

    if (!snapshot.length) {
        showDebriefMessage("No rehearsal conversation was recorded. Complete a rehearsal before generating a debrief.");
        return;
    }

    const managerTurns = snapshot.filter((t) => t.speaker === "manager" && String(t.text || "").trim());

    if (!managerTurns.length) {
        showDebriefMessage("No manager speech was recorded. Complete a rehearsal before generating a debrief.");
        return;
    }

    const requestId = ++debriefRequestId;

    debriefButton.disabled = true;
    updateDebriefTranscript();
    showDebriefMessage(`Generating debrief for this rehearsal (${managerTurns.length} manager turn(s))...`);

    try {
        const response = await fetch("/api/debrief", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ conversation: snapshot })
        });
        const data = await response.json();

        if (requestId !== debriefRequestId) return; // a newer rehearsal started meanwhile

        if (!response.ok) throw new Error(data.error || "Debrief request failed.");

        showDebriefMessage(data.response || "No debrief response returned.");
    } catch (error) {
        if (requestId !== debriefRequestId) return;
        console.error("Debrief error:", error);
        showDebriefMessage(`Error: ${error.message}`);
    } finally {
        if (requestId === debriefRequestId) debriefButton.disabled = false;
    }
}

const DEBRIEF_HEADINGS = /^(READINESS CALL|GOOD MOMENT|MOMENT TO IMPROVE|USABLE OPENING LINE|LIKELY OBJECTION \d|COACHING SUMMARY)\s*:?$/i;

function showDebriefMessage(message) {
    debriefResponse.style.display = "block";
    debriefResponse.innerHTML = "";

    let afterReadiness = false;

    String(message).split("\n").forEach((raw) => {
        const line = raw.trim().replace(/^\*+|\*+$/g, "").trim();
        if (!line) return;

        const el = document.createElement("div");

        if (DEBRIEF_HEADINGS.test(line)) {
            el.className = "debrief-heading";
            el.textContent = line.replace(/:$/, "");
            afterReadiness = /^READINESS CALL/i.test(line);
        } else {
            el.className = "debrief-line" + (afterReadiness ? " readiness" : "");
            el.textContent = raw.trim();
            afterReadiness = false;
        }
        debriefResponse.appendChild(el);
    });
}

function updateDebriefTranscript() {
    const lines = conversation
        .filter((t) => t && t.text && String(t.text).trim())
        .map((t) => {
            const speaker =
                t.speaker === "manager" ? "YOU — MANAGER"
                : t.speaker === "rohit" ? "ROHIT — SIMULATED EMPLOYEE"
                : "SYSTEM";
            return `${speaker}: ${t.text}`;
        });

    debriefTranscript.textContent = lines.length
        ? lines.join("\n\n")
        : "No rehearsal conversation recorded.";
}


// =========================================================
// TRANSCRIPT
// =========================================================

/** Adds a line and returns the element holding the text (so an interrupted line can be edited). */
function addTranscriptMessage(speaker, text) {
    text = normalizeSpeechText(text);
    if (!transcript || !text) return null;

    transcript.querySelector(".empty-transcript")?.remove();

    const entry = document.createElement("div");
    entry.className = `transcript-entry ${speaker}`;

    const message = document.createElement("div");
    message.className = `transcript-message ${speaker}`;

    const label = document.createElement("div");
    label.className = "transcript-speaker";
    label.textContent =
        speaker === "manager" ? "You — Manager"
        : speaker === "rohit" ? "Rohit — Simulated Employee"
        : "System";

    const body = document.createElement("div");
    body.className = "transcript-text";
    body.textContent = text;

    message.appendChild(label);
    message.appendChild(body);
    entry.appendChild(message);
    transcript.appendChild(entry);
    transcript.scrollTop = transcript.scrollHeight;

    return body;
}


// =========================================================
// STATUS UI
// =========================================================

function updateTurnStatus(title, description) {
    if (turnStatus) turnStatus.textContent = title;
    if (turnDescription) turnDescription.textContent = description;
}

function updateVoiceStatus(status) {
    if (voiceStatus) voiceStatus.textContent = status;
    if (!voiceStatusDot) return;

    voiceStatusDot.classList.remove("status-listening", "status-speaking", "status-thinking", "status-error");

    if (status === "Listening") voiceStatusDot.classList.add("status-listening");
    if (status === "Rohit speaking") voiceStatusDot.classList.add("status-speaking");
    if (status === "Thinking") voiceStatusDot.classList.add("status-thinking");
    if (["Error", "Voice unavailable", "Microphone permission required"].includes(status)) {
        voiceStatusDot.classList.add("status-error");
    }
}

function updateRecognitionUI() {
    if (!micButton) return;

    if (!recognitionSupported) {
        micButton.disabled = true;
        micButton.textContent = "Mic unavailable";
        return;
    }

    micButton.classList.toggle("listening", recognitionRunning);
    micButton.textContent = recognitionRunning ? "🎙 Listening" : "🎙 Speak";
}


// =========================================================
// KEYBOARD + CLEANUP
// =========================================================

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && employeeSpeechStarted) {
        markRohitInterrupted();
        stopRohitSpeaking();
        updateTurnStatus("Rohit stopped", "You can speak now.");
        if (meetingActive) startManagerListening(true);
    }
});

window.addEventListener("beforeunload", () => {
    meetingActive = false;
    recognitionShouldRun = false;
    stopRohitSpeaking();
    stopRecognition();
});