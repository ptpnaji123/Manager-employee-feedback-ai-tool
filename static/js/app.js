"use strict";

// =========================================================
// MANAGER FEEDBACK COACH
// STT: Whisper via Flask /api/transcribe
// TTS: Groq Orpheus via Flask /api/tts
// Rehearsal memory: per-meeting, kept on the server, deleted when the meeting ends
// =========================================================

// CONFIG

const CONFIG = {
    RECOGNITION_LANG: "en-IN",
    SILENCE_MS: 2000,
    SILENCE_MS_SHORT: 3000,
    SILENCE_MS_UNFINISHED: 3500,
    SHORT_TURN_WORDS: 5,
    BARGE_IN_MIN_WORDS: 2,
    MAX_RECORDING_MS: 30000,
    SPEECH_THRESHOLD: 0.025,
    TTS_ENDPOINT: "/api/tts",
    REHEARSE_END_ENDPOINT: "/api/rehearse/end"
};

const UNFINISHED_ENDINGS = new Set([
    "and", "but", "so", "because", "the", "a", "an", "to",
    "of", "um", "uh", "like", "that", "which", "if", "or",
    "then", "with", "for", "i", "you", "is", "are", "we",
    "it", "was", "in", "on", "at", "my", "your", "about"
]);

// =========================================================
// STATE
// =========================================================

let conversation = [];
let prepareHistory = [];
let currentMode = "rehearse";

let meetingActive = false;
let isGeneratingResponse = false;
let meetingSessionId = 0;
let meetingId = null;          // unique id sent to the server for this meeting's memory
let debriefRequestId = 0;

let recognitionSupported = false;
let recognitionRunning = false;
let recognitionShouldRun = false;
let managerIsSpeaking = false;
let whisperIsProcessing = false;

let whisperStream = null;
let whisperRecorder = null;
let whisperAudioContext = null;
let whisperAnalyser = null;
let whisperChunks = [];
let whisperSilenceTimer = null;
let whisperMaxTimer = null;
let whisperAnimationFrame = null;
let whisperStartedAt = 0;
let whisperHasSpeech = false;
let whisperFinishRequested = false;

let employeeSpeechStarted = false;
let speechGenerationId = 0;
let currentRohit = null;
let spokenIndex = 0;

// Orpheus audio playback state
let currentAudio = null;
let currentAudioUrl = null;
let currentAudioGenerationId = 0;

let sendStartedAt = null;
let llmFinishedAt = null;

// =========================================================
// DOM
// =========================================================

const $ = id => document.getElementById(id);

const contextScreen = $("contextScreen");
const workspace = $("workspace");
const startPrepareButton = $("startPrepare");

const rehearsePanel = $("rehearsePanel");
const debriefPanel = $("debriefPanel");

const currentModeTitle = $("currentModeTitle");
const currentModeDescription = $("currentModeDescription");
const voiceStatusDot = $("voiceStatusDot");
const voiceStatus = $("voiceStatus");
const modeBanner = $("modeBanner");

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
const backToRehearseButton = $("backToRehearse");

// =========================================================
// INITIALIZATION
// =========================================================

document.addEventListener("DOMContentLoaded", () => {
    console.log("App.js loaded");

    try {
        setupModeButtons();
        setupPrepare();
        setupRehearsal();
        setupMeetingControls();
        setupDebrief();
        setupWhisperSTT();

        showContextScreen();
        updateWorkspaceHeader("rehearse");
        updateRecognitionUI();

        console.log("App initialized successfully");
    } catch (error) {
        console.error("App initialization failed:", error);
    }
});

// =========================================================
// SCREENS AND MODES
// =========================================================

function showContextScreen() {
    currentMode = "rehearse";
    contextScreen?.classList.remove("hidden");
    workspace?.classList.add("hidden");
}

function startWorkspace() {
    contextScreen?.classList.add("hidden");
    workspace?.classList.remove("hidden");
    showMode("rehearse");
    prepareInput?.focus();
}

function showMode(mode) {
    currentMode = mode === "debrief" ? "debrief" : "rehearse";

    rehearsePanel?.classList.toggle(
        "hidden", currentMode === "debrief"
    );

    debriefPanel?.classList.toggle(
        "hidden", currentMode !== "debrief"
    );

    updateWorkspaceHeader(currentMode);

    if (currentMode === "debrief") {
        updateDebriefTranscript();
    }
}

function updateWorkspaceHeader(mode) {
    const debrief = mode === "debrief";

    if (modeBanner) {
        modeBanner.className =
            `mode-banner ${debrief ? "debrief" : "rehearse"}`;
    }

    if (currentModeTitle) {
        currentModeTitle.textContent = debrief ? "DEBRIEF" : "REHEARSE";
    }

    if (currentModeDescription) {
        currentModeDescription.textContent = debrief
            ? "Rohit has left. This is the coach, based on what you said."
            : "You are talking to Rohit (simulated).";
    }
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
// PREPARE MODE
// =========================================================

const PREPARE_SUGGESTIONS = [
    "Plan the conversation",
    "Write my opening line",
    "Give me 5 questions to ask",
    "What if he gets defensive?"
];

function setupPrepare() {
    if (!prepareButton || !prepareInput) return;

    const chips = document.createElement("div");
    chips.className = "chips";

    PREPARE_SUGGESTIONS.forEach(label => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "secondary-button";
        chip.style.cssText =
            "min-height:28px;padding:0 10px;font-size:12px;font-weight:500;";
        chip.textContent = label;

        chip.addEventListener("click", () => {
            prepareInput.value = label;
            prepareInput.focus();
        });

        chips.appendChild(chip);
    });

    prepareInput.parentNode.insertBefore(chips, prepareInput);

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

    prepareInput.addEventListener("keydown", event => {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            sendPrepareMessage();
        }
    });
}

async function sendPrepareMessage() {
    const message = prepareInput.value.trim();

    if (!message) {
        appendPrepareEntry(
            "coach",
            "Describe what you need help with, or select a suggestion."
        );
        return;
    }

    const history = prepareHistory.slice();

    prepareButton.disabled = true;
    appendPrepareEntry("manager", message);
    const pending = appendPrepareEntry("coach", "Thinking...");
    prepareInput.value = "";

    try {
        const response = await fetch("/api/prepare", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message, history })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Prepare request failed.");
        }

        const answer = data.response || "No preparation response returned.";
        pending.textContent = answer;

        prepareHistory.push({ role: "manager", text: message });
        prepareHistory.push({ role: "coach", text: answer });

    } catch (error) {
        console.error("Prepare error:", error);
        pending.textContent = `Error: ${error.message}`;
        prepareInput.value = message;
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

    block.append(label, body);
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
    const value = normalizeSpeechText(text);
    return value ? value.split(" ").length : 0;
}

function silenceDelay(text) {
    const words = normalizeSpeechText(text).toLowerCase().split(" ");
    const last = (words[words.length - 1] || "").replace(/[^a-z']/g, "");

    if (UNFINISHED_ENDINGS.has(last)) {
        return CONFIG.SILENCE_MS_UNFINISHED;
    }

    if (words.length < CONFIG.SHORT_TURN_WORDS) {
        return CONFIG.SILENCE_MS_SHORT;
    }

    return CONFIG.SILENCE_MS;
}

function updateManagerInput(text) {
    if (!managerInput) return;

    managerInput.value = text;
    managerInput.scrollTop = managerInput.scrollHeight;
}

function clearManagerSpeechState() {
    managerIsSpeaking = false;

    clearTimeout(whisperSilenceTimer);
    whisperSilenceTimer = null;

    if (managerInput) managerInput.value = "";
}

// =========================================================
// WHISPER SPEECH-TO-TEXT
// =========================================================

function setupWhisperSTT() {
    recognitionSupported =
        !!navigator.mediaDevices?.getUserMedia &&
        !!window.MediaRecorder;

    if (!recognitionSupported) {
        if (micButton) {
            micButton.disabled = true;
            micButton.textContent = "Mic unavailable";
        }

        updateVoiceStatus("Voice unavailable");
        return;
    }

    micButton?.addEventListener("click", toggleMicrophone);
}

async function toggleMicrophone() {
    if (!meetingActive || whisperIsProcessing) return;

    if (recognitionRunning) {
        finishManagerTurn();
        return;
    }

    if (employeeSpeechStarted) {
        markRohitInterrupted();
        stopRohitSpeaking();
    }

    await startManagerListening(true);
}

async function startManagerListening(fresh = true) {
    if (
        !meetingActive ||
        recognitionRunning ||
        whisperIsProcessing
    ) {
        return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
        updateVoiceStatus("Microphone unavailable");
        updateTurnStatus(
            "Microphone unavailable",
            "Use Chrome and allow microphone access."
        );
        return;
    }

    try {
        if (fresh) clearManagerSpeechState();

        whisperStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });

        // The meeting might have ended while permission was requested.
        if (!meetingActive) {
            stopWhisperResources();
            return;
        }

        whisperChunks = [];
        whisperHasSpeech = false;
        whisperFinishRequested = false;
        whisperStartedAt = Date.now();

        const mimeType = [
            "audio/webm;codecs=opus",
            "audio/webm",
            "audio/ogg;codecs=opus"
        ].find(type => MediaRecorder.isTypeSupported(type));

        whisperRecorder = mimeType
            ? new MediaRecorder(whisperStream, { mimeType })
            : new MediaRecorder(whisperStream);

        whisperRecorder.ondataavailable = event => {
            if (event.data?.size > 0) {
                whisperChunks.push(event.data);
            }
        };

        whisperRecorder.onerror = event => {
            console.error("Recording error:", event.error);
            stopWhisperResources();
            recognitionRunning = false;
            updateRecognitionUI();
        };

        whisperRecorder.onstop = handleWhisperRecordingStopped;

        whisperAudioContext = new (
            window.AudioContext || window.webkitAudioContext
        )();

        whisperAnalyser = whisperAudioContext.createAnalyser();
        whisperAnalyser.fftSize = 2048;

        const source =
            whisperAudioContext.createMediaStreamSource(whisperStream);

        source.connect(whisperAnalyser);

        await whisperAudioContext.resume();

        whisperRecorder.start(250);
        recognitionRunning = true;
        recognitionShouldRun = true;
        managerIsSpeaking = false;

        whisperMaxTimer = setTimeout(() => {
            if (recognitionRunning) finishManagerTurn();
        }, CONFIG.MAX_RECORDING_MS);

        updateRecognitionUI();
        updateVoiceStatus("Listening");
        updateTurnStatus(
            "Listening",
            "Speak naturally. Pause when you finish your response."
        );

        monitorWhisperSilence();

    } catch (error) {
        console.error("Microphone startup error:", error);

        stopWhisperResources();
        recognitionRunning = false;
        recognitionShouldRun = false;

        updateRecognitionUI();
        updateVoiceStatus("Microphone permission required");
        updateTurnStatus(
            "Microphone access failed",
            "Allow microphone access in Chrome, then press Speak again."
        );
    }
}

function monitorWhisperSilence() {
    if (!recognitionRunning || !whisperAnalyser) return;

    const samples = new Uint8Array(whisperAnalyser.fftSize);
    whisperAnalyser.getByteTimeDomainData(samples);

    let sum = 0;

    for (const sample of samples) {
        const value = (sample - 128) / 128;
        sum += value * value;
    }

    const rms = Math.sqrt(sum / samples.length);

    if (rms > CONFIG.SPEECH_THRESHOLD) {
        whisperHasSpeech = true;
        managerIsSpeaking = true;

        clearTimeout(whisperSilenceTimer);

        updateVoiceStatus("Listening");
        updateTurnStatus(
            "You're speaking",
            "Rohit will respond after you finish."
        );

        whisperSilenceTimer = setTimeout(() => {
            if (recognitionRunning && whisperHasSpeech) {
                finishManagerTurn();
            }
        }, silenceDelay(managerInput?.value || ""));
    }

    whisperAnimationFrame =
        requestAnimationFrame(monitorWhisperSilence);
}

function finishManagerTurn() {
    if (!recognitionRunning || whisperFinishRequested) return;

    whisperFinishRequested = true;
    recognitionShouldRun = false;
    recognitionRunning = false;
    managerIsSpeaking = false;

    clearTimeout(whisperSilenceTimer);
    clearTimeout(whisperMaxTimer);

    if (whisperAnimationFrame !== null) {
        cancelAnimationFrame(whisperAnimationFrame);
        whisperAnimationFrame = null;
    }

    if (whisperRecorder && whisperRecorder.state !== "inactive") {
        whisperRecorder.stop();
    } else {
        stopWhisperResources();
        updateRecognitionUI();
    }

    updateRecognitionUI();

    if (whisperHasSpeech) {
        updateVoiceStatus("Transcribing...");
        updateTurnStatus(
            "Processing speech",
            "Whisper is converting your audio to text."
        );
    }
}

async function handleWhisperRecordingStopped() {
    const chunks = [...whisperChunks];
    const mimeType = whisperRecorder?.mimeType || "audio/webm";
    const elapsed = Date.now() - whisperStartedAt;
    const hasSpeech = whisperHasSpeech;

    stopWhisperResources();

    if (!hasSpeech || !chunks.length || elapsed < 300) {
        updateRecognitionUI();

        if (meetingActive) {
            updateVoiceStatus("Ready");
            updateTurnStatus(
                "No speech detected",
                "Press Speak and try again."
            );
        }

        return;
    }

    if (!meetingActive) return;

    const extension = mimeType.includes("ogg") ? "ogg" :
        mimeType.includes("mp4") ? "mp4" : "webm";

    const audioBlob = new Blob(chunks, { type: mimeType });

    whisperIsProcessing = true;
    updateRecognitionUI();
    updateVoiceStatus("Transcribing...");

    const session = meetingSessionId;

    try {
        const formData = new FormData();
        formData.append("audio", audioBlob, `recording.${extension}`);

        const response = await fetch("/api/transcribe", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || `Whisper request failed (${response.status}).`
            );
        }

        if (session !== meetingSessionId || !meetingActive) return;

        const text = normalizeSpeechText(data.text);

        if (!text) {
            updateVoiceStatus("No speech detected");
            updateTurnStatus(
                "No speech detected",
                "Try speaking a little longer."
            );
            return;
        }

        console.log("Whisper transcript:", text);

        // Release the Whisper processing lock before Rohit's response.
        // Otherwise, the next recording may be blocked.
        whisperIsProcessing = false;
        updateRecognitionUI();

        if (managerInput) {
            managerInput.value = "";
        }

        await sendManagerMessage(text);

    } catch (error) {
        console.error("Whisper transcription error:", error);

        updateVoiceStatus("Transcription failed");
        updateTurnStatus(
            "Could not transcribe audio",
            error.message
        );
    } finally {
        whisperIsProcessing = false;
        updateRecognitionUI();

        if (
            meetingActive &&
            !isGeneratingResponse &&
            !employeeSpeechStarted &&
            !recognitionRunning
        ) {
            updateVoiceStatus("Ready");
        }
    }
}

function stopRecognition() {
    recognitionShouldRun = false;
    recognitionRunning = false;
    managerIsSpeaking = false;

    clearTimeout(whisperSilenceTimer);
    clearTimeout(whisperMaxTimer);

    if (whisperAnimationFrame !== null) {
        cancelAnimationFrame(whisperAnimationFrame);
        whisperAnimationFrame = null;
    }

    // Discard recordings when deliberately stopping or ending the meeting.
    if (whisperRecorder && whisperRecorder.state !== "inactive") {
        whisperRecorder.onstop = null;

        try {
            whisperRecorder.stop();
        } catch (error) {
            console.warn("Recorder cleanup:", error);
        }
    }

    stopWhisperResources();
    updateRecognitionUI();
}

function stopWhisperResources() {
    clearTimeout(whisperSilenceTimer);
    clearTimeout(whisperMaxTimer);

    whisperSilenceTimer = null;
    whisperMaxTimer = null;

    if (whisperAnimationFrame !== null) {
        cancelAnimationFrame(whisperAnimationFrame);
        whisperAnimationFrame = null;
    }

    if (whisperStream) {
        whisperStream.getTracks().forEach(track => track.stop());
        whisperStream = null;
    }

    if (whisperAudioContext) {
        whisperAudioContext.close().catch(error =>
            console.warn("AudioContext cleanup:", error)
        );
        whisperAudioContext = null;
    }

    whisperAnalyser = null;
    whisperRecorder = null;
    whisperChunks = [];
    whisperHasSpeech = false;
}

function restartRecognitionFresh() {
    if (!meetingActive || employeeSpeechStarted) return;

    stopRecognition();
    startManagerListening(true);
}

// =========================================================
// ORPHEUS TEXT-TO-SPEECH
// =========================================================

// The Flask endpoint should return audio/wav bytes from Groq Orpheus.
// The backend manages the Groq API key and the selected voice.

function stopOrpheusAudio() {
    // Invalidate any pending TTS request or playback callbacks.
    currentAudioGenerationId++;

    if (currentAudio) {
        currentAudio.onended = null;
        currentAudio.onerror = null;
        currentAudio.ontimeupdate = null;

        currentAudio.pause();

        try {
            currentAudio.currentTime = 0;
        } catch (_) {
            // The audio may not have loaded yet.
        }

        currentAudio = null;
    }

    if (currentAudioUrl) {
        URL.revokeObjectURL(currentAudioUrl);
        currentAudioUrl = null;
    }
}

async function playOrpheusSpeech(text, options = {}) {
    const {
        onStarted = null,
        onProgress = null,
        onFinished = null,
        onError = null
    } = options;

    stopOrpheusAudio();

    const generationId = currentAudioGenerationId;
    const normalizedText = normalizeSpeechText(text);

    if (!normalizedText) {
        onFinished?.();
        return;
    }

    let audioUrl = null;
    let audio = null;
    let completed = false;
    let started = false;

    const finish = (error = null) => {
        if (completed) return;
        completed = true;

        if (generationId === currentAudioGenerationId) {
            if (currentAudio === audio) {
                currentAudio = null;
            }

            if (currentAudioUrl === audioUrl) {
                currentAudioUrl = null;
            }

            if (audio) {
                audio.onended = null;
                audio.onerror = null;
                audio.ontimeupdate = null;
            }

            if (audioUrl) {
                URL.revokeObjectURL(audioUrl);
            }
        } else if (audioUrl) {
            URL.revokeObjectURL(audioUrl);
        }

        if (error) {
            onError?.(error);
        }

        onFinished?.(error);
    };

    try {
        const response = await fetch(CONFIG.TTS_ENDPOINT, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            // The backend selects the configured Orpheus voice.
            body: JSON.stringify({ text: normalizedText })
        });

        if (generationId !== currentAudioGenerationId) return;

        if (!response.ok) {
            let message = `TTS request failed (${response.status}).`;

            try {
                const data = await response.json();
                message = data.error || message;
            } catch (_) {
                // Keep the HTTP status message if the response isn't JSON.
            }

            throw new Error(message);
        }

        const blob = await response.blob();

        if (generationId !== currentAudioGenerationId) return;

        if (!blob.size) {
            throw new Error("The TTS endpoint returned empty audio.");
        }

        audioUrl = URL.createObjectURL(blob);
        audio = new Audio(audioUrl);

        currentAudio = audio;
        currentAudioUrl = audioUrl;

        audio.preload = "auto";

        audio.ontimeupdate = () => {
            if (
                generationId !== currentAudioGenerationId ||
                !audio.duration ||
                !Number.isFinite(audio.duration)
            ) {
                return;
            }

            const progress = Math.min(
                1,
                Math.max(0, audio.currentTime / audio.duration)
            );

            onProgress?.(progress);
        };

        audio.onended = () => {
            if (generationId !== currentAudioGenerationId) return;
            finish();
        };

        audio.onerror = () => {
            if (generationId !== currentAudioGenerationId) return;
            finish(new Error("The generated audio could not be played."));
        };

        await audio.play();

        if (generationId !== currentAudioGenerationId) {
            audio.pause();
            return;
        }

        started = true;
        onStarted?.();

    } catch (error) {
        if (generationId !== currentAudioGenerationId) return;

        console.error("Orpheus TTS error:", error);

        if (audioUrl && currentAudioUrl !== audioUrl) {
            URL.revokeObjectURL(audioUrl);
        }

        finish(error);

        if (!started) {
            console.warn("Orpheus speech did not start.");
        }
    }
}

// =========================================================
// REHEARSAL CONTROLS
// =========================================================

function setupRehearsal() {
    sendButton?.addEventListener("click", () => {
        const message = managerInput?.value.trim();
        if (!message || !meetingActive || isGeneratingResponse) return;

        if (employeeSpeechStarted) {
            markRohitInterrupted();
            stopRohitSpeaking();
        }

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

    managerInput?.addEventListener("keydown", event => {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            sendButton?.click();
        }
    });
}

// =========================================================
// REHEARSAL MEMORY (server side, per meeting)
// =========================================================

function newMeetingId() {
    return (window.crypto && crypto.randomUUID)
        ? crypto.randomUUID()
        : `m-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// Tells the server to delete everything it remembers about this meeting.
// sendBeacon keeps working even while the tab is closing.
function endRehearsalMemory() {
    if (!meetingId) return;

    const payload = new Blob(
        [JSON.stringify({ session_id: meetingId })],
        { type: "application/json" }
    );

    try {
        navigator.sendBeacon(CONFIG.REHEARSE_END_ENDPOINT, payload);
    } catch (error) {
        console.warn("Could not clear rehearsal memory:", error);
    }

    meetingId = null;
}

// =========================================================
// CONVERSATION WITH ROHIT
// =========================================================

function cleanRohitResponse(text) {
    let response = normalizeSpeechText(text);
    if (!response) return "";

    response = response
        .replace(/^```(?:text)?/i, "")
        .replace(/```$/i, "")
        .trim();

    response = response.replace(/\[[^\]]*\]|\([^)]*\)/g, "").trim();

    const prefixes = [
        "rohit — simulated employee:",
        "simulated employee:",
        "employee:",
        "rohit:"
    ];

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

    if (!message || isGeneratingResponse || !meetingActive) return;

    const session = meetingSessionId;

    stopRohitSpeaking();
    isGeneratingResponse = true;

    updateTurnStatus("Rohit is thinking", "Preparing his response...");
    updateVoiceStatus("Thinking");

    if (sendButton) sendButton.disabled = true;
    if (micButton) micButton.disabled = true;

    const previousConversation = conversation.map(t => ({
        speaker: t.speaker,
        text: t.text
    }));

    conversation.push({ speaker: "manager", text: message });
    addTranscriptMessage("manager", message);

    // Clear the input so the previous message isn't reused.
    if (managerInput) {
        managerInput.value = "";
    }

    sendStartedAt = performance.now();

    try {
        const response = await fetch("/api/rehearse", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message,
                conversation: previousConversation,
                session_id: meetingId
            })
        });

        const data = await response.json();

        if (session !== meetingSessionId) return;

        if (!response.ok) {
            throw new Error(data.error || "Rehearsal request failed.");
        }

        const answer = cleanRohitResponse(data.response);

        if (!answer) {
            throw new Error("Rohit returned an empty response.");
        }

        llmFinishedAt = performance.now();

        const turn = { speaker: "rohit", text: answer };
        conversation.push(turn);

        const element = addTranscriptMessage("rohit", answer);

        await speakEmployeeResponse(answer, turn, element);

    } catch (error) {
        if (session !== meetingSessionId) return;

        console.error("Rehearsal error:", error);

        addTranscriptMessage("system", `Error: ${error.message}`);

        updateTurnStatus(
            "Something went wrong",
            "Check Flask, the API route, and the language model."
        );

        updateVoiceStatus("Error");
    } finally {
        if (session === meetingSessionId) {
            isGeneratingResponse = false;

            if (sendButton) sendButton.disabled = false;
            updateRecognitionUI();
        }
    }
}

// =========================================================
// ROHIT TEXT-TO-SPEECH — ORPHEUS
// =========================================================

function speakEmployeeResponse(text, turn, element) {
    const generationId = ++speechGenerationId;

    currentRohit = {
        turn,
        el: element,
        full: text
    };

    spokenIndex = 0;
    employeeSpeechStarted = false;

    return playOrpheusSpeech(text, {
        onStarted: () => {
            if (generationId !== speechGenerationId) return;

            employeeSpeechStarted = true;

            const total = Math.round(
                performance.now() -
                (sendStartedAt || performance.now())
            );

            const model = Math.round(
                (llmFinishedAt || performance.now()) -
                (sendStartedAt || performance.now())
            );

            if (timeToFirstSound) {
                timeToFirstSound.textContent =
                    `${total} ms (model ${model} ms)`;
            }

            updateTurnStatus(
                "Rohit is speaking (simulated)",
                "Wait until he finishes, then speak."
            );

            updateVoiceStatus("Rohit speaking");

            liveMeetingCard?.classList.add("rohit-speaking");
            liveMeetingCard?.classList.remove("interruption-active");
        },

        onProgress: progress => {
            if (generationId !== speechGenerationId) return;

            spokenIndex = Math.min(
                text.length,
                Math.floor(text.length * progress)
            );
        },

        onError: error => {
            console.error("Rohit TTS failed:", error);

            if (generationId === speechGenerationId) {
                updateTurnStatus(
                    "Speech playback failed",
                    error.message || "Check the Flask /api/tts route."
                );

                updateVoiceStatus("Error");
            }
        },

        onFinished: error => {
            if (generationId !== speechGenerationId) return;

            employeeSpeechStarted = false;
            currentRohit = null;

            liveMeetingCard?.classList.remove("rohit-speaking");

            if (!error && meetingActive) {
                updateTurnStatus(
                    "Your turn",
                    "Speak naturally. Rohit is listening."
                );

                updateVoiceStatus("Ready");
            }

            if (meetingActive) {
                startManagerListening(true);
            }
        }
    });
}

function markRohitInterrupted() {
    if (!currentRohit) return;

    const { turn, el, full } = currentRohit;

    if (spokenIndex >= full.length - 1) return;

    const heard = full.slice(0, spokenIndex).trim();
    const marked = heard
        ? `${heard} — [interrupted]`
        : "[interrupted]";

    turn.text = marked;

    if (el) el.textContent = marked;
}

function stopRohitSpeaking() {
    speechGenerationId++;
    employeeSpeechStarted = false;

    stopOrpheusAudio();

    currentRohit = null;
    spokenIndex = 0;

    liveMeetingCard?.classList.remove("rohit-speaking");
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

    meetingSessionId++;
    debriefRequestId++;

    // Clear any leftover memory, then start a fresh one for this meeting.
    endRehearsalMemory();
    meetingId = newMeetingId();

    meetingActive = true;
    isGeneratingResponse = false;
    conversation = [];
    currentRohit = null;

    stopRohitSpeaking();
    stopRecognition();
    clearManagerSpeechState();

    if (transcript) transcript.innerHTML = "";

    if (debriefTranscript) {
        debriefTranscript.textContent = "Rehearsal in progress.";
    }

    if (debriefResponse) {
        debriefResponse.textContent = "";
        debriefResponse.style.display = "none";
    }

    if (timeToFirstSound) timeToFirstSound.textContent = "—";
    if (managerInput) managerInput.value = "";

    if (startMeetingButton) startMeetingButton.disabled = true;
    if (endMeetingButton) endMeetingButton.disabled = false;
    if (sendButton) sendButton.disabled = false;
    if (micButton) micButton.disabled = false;

    liveMeetingCard?.classList.add("meeting-active");
    liveMeetingCard?.classList.remove(
        "rohit-speaking",
        "interruption-active"
    );

    showMode("rehearse");

    updateTurnStatus(
        "Meeting started",
        "You have the floor. Start the conversation."
    );

    updateVoiceStatus("Ready");
    updateRecognitionUI();

    speakMeetingAnnouncement();
}

function speakMeetingAnnouncement() {
    const announcement =
        "Coach here. The rehearsal has started. " +
        "Rohit is simulated. You can begin when you're ready.";

    playOrpheusSpeech(announcement, {
        onError: error => {
            console.error("Meeting announcement TTS failed:", error);
            updateVoiceStatus("Error");
        },

        onFinished: () => {
            if (meetingActive) {
                startManagerListening(true);
            }
        }
    });
}

function speakCoach(text) {
    playOrpheusSpeech(text, {
        onError: error => {
            console.error("Coach TTS failed:", error);
        }
    });
}

function endMeeting() {
    if (!meetingActive) {
        showMode("debrief");
        return;
    }

    meetingSessionId++;
    meetingActive = false;
    isGeneratingResponse = false;

    // The meeting is over: delete the server-side memory for it.
    endRehearsalMemory();

    markRohitInterrupted();
    stopRohitSpeaking();
    stopRecognition();
    clearManagerSpeechState();

    if (startMeetingButton) startMeetingButton.disabled = false;
    if (endMeetingButton) endMeetingButton.disabled = true;
    if (sendButton) sendButton.disabled = false;
    if (micButton) micButton.disabled = false;

    liveMeetingCard?.classList.remove(
        "meeting-active",
        "rohit-speaking",
        "interruption-active"
    );

    updateTurnStatus("Meeting ended", "Generating your debrief...");
    updateVoiceStatus("Ready");

    speakCoach(
        "Rehearsal over. Rohit has left. Here is your debrief."
    );

    if (debriefResponse) {
        debriefResponse.textContent = "";
        debriefResponse.style.display = "none";
    }

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
    const snapshot = conversation.map(t => ({
        speaker: t.speaker,
        text: t.text
    }));

    if (!snapshot.length) {
        showDebriefMessage(
            "No rehearsal conversation was recorded. " +
            "Complete a rehearsal before generating a debrief."
        );
        return;
    }

    const managerTurns = snapshot.filter(t =>
        t.speaker === "manager" && String(t.text || "").trim()
    );

    if (!managerTurns.length) {
        showDebriefMessage(
            "No manager speech was recorded. " +
            "Complete a rehearsal before generating a debrief."
        );
        return;
    }

    const requestId = ++debriefRequestId;

    if (debriefButton) debriefButton.disabled = true;

    updateDebriefTranscript();

    showDebriefMessage(
        `Generating debrief for this rehearsal ` +
        `(${managerTurns.length} manager turn(s))...`
    );

    try {
        const response = await fetch("/api/debrief", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ conversation: snapshot })
        });

        const data = await response.json();

        if (requestId !== debriefRequestId) return;

        if (!response.ok) {
            throw new Error(data.error || "Debrief request failed.");
        }

        showDebriefMessage(
            data.response || "No debrief response returned."
        );

    } catch (error) {
        if (requestId !== debriefRequestId) return;

        console.error("Debrief error:", error);
        showDebriefMessage(`Error: ${error.message}`);

    } finally {
        if (requestId === debriefRequestId && debriefButton) {
            debriefButton.disabled = false;
        }
    }
}

const DEBRIEF_HEADINGS =
    /^(READINESS CALL|GOOD MOMENT|MOMENT TO IMPROVE|USABLE OPENING LINE|LIKELY OBJECTION \d|COACHING SUMMARY)\s*:?$/i;

function showDebriefMessage(message) {
    if (!debriefResponse) return;

    debriefResponse.style.display = "block";
    debriefResponse.innerHTML = "";

    let afterReadiness = false;

    String(message).split("\n").forEach(raw => {
        const line = raw.trim().replace(/^\*+|\*+$/g, "").trim();

        if (!line) return;

        const element = document.createElement("div");

        if (DEBRIEF_HEADINGS.test(line)) {
            element.className = "debrief-heading";
            element.textContent = line.replace(/:$/, "");
            afterReadiness = /^READINESS CALL/i.test(line);
        } else {
            element.className =
                "debrief-line" + (afterReadiness ? " readiness" : "");

            element.textContent = raw.trim();
            afterReadiness = false;
        }

        debriefResponse.appendChild(element);
    });
}

function updateDebriefTranscript() {
    if (!debriefTranscript) return;

    const lines = conversation
        .filter(t => t && t.text && String(t.text).trim())
        .map(t => {
            const speaker =
                t.speaker === "manager" ? "YOU — MANAGER" :
                t.speaker === "rohit" ? "ROHIT — SIMULATED EMPLOYEE" :
                "SYSTEM";

            return `${speaker}: ${t.text}`;
        });

    debriefTranscript.textContent = lines.length
        ? lines.join("\n\n")
        : "No rehearsal conversation recorded.";
}

// =========================================================
// TRANSCRIPT
// =========================================================

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
        speaker === "manager" ? "You — Manager" :
        speaker === "rohit" ? "Rohit — Simulated Employee" :
        "System";

    const body = document.createElement("div");
    body.className = "transcript-text";
    body.textContent = text;

    message.append(label, body);
    entry.appendChild(message);
    transcript.appendChild(entry);

    transcript.scrollTop = transcript.scrollHeight;

    return body;
}

// =========================================================
// STATUS AND UI
// =========================================================

function updateTurnStatus(title, description) {
    if (turnStatus) turnStatus.textContent = title;
    if (turnDescription) turnDescription.textContent = description;
}

function updateVoiceStatus(status) {
    if (voiceStatus) voiceStatus.textContent = status;
    if (!voiceStatusDot) return;

    voiceStatusDot.classList.remove(
        "status-listening",
        "status-speaking",
        "status-thinking",
        "status-error"
    );

    if (status === "Listening") {
        voiceStatusDot.classList.add("status-listening");
    }

    if (status === "Rohit speaking") {
        voiceStatusDot.classList.add("status-speaking");
    }

    if (status === "Thinking") {
        voiceStatusDot.classList.add("status-thinking");
    }

    if (["Error", "Voice unavailable",
         "Microphone permission required"].includes(status)) {
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

    micButton.disabled =
        !meetingActive || whisperIsProcessing || isGeneratingResponse;

    micButton.classList.toggle("listening", recognitionRunning);

    micButton.textContent = whisperIsProcessing
        ? "Transcribing..."
        : recognitionRunning
            ? "■ Finish speaking"
            : "🎙 Speak";
}

// =========================================================
// CLEANUP
// =========================================================

document.addEventListener("keydown", event => {
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

    // Closing or reloading the tab ends the meeting: delete its memory.
    endRehearsalMemory();

    stopRohitSpeaking();
    stopRecognition();
});