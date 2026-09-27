/* SpeakLoop frontend.
 * Concepts used (docs/01-concepts.md §2 & §7):
 * - MediaRecorder API: browser records mic -> webm/opus blob -> POST
 * - speechSynthesis: browser speaks the buddy's replies (free, offline)
 * - fetch + FormData for the multipart upload
 */
const $ = (id) => document.getElementById(id);
const chat = $("chat");

let sessionId = null;
let recording = false;
let recorder = null;
let audioChunks = [];
let ttsOn = true;
let busy = false;
let currentAudio = null;      // server-generated WAV (macOS `say` voice)
let lastMode = $("mode").value;

/* ---------- tiny helpers ---------- */
function scrollDown() { chat.scrollTop = chat.scrollHeight; }

function stopAudio() {
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
}

function clearChat() {
  chat.innerHTML = "";
  $("report").innerHTML = "<p style='color:var(--dim);font-size:13px'>Ends the session and shows feedback here.</p>";
  $("saved").textContent = "";
  $("qNow").textContent = "0"; $("turns").textContent = "0";
  $("fillerTotal").textContent = "0";
  $("fillers").textContent = "None yet — keep talking.";
}

function bubble(kind, text) {
  const div = document.createElement("div");
  div.className = "bubble " + kind;
  div.textContent = text;
  chat.appendChild(div);
  scrollDown();
  return div;
}

function quickNote(text) {
  if (!text) return;
  const div = document.createElement("div");
  div.className = "quick";
  div.textContent = "💡 " + text;
  chat.appendChild(div);
  scrollDown();
}

/* Coaching loop: buddy found a mistake and asked for another try. */
function correctionCard(text, attempt, max) {
  const div = document.createElement("div");
  div.className = "correction";
  div.innerHTML = `<b>📝 Say it like this:</b> `;
  div.appendChild(document.createTextNode(text));
  chat.appendChild(div);
  const chip = document.createElement("div");
  chip.className = "retrychip";
  chip.textContent = `🔁 Your turn — try again (attempt ${attempt + 1} of ${max})`;
  chat.appendChild(chip);
  scrollDown();
}

function showError(msg) { $("err").textContent = msg || ""; }

function speakReply(audioUrl, text) {
  if (!ttsOn) return;
  stopAudio();
  if (audioUrl) {                       // macOS `say` WAV — the good voice
    currentAudio = new Audio(audioUrl);
    currentAudio.play().catch(() => speakFallback(text));
  } else {
    speakFallback(text);
  }
}

function speakFallback(text) {          // browser voice (backup)
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.0;
  const voices = speechSynthesis.getVoices();
  const en = voices.find((v) => v.lang === "en-US") ||
             voices.find((v) => v.lang.startsWith("en"));
  if (en) u.voice = en;
  speechSynthesis.speak(u);
}

/* ---------- session lifecycle ---------- */
async function startSession() {
  $("gateErr").textContent = "";
  $("startBtn").disabled = true;
  clearChat();
  stopAudio();
  try {
    const r = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: $("mode").value, voice: $("voice").value }),
    });
    if (!r.ok) throw new Error("server said " + r.status);
    const data = await r.json();
    sessionId = data.session_id;
    lastMode = $("mode").value;
    $("qTot").textContent = data.total_questions || "–";
    bubble("system", "Session started — " + $("mode").selectedOptions[0].text);
    bubble("buddy", data.reply);
    speakReply(data.audio_url, data.reply);
    $("gate").style.display = "none";
    $("endBtn").disabled = false;
  } catch (e) {
    $("gateErr").textContent = "Could not start: " + e.message +
      " — is the server running and Ollama up?";
  }
  $("startBtn").disabled = false;
}

/* Mode dropdown: switching abandons the current session and starts the
 * newly selected mode immediately — no page refresh needed. */
$("mode").addEventListener("change", async () => {
  if (busy || recording) {                     // finish the current answer first
    $("mode").value = lastMode;
    showError("Finish or stop the current answer first.");
    return;
  }
  showError("");
  stopAudio();
  if (sessionId) {
    const fd = new FormData();
    fd.append("session_id", sessionId);
    await fetch("/api/abandon", { method: "POST", body: fd }).catch(() => {});
    sessionId = null;
  }
  $("endBtn").disabled = true;
  await startSession();
});

async function endSession() {
  if (!sessionId || busy) return;
  busy = true; $("endBtn").disabled = true; $("mic").disabled = true;
  stopAudio();
  bubble("system", "Wrapping up… building your coach report.");
  try {
    const fd = new FormData();
    fd.append("session_id", sessionId);
    const r = await fetch("/api/feedback", { method: "POST", body: fd });
    if (!r.ok) throw new Error("server said " + r.status);
    const { report, stats, transcript_file } = await r.json();
    renderReport(report, stats, transcript_file);
    sessionId = null;
    $("micLabel").textContent = "Pick a mode and press Start for a new session";
    $("gate").style.display = "flex";       // ready for the next round
    $("gateHeading").textContent = "Practice again?";
  } catch (e) {
    showError("Feedback failed: " + e.message);
    $("endBtn").disabled = false;
  }
  busy = false; $("mic").disabled = false;
}

function renderReport(rep, stats, file) {
  const el = $("report");
  const list = (a) => (a && a.length)
    ? "<ul>" + a.map((x) => `<li>${x}</li>`).join("") + "</ul>" : "";
  el.innerHTML = `
    <div class="score">${rep.overall_score ?? "–"}<span style="font-size:16px;color:var(--dim)">/10</span></div>
    <p>${rep.summary ?? ""}</p>
    <h3 style="color:var(--good)">Strengths</h3>${list(rep.strengths)}
    <h3 style="color:var(--warn)">To improve</h3>${list(rep.improvements)}
    ${rep.best_answer ? `<p><b>Best:</b> ${rep.best_answer}</p>` : ""}
    ${rep.weakest_answer ? `<p><b>Weakest:</b> ${rep.weakest_answer}</p>` : ""}
    <div class="focus"><b>Next focus:</b> ${rep.next_focus ?? "keep practicing!"}</div>`;
  $("saved").textContent = file ? "Saved on server: transcripts/" + file : "";
  $("fillers").textContent = Object.keys(stats.fillers || {}).length
    ? Object.entries(stats.fillers)
        .map(([w, n]) => `<b>${w}</b>×${n}`).join(" · ")
    : "None — clean speaking!";
}

/* ---------- mic recording ---------- */
async function toggleMic() {
  if (busy) return;
  showError("");
  if (recording) { recorder.stop(); return; }      // onstop handler sends it

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    audioChunks = [];
    recorder.ondataavailable = (e) => audioChunks.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      recording = false;
      $("mic").classList.remove("rec");
      $("mic").textContent = "🎤";
      $("micLabel").textContent = "Processing… (transcribing + thinking)";
      sendAudio(new Blob(audioChunks));
    };
    recorder.start();
    recording = true;
    $("mic").classList.add("rec");
    $("mic").textContent = "⏹";
    $("micLabel").textContent = "Recording… click again to send";
    stopAudio();                      // don't talk over you
  } catch (e) {
    showError("Mic blocked — allow microphone for localhost in Chrome settings.");
  }
}

async function sendAudio(blob) {
  if (!sessionId) return;
  busy = true; $("mic").disabled = true;
  try {
    const fd = new FormData();
    fd.append("session_id", sessionId);
    fd.append("audio", blob, "answer.webm");
    fd.append("voice", $("voice").value);
    const r = await fetch("/api/answer", { method: "POST", body: fd });
    if (!r.ok) throw new Error("server said " + r.status);
    const data = await r.json();

    if (data.transcript) bubble("you", data.transcript);
    bubble("buddy", data.reply);
    if (data.retry && data.correction) {
      correctionCard(data.correction, data.attempt, data.max_attempts);
      $("micLabel").textContent =
        `🔁 Try again — say it better (attempt ${data.attempt + 1} of ${data.max_attempts})`;
    } else {
      quickNote(data.quick_feedback);
      $("micLabel").textContent = data.finished
        ? "Bank finished — hit “End & feedback”"
        : "Click the mic, answer out loud, click again to send";
    }
    speakReply(data.audio_url, data.reply);
    $("turns").textContent = data.transcript
      ? Number($("turns").textContent) + 1 : $("turns").textContent;
    $("qNow").textContent = data.question_number ?? 0;
    updateFillers(data.fillers);
  } catch (e) {
    showError("Send failed: " + e.message);
    $("micLabel").textContent = "Click the mic to try again";
  }
  busy = false; $("mic").disabled = false;
}

function updateFillers(f) {
  if (!f) return;
  const total = Object.values(f).reduce((a, b) => a + b, 0);
  $("fillerTotal").textContent = total;
  $("fillers").innerHTML = Object.keys(f).length
    ? Object.entries(f).sort((a, b) => b[1] - a[1])
        .map(([w, n]) => `<b>${w}</b>×${n}`).join(" · ")
    : "None — clean speaking!";
}

/* ---------- voice picker (macOS voices via server; Indian first) ---------- */
async function loadVoices() {
  try {
    const r = await fetch("/api/voices");
    if (!r.ok) return;
    const { voices, default: def } = await r.json();
    const sel = $("voice");
    sel.innerHTML = "";
    for (const v of voices) {
      const opt = document.createElement("option");
      opt.value = v.name;
      opt.textContent = `${v.base || v.name} · ${v.label}`;
      sel.appendChild(opt);
    }
    const saved = localStorage.getItem("ib-voice");
    sel.value = (saved && voices.some((v) => v.name === saved)) ? saved
                                                             : (def || "Aman");
  } catch (_) { /* picker stays a placeholder; synth falls back to auto */ }
}

$("voice").addEventListener("change", () => {
  localStorage.setItem("ib-voice", $("voice").value);
  showError("");
});

/* ---------- health check + wiring ---------- */
(async () => {
  loadVoices();
  try {
    const r = await fetch("/api/health");
    if (r.ok) $("healthDot").classList.add("ok");
  } catch (_) { /* dot stays amber */ }
  // warm the voice list (Chrome loads voices async)
  if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = () => {};
})();

$("startBtn").onclick = startSession;
$("mic").onclick = toggleMic;
$("endBtn").onclick = endSession;
$("ttsToggle").onclick = () => {
  ttsOn = !ttsOn;
  stopAudio();
  $("ttsToggle").textContent = ttsOn ? "🔊 Voice: on" : "🔇 Voice: off";
};
