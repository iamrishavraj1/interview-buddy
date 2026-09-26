/* Interview Buddy frontend.
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

/* ---------- tiny helpers ---------- */
function scrollDown() { chat.scrollTop = chat.scrollHeight; }

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

function showError(msg) { $("err").textContent = msg || ""; }

function speak(text) {
  if (!ttsOn || !("speechSynthesis" in window)) return;
  speechSynthesis.cancel();                       // stop any earlier reply
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
  try {
    const r = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: $("mode").value }),
    });
    if (!r.ok) throw new Error("server said " + r.status);
    const data = await r.json();
    sessionId = data.session_id;
    $("qTot").textContent = data.total_questions || "–";
    bubble("system", "Session started — " + $("mode").selectedOptions[0].text);
    bubble("buddy", data.reply);
    speak(data.reply);
    $("gate").style.display = "none";
    $("endBtn").disabled = false;
  } catch (e) {
    $("gateErr").textContent = "Could not start: " + e.message +
      " — is the server running and Ollama up?";
  }
  $("startBtn").disabled = false;
}

async function endSession() {
  if (!sessionId || busy) return;
  busy = true; $("endBtn").disabled = true; $("mic").disabled = true;
  speechSynthesis.cancel();
  bubble("system", "Wrapping up… building your coach report.");
  try {
    const fd = new FormData();
    fd.append("session_id", sessionId);
    const r = await fetch("/api/feedback", { method: "POST", body: fd });
    if (!r.ok) throw new Error("server said " + r.status);
    const { report, stats, transcript_file } = await r.json();
    renderReport(report, stats, transcript_file);
    sessionId = null;
    $("micLabel").textContent = "Session over — refresh the page for a new one";
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
    speechSynthesis.cancel();                      // don't talk over you
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
    const r = await fetch("/api/answer", { method: "POST", body: fd });
    if (!r.ok) throw new Error("server said " + r.status);
    const data = await r.json();

    if (data.transcript) bubble("you", data.transcript);
    bubble("buddy", data.reply);
    quickNote(data.quick_feedback);
    speak(data.reply);
    $("turns").textContent = data.transcript
      ? Number($("turns").textContent) + 1 : $("turns").textContent;
    $("qNow").textContent = data.question_number ?? 0;
    updateFillers(data.fillers);
    $("micLabel").textContent = data.finished
      ? "Bank finished — hit “End & feedback”"
      : "Click the mic, answer out loud, click again to send";
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

/* ---------- health check + wiring ---------- */
(async () => {
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
  if (!ttsOn) speechSynthesis.cancel();
  $("ttsToggle").textContent = ttsOn ? "🔊 Voice: on" : "🔇 Voice: off";
};
