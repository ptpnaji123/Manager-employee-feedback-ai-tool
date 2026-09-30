// =========================================================
// MANAGER FEEDBACK COACH
// Main application JavaScript
// =========================================================


// =========================================================
// GLOBAL STATE
// =========================================================

let conversation = [];

let currentMode = "prepare";

let meetingActive = false;
let isGeneratingResponse = false;

// Speech recognition
let recognition = null;
let recognitionSupported = false;
let recognitionRunning = false;
let recognitionShouldRun = false;

let recognitionSessionId = 0;
let activeRecognitionSession = 0;

let recognitionFinalText = "";
let recognitionInterimText = "";

let currentManagerSpeech = "";
let interimManagerSpeech = "";

let managerIsSpeaking = false;

// Employee speech / interruption
let employeeSpeechStarted = false;
let interruptionDetected = false;

// Timers
let recognitionRestartTimer = null;
let silenceTimer = null;

// Timing
let meetingStartedAt = null;
let responseGenerationStartedAt = null;

// TTS generation guard
let speechGenerationId = 0;


// =========================================================
// DOM REFERENCES
// =========================================================

const contextScreen =
    document.getElementById("contextScreen");

const workspace =
    document.getElementById("workspace");


// ---------------------------------------------------------
// Context buttons
// ---------------------------------------------------------

const startPrepareButton =
    document.getElementById("startPrepare");

const startRehearseButton =
    document.getElementById("startRehearse");

const goToRehearseButton =
    document.getElementById("goToRehearse");


// ---------------------------------------------------------
// Panels
// ---------------------------------------------------------

const preparePanel =
    document.getElementById("preparePanel");

const rehearsePanel =
    document.getElementById("rehearsePanel");

const debriefPanel =
    document.getElementById("debriefPanel");


// ---------------------------------------------------------
// Workspace header
// ---------------------------------------------------------

const currentModeTitle =
    document.getElementById("currentModeTitle");

const currentModeDescription =
    document.getElementById("currentModeDescription");

const voiceStatusDot =
    document.getElementById("voiceStatusDot");

const voiceStatus =
    document.getElementById("voiceStatus");


// ---------------------------------------------------------
// Prepare
// ---------------------------------------------------------

const prepareInput =
    document.getElementById("prepareInput");

const prepareButton =
    document.getElementById("prepareButton");

const prepareResponse =
    document.getElementById("prepareResult");


// ---------------------------------------------------------
// Rehearsal
// ---------------------------------------------------------

const managerInput =
    document.getElementById("managerInput");

const sendButton =
    document.getElementById("sendButton");

const micButton =
    document.getElementById("micButton");

const transcript =
    document.getElementById("transcript");


// ---------------------------------------------------------
// Meeting controls
// ---------------------------------------------------------

const startMeetingButton =
    document.getElementById("startMeeting");

const endMeetingButton =
    document.getElementById("endMeeting");

const stopSpeakingButton =
    document.getElementById("stopSpeakingButton");

const finishRehearsalButton =
    document.getElementById("finishRehearsal");

const turnStatus =
    document.getElementById("turnStatus");

const turnDescription =
    document.getElementById("turnDescription");

const liveMeetingCard =
    document.getElementById("liveMeetingCard");

const timeToFirstSound =
    document.getElementById("timeToFirstSound");


// ---------------------------------------------------------
// Debrief
// ---------------------------------------------------------

const debriefButton =
    document.getElementById("debriefButton");

const debriefResponse =
    document.getElementById("debriefResult");

const debriefTranscript =
    document.getElementById("debriefTranscript");


// =========================================================
// INITIALIZATION
// =========================================================

document.addEventListener(
    "DOMContentLoaded",
    initializeApplication
);


function initializeApplication() {

    console.log(
        "Manager Feedback Coach initialized."
    );

    setupModeButtons();

    setupPrepare();

    setupRehearsal();

    setupMeetingControls();

    setupDebrief();

    setupSpeechRecognition();

    showContextScreen();

    updateWorkspaceHeader("prepare");

    updateRecognitionUI();

}


// =========================================================
// CONTEXT / WORKSPACE
// =========================================================

function showContextScreen() {

    currentMode = "prepare";

    if (contextScreen) {

        contextScreen.classList.remove("hidden");

        contextScreen.style.display = "block";

    }

    if (workspace) {

        workspace.classList.add("hidden");

        workspace.style.display = "none";

    }

}


// =========================================================
// START WORKSPACE
// =========================================================

function startWorkspace(mode) {

    console.log(
        "Starting workspace:",
        mode
    );

    currentMode = mode;

    if (contextScreen) {

        contextScreen.classList.add("hidden");

        contextScreen.style.display = "none";

    }

    if (workspace) {

        workspace.classList.remove("hidden");

        workspace.style.display = "block";

    }

    showMode(mode);

}


// =========================================================
// SHOW MODE
// =========================================================

function showMode(mode) {

    if (
        mode !== "prepare" &&
        mode !== "rehearse" &&
        mode !== "debrief"
    ) {

        mode = "prepare";

    }

    currentMode = mode;


    // -----------------------------------------------------
    // Prepare
    // -----------------------------------------------------

    if (preparePanel) {

        const visible =
            mode === "prepare";

        preparePanel.classList.toggle(
            "hidden",
            !visible
        );

        preparePanel.style.display =
            visible ? "block" : "none";

    }


    // -----------------------------------------------------
    // Rehearse
    // -----------------------------------------------------

    if (rehearsePanel) {

        const visible =
            mode === "rehearse";

        rehearsePanel.classList.toggle(
            "hidden",
            !visible
        );

        rehearsePanel.style.display =
            visible ? "block" : "none";

    }


    // -----------------------------------------------------
    // Debrief
    // -----------------------------------------------------

    if (debriefPanel) {

        const visible =
            mode === "debrief";

        debriefPanel.classList.toggle(
            "hidden",
            !visible
        );

        debriefPanel.style.display =
            visible ? "block" : "none";

    }


    // -----------------------------------------------------
    // Navigation buttons
    // -----------------------------------------------------

    document
        .querySelectorAll("[data-mode]")
        .forEach((button) => {

            button.classList.toggle(
                "active",
                button.dataset.mode === mode
            );

        });


    updateWorkspaceHeader(mode);


    if (mode === "debrief") {

        updateDebriefTranscript();

    }

}


// =========================================================
// WORKSPACE HEADER
// =========================================================

function updateWorkspaceHeader(mode) {

    if (
        !currentModeTitle ||
        !currentModeDescription
    ) {

        return;

    }


    if (mode === "prepare") {

        currentModeTitle.textContent =
            "Prepare";

        currentModeDescription.textContent =
            "Plan the conversation using Situation, Behaviour and Impact.";

    }


    if (mode === "rehearse") {

        currentModeTitle.textContent =
            "Rehearse";

        currentModeDescription.textContent =
            "Practise the conversation with Rohit using your voice.";

    }


    if (mode === "debrief") {

        currentModeTitle.textContent =
            "Debrief";

        currentModeDescription.textContent =
            "Review what actually happened in your rehearsal.";

    }

}


// =========================================================
// MODE BUTTONS
// =========================================================

function setupModeButtons() {

    if (startPrepareButton) {

        startPrepareButton.addEventListener(
            "click",
            () => {

                startWorkspace("prepare");

            }
        );

    }


    if (startRehearseButton) {

        startRehearseButton.addEventListener(
            "click",
            () => {

                startWorkspace("rehearse");

            }
        );

    }


    if (goToRehearseButton) {

        goToRehearseButton.addEventListener(
            "click",
            () => {

                startWorkspace("rehearse");

            }
        );

    }


    document
        .querySelectorAll("[data-mode]")
        .forEach((button) => {

            button.addEventListener(
                "click",
                () => {

                    const mode =
                        button.dataset.mode;


                    if (
                        meetingActive &&
                        mode !== "rehearse"
                    ) {

                        updateTurnStatus(
                            "Meeting still active",
                            "Finish the rehearsal before changing modes."
                        );

                        return;

                    }


                    showMode(mode);

                }
            );

        });

}


// =========================================================
// PREPARE
// =========================================================

function setupPrepare() {

    if (!prepareButton) {

        return;

    }


    prepareButton.addEventListener(
        "click",
        async () => {

            const message =
                prepareInput
                    ? prepareInput.value.trim()
                    : "";


            if (!message) {

                showPrepareMessage(
                    "Please describe what you want help with."
                );

                return;

            }


            prepareButton.disabled =
                true;


            showPrepareMessage(
                "Thinking..."
            );


            try {

                const response =
                    await fetch(
                        "/api/prepare",
                        {
                            method: "POST",

                            headers: {
                                "Content-Type":
                                    "application/json"
                            },

                            body: JSON.stringify({
                                message: message
                            })

                        }
                    );


                const data =
                    await response.json();


                if (!response.ok) {

                    throw new Error(
                        data.error ||
                        "Prepare request failed."
                    );

                }


                showPrepareMessage(
                    data.response ||
                    "No preparation response returned."
                );


            } catch (error) {

                console.error(
                    "Prepare error:",
                    error
                );


                showPrepareMessage(
                    `Error: ${error.message}`
                );


            } finally {

                prepareButton.disabled =
                    false;

            }

        }
    );

}


function showPrepareMessage(message) {

    if (!prepareResponse) {

        return;

    }

    prepareResponse.style.display =
        "block";

    prepareResponse.textContent =
        message;

}


// =========================================================
// SPEECH RECOGNITION SETUP
// =========================================================

function setupSpeechRecognition() {

    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;


    if (!SpeechRecognition) {

        console.warn(
            "Speech recognition is not supported by this browser."
        );

        recognitionSupported =
            false;

        if (micButton) {

            micButton.disabled =
                true;

            micButton.textContent =
                "Mic unavailable";

        }

        updateVoiceStatus(
            "Voice unavailable"
        );

        return;

    }


    recognitionSupported =
        true;


    if (micButton) {

        micButton.addEventListener(
            "click",
            toggleMicrophone
        );

    }


    console.log(
        "Speech recognition supported."
    );

}


// =========================================================
// MICROPHONE TOGGLE
// =========================================================

function toggleMicrophone() {

    if (!recognitionSupported) {

        return;

    }


    if (recognitionRunning) {

        stopRecognition();


        updateTurnStatus(
            "Microphone paused",
            "Press Speak to listen again."
        );


        updateVoiceStatus(
            "Ready"
        );


        return;

    }


    if (!meetingActive) {

        updateTurnStatus(
            "Start the meeting first",
            "Press Start Meeting before using the microphone."
        );

        return;

    }


    recognitionShouldRun =
        true;


    resetRecognitionBuffer();

    startRecognition();


    updateTurnStatus(
        "Listening",
        "Speak naturally."
    );


    updateVoiceStatus(
        "Listening"
    );

}


// =========================================================
// CREATE RECOGNITION INSTANCE
// =========================================================

function createRecognitionInstance() {

    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;


    if (!SpeechRecognition) {

        return null;

    }


    const instance =
        new SpeechRecognition();


    // IMPORTANT:
    // Short sessions prevent Chrome from returning
    // increasingly duplicated rolling transcripts.
    instance.continuous =
        false;

    instance.interimResults =
        true;

    instance.maxAlternatives =
        1;

    instance.lang =
        "en-IN";


    const sessionId =
        ++recognitionSessionId;


    activeRecognitionSession =
        sessionId;


    instance.onstart =
        () => {

            if (
                sessionId !==
                activeRecognitionSession
            ) {

                return;

            }


            recognitionRunning =
                true;


            console.log(
                "Recognition started:",
                sessionId
            );


            updateRecognitionUI();

        };


    instance.onresult =
        (event) => {

            if (
                sessionId !==
                activeRecognitionSession
            ) {

                return;

            }


            handleRecognitionResult(
                event
            );

        };


    instance.onerror =
        (event) => {

            if (
                sessionId !==
                activeRecognitionSession
            ) {

                return;

            }


            console.warn(
                "Speech recognition error:",
                event.error
            );


            recognitionRunning =
                false;


            updateRecognitionUI();


            if (
                event.error === "not-allowed" ||
                event.error === "service-not-allowed"
            ) {

                recognitionShouldRun =
                    false;


                updateVoiceStatus(
                    "Microphone permission required"
                );


                updateTurnStatus(
                    "Microphone permission required",
                    "Allow microphone access in your browser."
                );


                return;

            }


            if (
                recognitionShouldRun
            ) {

                scheduleRecognitionRestart();

            }

        };


    instance.onend =
        () => {

            if (
                sessionId !==
                activeRecognitionSession
            ) {

                return;

            }


            recognitionRunning =
                false;


            updateRecognitionUI();


            /*
             * If the session ended naturally,
             * create a completely new session.
             */
            if (
                recognitionShouldRun &&
                meetingActive
            ) {

                scheduleRecognitionRestart();

            }

        };


    return instance;

}


// =========================================================
// START RECOGNITION
// =========================================================

function startRecognition() {

    if (!recognitionSupported) {

        return;

    }


    if (!recognitionShouldRun) {

        return;

    }


    if (!meetingActive) {

        return;

    }


    if (recognitionRunning) {

        return;

    }


    if (recognitionRestartTimer) {

        clearTimeout(
            recognitionRestartTimer
        );

        recognitionRestartTimer =
            null;

    }


    recognition =
        createRecognitionInstance();


    if (!recognition) {

        return;

    }


    try {

        recognition.start();

    } catch (error) {

        console.warn(
            "Recognition start error:",
            error.message
        );


        recognitionRunning =
            false;


        scheduleRecognitionRestart();

    }

}


// =========================================================
// STOP RECOGNITION
// =========================================================

function stopRecognition() {

    recognitionShouldRun =
        false;


    if (recognitionRestartTimer) {

        clearTimeout(
            recognitionRestartTimer
        );

        recognitionRestartTimer =
            null;

    }


    /*
     * Invalidate the current session first.
     *
     * This prevents late browser events from
     * entering the next manager turn.
     */
    activeRecognitionSession =
        ++recognitionSessionId;


    if (recognition) {

        try {

            recognition.stop();

        } catch (error) {

            console.warn(
                "Recognition stop error:",
                error.message
            );

        }

    }


    recognitionRunning =
        false;


    updateRecognitionUI();

}


// =========================================================
// RESTART RECOGNITION
// =========================================================

function scheduleRecognitionRestart() {

    if (!recognitionShouldRun) {

        return;

    }


    if (!meetingActive) {

        return;

    }


    if (recognitionRestartTimer) {

        return;

    }


    recognitionRestartTimer =
        setTimeout(
            () => {

                recognitionRestartTimer =
                    null;


                if (
                    !recognitionShouldRun ||
                    !meetingActive ||
                    recognitionRunning
                ) {

                    return;

                }


                startRecognition();

            },
            200
        );

}


// =========================================================
// RESET RECOGNITION BUFFER
// =========================================================

function resetRecognitionBuffer() {

    recognitionFinalText =
        "";

    recognitionInterimText =
        "";

    currentManagerSpeech =
        "";

    interimManagerSpeech =
        "";

}


// =========================================================
// NORMALIZE SPEECH TEXT
// =========================================================

function normalizeSpeechText(text) {

    return String(text || "")
        .replace(/\s+/g, " ")
        .trim();

}


// =========================================================
// MERGE TEXT WITHOUT DUPLICATION
// =========================================================

function mergeWithoutDuplication(
    existing,
    incoming
) {

    existing =
        normalizeSpeechText(existing);


    incoming =
        normalizeSpeechText(incoming);


    if (!existing) {

        return incoming;

    }


    if (!incoming) {

        return existing;

    }


    const existingLower =
        existing.toLowerCase();

    const incomingLower =
        incoming.toLowerCase();


    // Exact duplicate
    if (
        existingLower ===
        incomingLower
    ) {

        return existing;

    }


    // Incoming is already inside existing
    if (
        existingLower.includes(
            incomingLower
        )
    ) {

        return existing;

    }


    // Existing is already inside incoming
    if (
        incomingLower.includes(
            existingLower
        )
    ) {

        return incoming;

    }


    /*
     * Find overlap between the end of existing
     * and beginning of incoming.
     */
    const existingWords =
        existing.split(/\s+/);

    const incomingWords =
        incoming.split(/\s+/);


    const maxOverlap =
        Math.min(
            existingWords.length,
            incomingWords.length
        );


    for (
        let size = maxOverlap;
        size >= 1;
        size--
    ) {

        const existingEnd =
            existingWords
                .slice(
                    existingWords.length - size
                )
                .join(" ")
                .toLowerCase();


        const incomingStart =
            incomingWords
                .slice(
                    0,
                    size
                )
                .join(" ")
                .toLowerCase();


        if (
            existingEnd ===
            incomingStart
        ) {

            const remaining =
                incomingWords
                    .slice(size)
                    .join(" ");


            if (!remaining) {

                return existing;

            }


            return normalizeSpeechText(
                `${existing} ${remaining}`
            );

        }

    }


    return normalizeSpeechText(
        `${existing} ${incoming}`
    );

}


// =========================================================
// CHECK CONTAINMENT
// =========================================================

function isAlreadyContained(
    text,
    existing
) {

    text =
        normalizeSpeechText(text);

    existing =
        normalizeSpeechText(existing);


    if (
        !text ||
        !existing
    ) {

        return false;

    }


    const textLower =
        text.toLowerCase();

    const existingLower =
        existing.toLowerCase();


    return (
        existingLower.includes(textLower) ||
        textLower.includes(existingLower)
    );

}


// =========================================================
// HANDLE SPEECH RECOGNITION RESULT
// =========================================================

function handleRecognitionResult(event) {

    if (!event.results) {

        return;

    }


    /*
     * With continuous=false, each recognition instance
     * is intentionally short.
     *
     * We process final results separately from interim
     * results.
     */
    let finalText = "";

    let interimText = "";


    for (
        let i = 0;
        i < event.results.length;
        i++
    ) {

        const result =
            event.results[i];


        if (
            !result ||
            !result[0]
        ) {

            continue;

        }


        const text =
            normalizeSpeechText(
                result[0].transcript
            );


        if (!text) {

            continue;

        }


        if (result.isFinal) {

            finalText =
                mergeWithoutDuplication(
                    finalText,
                    text
                );

        } else {

            interimText =
                mergeWithoutDuplication(
                    interimText,
                    text
                );

        }

    }


    finalText =
        normalizeSpeechText(
            finalText
        );


    interimText =
        normalizeSpeechText(
            interimText
        );


    /*
     * -----------------------------------------------------
     * BARGE-IN
     * -----------------------------------------------------
     */

    if (
        employeeSpeechStarted &&
        (
            finalText ||
            interimText
        )
    ) {

        handleManagerInterruption();

    }


    /*
     * -----------------------------------------------------
     * FINAL SPEECH
     * -----------------------------------------------------
     */

    if (finalText) {

        managerIsSpeaking =
            true;


        /*
         * Add final speech exactly once.
         */
        recognitionFinalText =
            mergeWithoutDuplication(
                recognitionFinalText,
                finalText
            );


        currentManagerSpeech =
            normalizeSpeechText(
                recognitionFinalText
            );


        recognitionInterimText =
            "";

        interimManagerSpeech =
            "";


        updateManagerInput(
            currentManagerSpeech
        );


        updateTurnStatus(
            "You're speaking",
            "Rohit is listening."
        );


        updateVoiceStatus(
            "Listening"
        );


        resetManagerSilenceTimer();

    }


    /*
     * -----------------------------------------------------
     * INTERIM SPEECH
     * -----------------------------------------------------
     */

    if (interimText) {

        managerIsSpeaking =
            true;


        recognitionInterimText =
            interimText;


        interimManagerSpeech =
            interimText;


        updateManagerInput(
            combineFinalAndInterimSpeech()
        );


        updateTurnStatus(
            "You're speaking",
            "Rohit is listening."
        );


        updateVoiceStatus(
            "Listening"
        );


        resetManagerSilenceTimer();

    }

}


// =========================================================
// COMBINE FINAL + INTERIM
// =========================================================

function combineFinalAndInterimSpeech() {

    const finalText =
        normalizeSpeechText(
            recognitionFinalText
        );


    const interimText =
        normalizeSpeechText(
            recognitionInterimText
        );


    if (!finalText) {

        return interimText;

    }


    if (!interimText) {

        return finalText;

    }


    /*
     * Do not duplicate interim text when Chrome has
     * already included it in the final result.
     */
    if (
        isAlreadyContained(
            interimText,
            finalText
        )
    ) {

        return (
            interimText.length >
            finalText.length
        )
            ? interimText
            : finalText;

    }


    return mergeWithoutDuplication(
        finalText,
        interimText
    );

}


// =========================================================
// MANAGER INTERRUPTION / BARGE-IN
// =========================================================

function handleManagerInterruption() {

    if (!employeeSpeechStarted) {

        return;

    }


    console.log(
        "BARGE-IN: Manager started speaking."
    );


    interruptionDetected =
        true;


    speechGenerationId++;


    if (
        "speechSynthesis" in window
    ) {

        window.speechSynthesis.cancel();

    }


    employeeSpeechStarted =
        false;


    if (liveMeetingCard) {

        liveMeetingCard.classList.remove(
            "rohit-speaking"
        );

        liveMeetingCard.classList.add(
            "interruption-active"
        );

    }


    updateTurnStatus(
        "You interrupted Rohit",
        "His voice has stopped. Finish what you want to say."
    );


    updateVoiceStatus(
        "Listening"
    );

}


// =========================================================
// BUILD CURRENT MANAGER SPEECH
// =========================================================

function buildCurrentManagerSpeech() {

    const finalText =
        normalizeSpeechText(
            recognitionFinalText
        );


    const interimText =
        normalizeSpeechText(
            recognitionInterimText
        );


    if (!finalText) {

        return interimText;

    }


    if (!interimText) {

        return finalText;

    }


    return combineFinalAndInterimSpeech();

}


// =========================================================
// UPDATE MANAGER INPUT
// =========================================================

function updateManagerInput(text) {

    if (!managerInput) {

        return;

    }


    managerInput.value =
        text;


    managerInput.scrollTop =
        managerInput.scrollHeight;

}


// =========================================================
// SILENCE TIMER
// =========================================================

function resetManagerSilenceTimer() {

    if (silenceTimer) {

        clearTimeout(
            silenceTimer
        );

    }


    silenceTimer =
        setTimeout(
            () => {

                if (
                    managerIsSpeaking &&
                    !employeeSpeechStarted &&
                    !isGeneratingResponse &&
                    meetingActive
                ) {

                    finishManagerTurn();

                }

            },
            1200
        );

}


// =========================================================
// FINISH MANAGER TURN
// =========================================================

function finishManagerTurn() {

    if (
        isGeneratingResponse
    ) {

        return;

    }


    const message =
        normalizeSpeechText(
            buildCurrentManagerSpeech()
        );


    if (!message) {

        return;

    }


    console.log(
        "FINAL MANAGER TURN:",
        message
    );


    /*
     * IMPORTANT:
     *
     * Stop recognition BEFORE sending the message.
     *
     * This prevents late Chrome recognition events from
     * modifying the message while the backend is processing.
     */
    stopRecognition();


    clearManagerSpeechState();


    sendManagerMessage(
        message
    );

}


// =========================================================
// REHEARSAL SETUP
// =========================================================

function setupRehearsal() {


    // -----------------------------------------------------
    // Typed send
    // -----------------------------------------------------

    if (sendButton) {

        sendButton.addEventListener(
            "click",
            () => {

                const message =
                    managerInput
                        ? managerInput.value.trim()
                        : "";


                if (!message) {

                    return;

                }


                if (
                    employeeSpeechStarted
                ) {

                    handleManagerInterruption();

                }


                stopRecognition();

                clearManagerSpeechState();


                sendManagerMessage(
                    message
                );

            }
        );

    }


    // -----------------------------------------------------
    // Stop Rohit
    // -----------------------------------------------------

    if (stopSpeakingButton) {

        stopSpeakingButton.addEventListener(
            "click",
            () => {

                stopRohitSpeaking();


                updateTurnStatus(
                    "Rohit stopped",
                    "You can speak now."
                );


                updateVoiceStatus(
                    "Listening"
                );


                if (meetingActive) {

                    startManagerListening();

                }

            }
        );

    }


    // -----------------------------------------------------
    // Finish rehearsal
    // -----------------------------------------------------

    if (finishRehearsalButton) {

        finishRehearsalButton.addEventListener(
            "click",
            () => {

                endMeeting();

            }
        );

    }


    // -----------------------------------------------------
    // Ctrl + Enter
    // -----------------------------------------------------

    if (managerInput) {

        managerInput.addEventListener(
            "keydown",
            (event) => {

                if (
                    event.key === "Enter" &&
                    event.ctrlKey
                ) {

                    event.preventDefault();


                    if (sendButton) {

                        sendButton.click();

                    }

                }

            }
        );

    }

}


// =========================================================
// CLEAR MANAGER SPEECH STATE
// =========================================================

function clearManagerSpeechState() {

    currentManagerSpeech =
        "";

    interimManagerSpeech =
        "";

    recognitionFinalText =
        "";

    recognitionInterimText =
        "";

    managerIsSpeaking =
        false;


    if (silenceTimer) {

        clearTimeout(
            silenceTimer
        );

        silenceTimer =
            null;

    }


    updateManagerInput("");

}


// =========================================================
// CLEAN ROHIT RESPONSE
// =========================================================

function cleanRohitResponse(text) {

    let response =
        normalizeSpeechText(text);


    if (!response) {

        return "";

    }


    /*
     * Remove markdown fences.
     */
    response =
        response
            .replace(/^```(?:text)?/i, "")
            .replace(/```$/i, "")
            .trim();


    /*
     * Remove common LLM speaker prefixes.
     */
    const prefixes = [

        "ROHIT:",
        "Rohit:",
        "EMPLOYEE:",
        "Employee:",
        "SIMULATED EMPLOYEE:",
        "Simulated Employee:",
        "ROHIT — SIMULATED EMPLOYEE:",
        "Rohit — Simulated Employee:"

    ];


    let changed =
        true;


    while (changed) {

        changed =
            false;


        for (const prefix of prefixes) {

            if (
                response
                    .toLowerCase()
                    .startsWith(
                        prefix.toLowerCase()
                    )
            ) {

                response =
                    response
                        .slice(prefix.length)
                        .trim();


                changed =
                    true;

            }

        }

    }


    /*
     * Remove surrounding quotation marks.
     */
    if (
        response.length >= 2 &&
        (
            (
                response.startsWith('"') &&
                response.endsWith('"')
            ) ||
            (
                response.startsWith("'") &&
                response.endsWith("'")
            )
        )
    ) {

        response =
            response.slice(
                1,
                -1
            ).trim();

    }


    return response;

}


// =========================================================
// SEND MANAGER MESSAGE
// =========================================================

async function sendManagerMessage(message) {

    message =
        normalizeSpeechText(
            message
        );


    if (!message) {

        return;

    }


    if (isGeneratingResponse) {

        return;

    }


    stopRohitSpeaking();


    managerIsSpeaking =
        false;


    updateTurnStatus(
        "Rohit is thinking",
        "Preparing his response..."
    );


    updateVoiceStatus(
        "Thinking"
    );


    isGeneratingResponse =
        true;


    if (sendButton) {

        sendButton.disabled =
            true;

    }


    if (micButton) {

        micButton.disabled =
            true;

    }


    /*
     * Only send completed previous turns to backend.
     */
    const previousConversation =
        conversation.map(
            (turn) => ({

                speaker:
                    turn.speaker,

                text:
                    turn.text

            })
        );


    /*
     * Add manager message to visible transcript
     * exactly once.
     */
    addTranscriptMessage(
        "manager",
        message
    );


    responseGenerationStartedAt =
        performance.now();


    try {

        const response =
            await fetch(
                "/api/rehearse",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        message:
                            message,

                        conversation:
                            previousConversation

                    })

                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.error ||
                "Rehearsal request failed."
            );

        }


        const rohitResponse =
            cleanRohitResponse(
                data.response
            );


        if (!rohitResponse) {

            throw new Error(
                "Rohit returned an empty response."
            );

        }


        /*
         * Save conversation.
         */
        conversation.push({

            speaker:
                "manager",

            text:
                message

        });


        conversation.push({

            speaker:
                "rohit",

            text:
                rohitResponse

        });


        /*
         * Display Rohit's response.
         */
        addTranscriptMessage(
            "rohit",
            rohitResponse
        );


        /*
         * Speak response.
         */
        speakEmployeeResponse(
            rohitResponse
        );


    } catch (error) {

        console.error(
            "Rehearsal error:",
            error
        );


        addTranscriptMessage(
            "system",
            `Error: ${error.message}`
        );


        updateTurnStatus(
            "Something went wrong",
            "Check that Flask and Ollama are running."
        );


        updateVoiceStatus(
            "Error"
        );


    } finally {

        isGeneratingResponse =
            false;


        if (sendButton) {

            sendButton.disabled =
                false;

        }


        if (micButton) {

            micButton.disabled =
                false;

        }

    }

}


// =========================================================
// ROHIT TEXT-TO-SPEECH
// =========================================================

function speakEmployeeResponse(text) {

    if (
        !("speechSynthesis" in window)
    ) {

        updateTurnStatus(
            "Rohit responded",
            "Browser speech synthesis is unavailable."
        );


        updateVoiceStatus(
            "Voice unavailable"
        );


        if (meetingActive) {

            startManagerListening();

        }


        return;

    }


    window.speechSynthesis.cancel();


    const generationId =
        ++speechGenerationId;


    const utterance =
        new SpeechSynthesisUtterance(
            text
        );


    utterance.lang =
        "en-IN";


    utterance.rate =
        0.96;


    utterance.pitch =
        0.92;


    utterance.volume =
        1.0;


    utterance.onstart =
        () => {

            if (
                generationId !==
                speechGenerationId
            ) {

                return;

            }


            employeeSpeechStarted =
                true;


            const elapsed =
                performance.now() -
                (
                    responseGenerationStartedAt ||
                    performance.now()
                );


            if (timeToFirstSound) {

                timeToFirstSound.textContent =
                    `${Math.round(elapsed)} ms`;

            }


            updateTurnStatus(
                "Rohit is speaking",
                "You can interrupt him at any time."
            );


            updateVoiceStatus(
                "Rohit speaking"
            );


            if (liveMeetingCard) {

                liveMeetingCard.classList.add(
                    "rohit-speaking"
                );

                liveMeetingCard.classList.remove(
                    "interruption-active"
                );

            }


            /*
             * Keep microphone recognition running
             * during Rohit's speech so interruption
             * can be detected.
             */
            if (meetingActive) {

                recognitionShouldRun =
                    true;

                startRecognition();

            }

        };


    utterance.onend =
        () => {

            if (
                generationId !==
                speechGenerationId
            ) {

                return;

            }


            employeeSpeechStarted =
                false;


            if (liveMeetingCard) {

                liveMeetingCard.classList.remove(
                    "rohit-speaking"
                );

            }


            if (meetingActive) {

                startManagerListening();

            } else {

                updateTurnStatus(
                    "Response complete",
                    "Start the meeting to continue."
                );


                updateVoiceStatus(
                    "Ready"
                );

            }

        };


    utterance.onerror =
        (event) => {

            if (
                event.error === "canceled" ||
                event.error === "interrupted"
            ) {

                return;

            }


            console.warn(
                "Speech synthesis error:",
                event.error
            );


            employeeSpeechStarted =
                false;


            if (liveMeetingCard) {

                liveMeetingCard.classList.remove(
                    "rohit-speaking"
                );

            }


            if (meetingActive) {

                startManagerListening();

            }

        };


    window.speechSynthesis.speak(
        utterance
    );

}


// =========================================================
// STOP ROHIT SPEAKING
// =========================================================

function stopRohitSpeaking() {

    speechGenerationId++;


    employeeSpeechStarted =
        false;


    if (
        "speechSynthesis" in window
    ) {

        window.speechSynthesis.cancel();

    }


    if (liveMeetingCard) {

        liveMeetingCard.classList.remove(
            "rohit-speaking"
        );

    }

}


// =========================================================
// MEETING CONTROLS
// =========================================================

function setupMeetingControls() {

    if (startMeetingButton) {

        startMeetingButton.addEventListener(
            "click",
            startMeeting
        );

    }


    if (endMeetingButton) {

        endMeetingButton.addEventListener(
            "click",
            endMeeting
        );

    }

}


// =========================================================
// START MEETING
// =========================================================

function startMeeting() {

    if (meetingActive) {

        return;

    }


    console.log(
        "Starting rehearsal meeting."
    );


    meetingActive =
        true;


    conversation =
        [];


    stopRohitSpeaking();

    stopRecognition();

    clearManagerSpeechState();


    interruptionDetected =
        false;


    meetingStartedAt =
        performance.now();


    if (transcript) {

        transcript.innerHTML =
            "";

    }


    if (debriefTranscript) {

        debriefTranscript.textContent =
            "Rehearsal in progress.";

    }


    if (debriefResponse) {

        debriefResponse.textContent =
            "";

    }


    if (timeToFirstSound) {

        timeToFirstSound.textContent =
            "—";

    }


    if (managerInput) {

        managerInput.value =
            "";

    }


    if (startMeetingButton) {

        startMeetingButton.disabled =
            true;

    }


    if (endMeetingButton) {

        endMeetingButton.disabled =
            false;

    }


    if (liveMeetingCard) {

        liveMeetingCard.classList.add(
            "meeting-active"
        );

    }


    updateTurnStatus(
        "Meeting started",
        "You have the floor. Start the conversation."
    );


    updateVoiceStatus(
        "Listening"
    );


    /*
     * Enable recognition.
     */
    recognitionShouldRun =
        true;


    resetRecognitionBuffer();


    /*
     * The announcement speaks first.
     * Recognition starts after the announcement.
     */
    speakMeetingAnnouncement();

}


// =========================================================
// MEETING ANNOUNCEMENT
// =========================================================

function speakMeetingAnnouncement() {

    if (
        !("speechSynthesis" in window)
    ) {

        startManagerListening();

        return;

    }


    const utterance =
        new SpeechSynthesisUtterance(
            "The meeting has started. You can begin when you're ready."
        );


    utterance.lang =
        "en-IN";


    utterance.rate =
        0.98;


    utterance.onend =
        () => {

            if (meetingActive) {

                startManagerListening();

            }

        };


    window.speechSynthesis.cancel();


    window.speechSynthesis.speak(
        utterance
    );

}


// =========================================================
// START MANAGER LISTENING
// =========================================================

function startManagerListening() {

    if (!meetingActive) {

        return;

    }


    employeeSpeechStarted =
        false;


    recognitionShouldRun =
        true;


    updateTurnStatus(
        "Your turn",
        "Speak naturally. Rohit is listening."
    );


    updateVoiceStatus(
        "Listening"
    );


    startRecognition();

}


// =========================================================
// END MEETING
// =========================================================

function endMeeting() {

    if (!meetingActive) {

        showMode(
            "debrief"
        );

        return;

    }


    console.log(
        "Ending rehearsal meeting."
    );


    meetingActive =
        false;


    stopRohitSpeaking();

    stopRecognition();


    if (silenceTimer) {

        clearTimeout(
            silenceTimer
        );

        silenceTimer =
            null;

    }


    clearManagerSpeechState();


    if (startMeetingButton) {

        startMeetingButton.disabled =
            false;

    }


    if (endMeetingButton) {

        endMeetingButton.disabled =
            true;

    }


    if (liveMeetingCard) {

        liveMeetingCard.classList.remove(
            "meeting-active",
            "rohit-speaking",
            "interruption-active"
        );

    }


    updateTurnStatus(
        "Meeting ended",
        "Review the rehearsal and generate the debrief."
    );


    updateVoiceStatus(
        "Ready"
    );


    updateDebriefTranscript();


    showMode(
        "debrief"
    );

}


// =========================================================
// DEBRIEF SETUP
// =========================================================

function setupDebrief() {

    if (!debriefButton) {

        return;

    }


    debriefButton.addEventListener(
        "click",
        generateDebrief
    );

}


// =========================================================
// GENERATE DEBRIEF
// =========================================================

async function generateDebrief() {

    if (!conversation.length) {

        showDebriefMessage(
            "No rehearsal conversation was recorded. Complete a rehearsal before generating a debrief."
        );

        return;

    }


    const hasManagerTurn =
        conversation.some(
            (turn) =>
                turn.speaker === "manager" &&
                String(
                    turn.text || ""
                ).trim()
        );


    if (!hasManagerTurn) {

        showDebriefMessage(
            "No manager speech was recorded. Complete a rehearsal before generating a debrief."
        );

        return;

    }


    debriefButton.disabled =
        true;


    showDebriefMessage(
        "Generating debrief..."
    );


    updateDebriefTranscript();


    try {

        const response =
            await fetch(
                "/api/debrief",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        conversation:
                            conversation

                    })

                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.error ||
                "Debrief request failed."
            );

        }


        showDebriefMessage(
            data.response ||
            "No debrief response returned."
        );


    } catch (error) {

        console.error(
            "Debrief error:",
            error
        );


        showDebriefMessage(
            `Error: ${error.message}`
        );


    } finally {

        debriefButton.disabled =
            false;

    }

}


// =========================================================
// DEBRIEF RESULT DISPLAY
// =========================================================

function showDebriefMessage(message) {

    if (!debriefResponse) {

        return;

    }


    debriefResponse.style.display =
        "block";


    debriefResponse.textContent =
        message;

}


// =========================================================
// DEBRIEF TRANSCRIPT
// =========================================================

function updateDebriefTranscript() {

    if (!debriefTranscript) {

        return;

    }


    if (!conversation.length) {

        debriefTranscript.textContent =
            "No rehearsal conversation recorded.";

        return;

    }


    const lines =
        conversation
            .filter(
                (turn) =>
                    turn &&
                    turn.text &&
                    String(
                        turn.text
                    ).trim()
            )
            .map(
                (turn) => {

                    const speaker =
                        turn.speaker === "manager"
                            ? "YOU — MANAGER"
                            : turn.speaker === "rohit"
                                ? "ROHIT — SIMULATED EMPLOYEE"
                                : "SYSTEM";


                    return `${speaker}: ${turn.text}`;

                }
            );


    if (!lines.length) {

        debriefTranscript.textContent =
            "No rehearsal conversation recorded.";

        return;

    }


    debriefTranscript.textContent =
        lines.join("\n\n");

}


// =========================================================
// TRANSCRIPT
// =========================================================

function addTranscriptMessage(
    speaker,
    text
) {

    if (!transcript) {

        return;

    }


    text =
        normalizeSpeechText(text);


    if (!text) {

        return;

    }


    /*
     * Prevent exact duplicate messages.
     */
    const existingMessages =
        transcript.querySelectorAll(
            ".transcript-message"
        );


    for (
        let i = existingMessages.length - 1;
        i >= 0;
        i--
    ) {

        const existing =
            existingMessages[i];


        const existingSpeaker =
            existing.classList.contains(
                speaker
            );


        const existingBody =
            existing.querySelector(
                ".transcript-text"
            );


        if (
            existingSpeaker &&
            existingBody &&
            normalizeSpeechText(
                existingBody.textContent
            ) === text
        ) {

            return;

        }

    }


    const emptyTranscript =
        transcript.querySelector(
            ".empty-transcript"
        );


    if (emptyTranscript) {

        emptyTranscript.remove();

    }


    const message =
        document.createElement(
            "div"
        );


    message.className =
        `transcript-message ${speaker}`;


    const label =
        document.createElement(
            "div"
        );


    label.className =
        "transcript-speaker";


    if (speaker === "manager") {

        label.textContent =
            "You — Manager";

    } else if (
        speaker === "rohit"
    ) {

        label.textContent =
            "Rohit — Simulated Employee";

    } else {

        label.textContent =
            "System";

    }


    const body =
        document.createElement(
            "div"
        );


    body.className =
        "transcript-text";


    body.textContent =
        text;


    message.appendChild(
        label
    );


    message.appendChild(
        body
    );


    transcript.appendChild(
        message
    );


    transcript.scrollTop =
        transcript.scrollHeight;

}


// =========================================================
// TURN STATUS
// =========================================================

function updateTurnStatus(
    title,
    description
) {

    if (turnStatus) {

        turnStatus.textContent =
            title;

    }


    if (turnDescription) {

        turnDescription.textContent =
            description;

    }

}


// =========================================================
// VOICE STATUS
// =========================================================

function updateVoiceStatus(status) {

    if (voiceStatus) {

        voiceStatus.textContent =
            status;

    }


    if (!voiceStatusDot) {

        return;

    }


    voiceStatusDot.classList.remove(
        "status-listening",
        "status-speaking",
        "status-thinking",
        "status-error"
    );


    if (
        status === "Listening"
    ) {

        voiceStatusDot.classList.add(
            "status-listening"
        );

    }


    if (
        status === "Rohit speaking"
    ) {

        voiceStatusDot.classList.add(
            "status-speaking"
        );

    }


    if (
        status === "Thinking"
    ) {

        voiceStatusDot.classList.add(
            "status-thinking"
        );

    }


    if (
        status === "Error" ||
        status === "Voice unavailable" ||
        status === "Microphone permission required"
    ) {

        voiceStatusDot.classList.add(
            "status-error"
        );

    }

}


// =========================================================
// RECOGNITION UI
// =========================================================

function updateRecognitionUI() {

    if (!micButton) {

        return;

    }


    if (!recognitionSupported) {

        micButton.disabled =
            true;

        micButton.textContent =
            "Mic unavailable";

        return;

    }


    /*
     * Do not permanently disable the microphone
     * just because the backend is generating a response.
     */
    if (recognitionRunning) {

        micButton.classList.add(
            "listening"
        );

        micButton.textContent =
            "🎙 Listening";

    } else {

        micButton.classList.remove(
            "listening"
        );

        micButton.textContent =
            "🎙 Speak";

    }

}


// =========================================================
// KEYBOARD SHORTCUT
// =========================================================

document.addEventListener(
    "keydown",
    (event) => {

        if (
            event.key === "Escape" &&
            employeeSpeechStarted
        ) {

            stopRohitSpeaking();


            updateTurnStatus(
                "Rohit stopped",
                "You can speak now."
            );


            if (meetingActive) {

                startManagerListening();

            } else {

                updateVoiceStatus(
                    "Ready"
                );

            }

        }

    }
);


// =========================================================
// CLEANUP
// =========================================================

window.addEventListener(
    "beforeunload",
    () => {

        meetingActive =
            false;


        recognitionShouldRun =
            false;


        stopRohitSpeaking();

        stopRecognition();

    }
);