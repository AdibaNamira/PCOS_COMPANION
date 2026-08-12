"""
Full pipeline + MedlinePlus + special intents + voice input + real period
tracking (Part 13, SQLite-backed with anonymous device cookie).
"""

import uuid
from datetime import date
from flask import Flask, request, jsonify, render_template_string

from planner import ResponsePlanner
from generator import generate_response
from verifier import verify, log_interaction
from feedback import log_feedback
from medlineplus_client import try_augment_plan_with_medlineplus
from special_intents import get_special_response
from intent_classifier import classify_message, is_high_risk_medical, is_source_followup_request
from cycle_tracker import compute_cycle_context
from cycle_store import log_period_start, get_period_history, compute_avg_cycle_length, get_latest_period_start

app = Flask(__name__)
planner = ResponsePlanner()
LAST_SOURCE_BY_DEVICE = {}  # simple in-memory tracking, per anonymous device_id

DEVICE_COOKIE_NAME = "pcos_device_id"
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


def ensure_device_id():
    device_id = request.cookies.get(DEVICE_COOKIE_NAME)
    is_new = False
    if not device_id:
        device_id = str(uuid.uuid4())
        is_new = True
    return device_id, is_new


def attach_device_cookie(response, device_id, is_new):
    if is_new:
        response.set_cookie(DEVICE_COOKIE_NAME, device_id, max_age=DEVICE_COOKIE_MAX_AGE,
                             httponly=True, samesite="Lax")
    return response


INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>PCOS Companion</title>
<style>
  :root {
    --bg: #faf9f7; --card: #ffffff; --accent: #d98ca0; --accent-soft: #f3d9e0;
    --accent-dark: #b96a80; --lavender: #cdd3f0; --text: #3a3540; --text-soft: #8a8390;
    --warn-bg: #fff6e0; --warn-border: #e0b400; --mic-active: #e05252;
  }
  * { box-sizing: border-box; }
  body { font-family: 'Segoe UI', Arial, sans-serif; background: var(--bg); margin: 0; display: flex; justify-content: center; color: var(--text); overflow: hidden; position: relative; }
  .blob { position: fixed; border-radius: 50%; filter: blur(60px); opacity: 0.35; z-index: 0; pointer-events: none; }
  .blob.one { width: 260px; height: 260px; background: var(--accent-soft); top: -80px; left: -60px; animation: floatOne 14s ease-in-out infinite; }
  .blob.two { width: 220px; height: 220px; background: var(--lavender); bottom: -60px; right: -60px; animation: floatTwo 16s ease-in-out infinite; }
  @keyframes floatOne { 0%, 100% { transform: translate(0,0);} 50% { transform: translate(30px,40px);} }
  @keyframes floatTwo { 0%, 100% { transform: translate(0,0);} 50% { transform: translate(-30px,-30px);} }
  #app { width: 100%; max-width: 600px; height: 100vh; display: flex; flex-direction: column; position: relative; z-index: 1; background: var(--card); box-shadow: 0 0 40px rgba(0,0,0,0.05); }
  header { padding: 14px 22px; border-bottom: 1px solid #f0ecec; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  header .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); animation: pulse 2.2s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { transform: scale(1); opacity: 1;} 50% { transform: scale(1.4); opacity: 0.6;} }
  header .title { font-size: 1.15em; font-weight: 600; }
  header select { font-size: 0.8em; border-radius: 10px; border: 1px solid #e8e4e4; padding: 3px 6px; background: #fbfafa; color: var(--text); }
  header .subtitle { font-size: 0.8em; color: var(--text-soft); margin-left: auto; }
  #cycle-badge { font-size: 0.78em; background: var(--lavender); color: #3a3550; padding: 4px 10px; border-radius: 12px; cursor: pointer; white-space: nowrap; }
  #cycle-panel { display: none; padding: 14px 18px; background: #f8f6fb; border-bottom: 1px solid #f0ecec; flex-direction: column; gap: 10px; }
  #cycle-panel.open { display: flex; }
  #cycle-panel .row { display: flex; gap: 10px; align-items: flex-end; }
  #cycle-panel label { font-size: 0.82em; color: var(--text-soft); display: flex; flex-direction: column; gap: 4px; flex: 1; }
  #cycle-panel input { padding: 8px 10px; border-radius: 10px; border: 1px solid #e0dce8; font-size: 0.9em; }
  #cycle-panel button.log-btn { padding: 9px 16px; border-radius: 14px; border: none; background: var(--accent); color: white; cursor: pointer; font-size: 0.85em; height: 38px; }
  #cycle-panel .avg-line { font-size: 0.8em; color: var(--text-soft); }
  #cycle-history { font-size: 0.8em; color: var(--text-soft); }
  #cycle-panel .note { font-size: 0.72em; color: var(--text-soft); }
  #messages { flex: 1; overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 14px; }
  .msg { max-width: 80%; padding: 12px 16px; border-radius: 16px; line-height: 1.45; white-space: pre-wrap; font-size: 0.96em; animation: messageIn 0.28s ease-out; }
  @keyframes messageIn { from { opacity: 0; transform: translateY(8px);} to { opacity: 1; transform: translateY(0);} }
  .msg.user { align-self: flex-end; background: var(--accent-soft); border-bottom-right-radius: 4px; color: #5a3c46; }
  .msg.bot { align-self: flex-start; background: #f7f6f4; border-bottom-left-radius: 4px; }
  .msg.bot.flagged { border: 1.5px solid var(--warn-border); background: var(--warn-bg); }
  .feedback-row { display: flex; gap: 10px; margin-top: 8px; }
  .feedback-row button { border: none; background: transparent; cursor: pointer; font-size: 1.05em; opacity: 0.4; transition: transform 0.15s ease, opacity 0.15s ease; }
  .feedback-row button:hover { opacity: 0.9; transform: scale(1.15); }
  .feedback-row button.selected { opacity: 1; transform: scale(1.2); }
  #quick-replies { padding: 0 18px 12px; display: flex; flex-wrap: wrap; gap: 8px; }
  #quick-replies.hidden { display: none; }
  .quick-reply-btn {
    background: #f7f6f4; border: 1px solid #e8e4e4; border-radius: 16px;
    padding: 8px 14px; font-size: 0.85em; cursor: pointer; color: var(--text);
    transition: background 0.15s ease, border-color 0.15s ease;
  }
  .quick-reply-btn:hover { background: var(--accent-soft); border-color: var(--accent); }
  #typing { padding: 0 18px 6px; display: flex; align-items: center; gap: 4px; min-height: 18px; }
  #typing { padding: 0 18px 6px; display: flex; align-items: center; gap: 4px; min-height: 18px; }
  #typing .dot-anim { width: 6px; height: 6px; border-radius: 50%; background: var(--text-soft); animation: bounce 1.2s infinite ease-in-out; }
  #typing .dot-anim:nth-child(2) { animation-delay: 0.15s; }
  #typing .dot-anim:nth-child(3) { animation-delay: 0.3s; }
  @keyframes bounce { 0%,60%,100% { transform: translateY(0); opacity: 0.5;} 30% { transform: translateY(-4px); opacity: 1;} }
  #input-row { display: flex; padding: 14px; border-top: 1px solid #f0ecec; background: var(--card); gap: 8px; }
  #input-row input { flex: 1; padding: 12px 16px; border-radius: 22px; border: 1px solid #e8e4e4; outline: none; font-size: 0.95em; background: #fbfafa; }
  #input-row input:disabled { opacity: 0.6; cursor: not-allowed; }
  #input-row input:focus { border-color: var(--accent); }
  #input-row button.send-btn { padding: 12px 22px; border-radius: 22px; border: none; background: var(--accent); color: white; cursor: pointer; font-size: 0.95em; }
  #input-row button.send-btn:hover { background: var(--accent-dark); }
  #mic-btn { width: 44px; height: 44px; border-radius: 50%; border: none; background: #f3d9e0; color: var(--accent-dark); cursor: pointer; font-size: 1.1em; flex-shrink: 0; display: flex; align-items: center; justify-content: center; transition: background 0.15s ease, transform 0.15s ease; }
  #mic-btn:hover { background: var(--accent-soft); }
  #mic-btn.listening { background: var(--mic-active); color: white; animation: micPulse 1s infinite; }
  @keyframes micPulse { 0%,100% { transform: scale(1);} 50% { transform: scale(1.12);} }
  #mic-btn:disabled { opacity: 0.3; cursor: not-allowed; }
</style>
</head>
<body>
<div class="blob one"></div>
<div class="blob two"></div>
<div id="app">
  <header>
    <div class="dot"></div>
    <div class="title">PCOS Companion</div>
    <select id="voice-lang" title="Voice input language">
      <option value="en-US">EN</option>
      <option value="bn-IN">বাংলা</option>
    </select>
    <span id="cycle-badge">🩸 Log your period</span>
    <div class="subtitle">prototype</div>
  </header>

  <div id="cycle-panel">
    <div class="row">
      <label>Period start date
        <input type="date" id="cycle-date" />
      </label>
      <button class="log-btn" id="cycle-log-btn">Log period</button>
    </div>
    <div class="avg-line" id="cycle-avg-line">No history yet — log at least 2 periods for an accurate average.</div>
    <div id="cycle-history"></div>
    <div class="note">Stored on this server, linked only to an anonymous browser ID — not to your name or any account (until real login is added later).</div>
  </div>

  <div id="messages"></div>
  <div id="quick-replies"></div>
  <div id="typing"></div>
  <div id="input-row">
    <button id="mic-btn" title="Speak your message">🎤</button>
    <input id="input" type="text" placeholder="Type or tap the mic to speak..." autofocus />
    <button class="send-btn" id="send">Send</button>
  </div>
</div>

<script>
const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
const typingEl = document.getElementById('typing');
const quickRepliesEl = document.getElementById('quick-replies');

const QUICK_REPLIES = [
  "What are the symptoms of PCOS?",
  "What questions should I ask my doctor?",
  "I'm feeling really anxious about my period",
  "Does PCOS cause weight gain?",
  "I feel alone dealing with this",
];

function renderQuickReplies() {
  quickRepliesEl.innerHTML = '';
  QUICK_REPLIES.forEach(q => {
    const btn = document.createElement('button');
    btn.className = 'quick-reply-btn';
    btn.textContent = q;
    btn.onclick = () => {
      inputEl.value = q;
      sendMessage();
    };
    quickRepliesEl.appendChild(btn);
  });
}
renderQuickReplies();
const micBtn = document.getElementById('mic-btn');
const langSelect = document.getElementById('voice-lang');
const cycleBadge = document.getElementById('cycle-badge');
const cyclePanel = document.getElementById('cycle-panel');
const cycleDateInput = document.getElementById('cycle-date');
const cycleLogBtn = document.getElementById('cycle-log-btn');
const cycleAvgLine = document.getElementById('cycle-avg-line');
const cycleHistoryEl = document.getElementById('cycle-history');

cycleDateInput.valueAsDate = new Date();

function renderCycleStatus(data) {
  if (data.status === 'ok') {
    const phaseLabel = data.phase.charAt(0).toUpperCase() + data.phase.slice(1);
    cycleBadge.textContent = `🩸 ${phaseLabel} · Day ${data.cycle_day}`;
  } else {
    cycleBadge.textContent = '🩸 Log your period';
  }
  if (data.history && data.history.length >= 2) {
    cycleAvgLine.textContent = `Average cycle length (from your history): ${data.avg_cycle_length} days`;
  } else {
    cycleAvgLine.textContent = 'No history yet — log at least 2 periods for an accurate average.';
  }
  const history = data.history || [];
  if (history.length === 0) {
    cycleHistoryEl.textContent = '';
  } else {
    cycleHistoryEl.textContent = `Last logged: ${history[0]}` + (history.length > 1 ? ` (${history.length} periods tracked total)` : '');
  }
}

async function refreshCycleStatus() {
  try {
    const res = await fetch('/cycle_status');
    const data = await res.json();
    renderCycleStatus(data);
  } catch (e) { console.error('cycle status failed', e); }
}

cycleBadge.onclick = () => { cyclePanel.classList.toggle('open'); };

cycleLogBtn.onclick = async () => {
  const dateVal = cycleDateInput.value;
  if (!dateVal) return;
  cycleLogBtn.disabled = true;
  cycleLogBtn.textContent = 'Logging...';
  try {
    const res = await fetch('/cycle_log', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({period_start_date: dateVal})
    });
    const data = await res.json();
    renderCycleStatus(data);
  } catch (e) {
    console.error('cycle log failed', e);
  } finally {
    cycleLogBtn.disabled = false;
    cycleLogBtn.textContent = 'Log period';
  }
};

refreshCycleStatus();

function addUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'msg user';
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function linkify(text) {
  const escaped = escapeHtml(text);
  const urlPattern = /(https?:\/\/[^\s]+)/g;
  return escaped.replace(urlPattern, (url) => {
    // strip trailing punctuation that isn't part of the URL
    const trailingMatch = url.match(/[.,)\]]+$/);
    const trailing = trailingMatch ? trailingMatch[0] : '';
    const cleanUrl = trailing ? url.slice(0, -trailing.length) : url;
    return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer">${cleanUrl}</a>${trailing}`;
  });
}

function addBotMessage(text, interactionId, flagged) {
  const div = document.createElement('div');
  div.className = 'msg bot' + (flagged ? ' flagged' : '');
  div.innerHTML = linkify(text);
  const feedbackRow = document.createElement('div');
  feedbackRow.className = 'feedback-row';
  const upBtn = document.createElement('button');
  upBtn.textContent = '\\ud83d\\udc4d';
  const downBtn = document.createElement('button');
  downBtn.textContent = '\\ud83d\\udc4e';
  upBtn.onclick = () => sendFeedback(interactionId, 'up', upBtn, downBtn);
  downBtn.onclick = () => sendFeedback(interactionId, 'down', downBtn, upBtn);
  feedbackRow.appendChild(upBtn);
  feedbackRow.appendChild(downBtn);
  div.appendChild(feedbackRow);
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showTyping() { typingEl.innerHTML = '<span class="dot-anim"></span><span class="dot-anim"></span><span class="dot-anim"></span>'; }
function hideTyping() { typingEl.innerHTML = ''; }

async function sendFeedback(interactionId, rating, clickedBtn, otherBtn) {
  if (!interactionId) return;
  clickedBtn.classList.add('selected');
  otherBtn.classList.remove('selected');
  otherBtn.disabled = true;
  clickedBtn.disabled = true;
  try {
    await fetch('/feedback', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({interaction_id: interactionId, rating: rating})
    });
  } catch (e) { console.error('feedback failed', e); }
}

let isSending = false;
let currentController = null;

async function sendMessage() {
  if (isSending) return;  // Enter key still blocked mid-send; use the Stop button instead
  const text = inputEl.value.trim();
  if (!text) return;

  isSending = true;
  sendBtn.textContent = 'Stop';
  micBtn.disabled = true;
  // Note: inputEl is intentionally NOT disabled - you can keep typing your
  // next message while waiting, same as Claude's interface.

  quickRepliesEl.classList.add('hidden');
  addUserMessage(text);
  inputEl.value = '';
  showTyping();

  currentController = new AbortController();

  try {
    const res = await fetch('/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text}),
      signal: currentController.signal
    });
    const data = await res.json();
    hideTyping();
    addBotMessage(data.response, data.interaction_id, data.flagged);
  } catch (e) {
    hideTyping();
    if (e.name === 'AbortError') {
      addBotMessage('(Cancelled)', null, false);
    } else {
      addBotMessage('Sorry, something went wrong reaching the server. Please try again.', null, false);
      console.error(e);
    }
  } finally {
    isSending = false;
    currentController = null;
    sendBtn.textContent = 'Send';
    if (SpeechRecognitionAPI) micBtn.disabled = false;
    inputEl.focus();
  }
}

function stopOrSend() {
  if (isSending && currentController) {
    currentController.abort();
  } else {
    sendMessage();
  }
}

sendBtn.onclick = stopOrSend;
inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !isSending) sendMessage();
});

const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let isListening = false;
if (!SpeechRecognitionAPI) {
  micBtn.disabled = true;
  micBtn.title = 'Voice input is not supported in this browser. Try Chrome, Edge, or Safari.';
} else {
  recognition = new SpeechRecognitionAPI();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.onstart = () => { isListening = true; micBtn.classList.add('listening'); micBtn.textContent = '⏺'; };
  recognition.onresult = (event) => {
    let transcript = '';
    for (let i = 0; i < event.results.length; i++) { transcript += event.results[i][0].transcript; }
    inputEl.value = transcript;
  };
  recognition.onerror = (event) => { console.error('speech recognition error', event.error); stopListening(); };
  recognition.onend = () => { stopListening(); };
  function stopListening() { isListening = false; micBtn.classList.remove('listening'); micBtn.textContent = '🎤'; }
  micBtn.onclick = () => {
    if (isListening) { recognition.stop(); return; }
    recognition.lang = langSelect.value;
    inputEl.value = '';
    inputEl.placeholder = 'Listening...';
    try { recognition.start(); } catch (e) { console.error('could not start recognition', e); }
  };
}
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


@app.route("/cycle_status")
def cycle_status():
    device_id, is_new = ensure_device_id()
    history = get_period_history(device_id)
    avg = compute_avg_cycle_length(device_id)
    latest = get_latest_period_start(device_id)
    context = compute_cycle_context(latest, avg) if latest else None

    payload = {"status": "ok" if context else "no_data", "history": history, "avg_cycle_length": avg}
    if context:
        payload.update({"phase": context["phase"], "cycle_day": context["cycle_day"], "days_late": context["days_late"]})

    response = jsonify(payload)
    return attach_device_cookie(response, device_id, is_new)


@app.route("/cycle_log", methods=["POST"])
def cycle_log():
    device_id, is_new = ensure_device_id()
    data = request.get_json(force=True)
    period_date = data.get("period_start_date") or date.today().isoformat()

    log_period_start(device_id, period_date)

    history = get_period_history(device_id)
    avg = compute_avg_cycle_length(device_id)
    latest = get_latest_period_start(device_id)
    context = compute_cycle_context(latest, avg) if latest else None

    payload = {"status": "ok" if context else "no_data", "history": history, "avg_cycle_length": avg}
    if context:
        payload.update({"phase": context["phase"], "cycle_day": context["cycle_day"], "days_late": context["days_late"]})

    response = jsonify(payload)
    return attach_device_cookie(response, device_id, is_new)


@app.route("/chat", methods=["POST"])
def chat():
    device_id, is_new = ensure_device_id()

    data = request.get_json(force=True)
    patient_message = (data.get("message") or "").strip()
    if not patient_message:
        response = jsonify({"response": "Please type something.", "interaction_id": None, "flagged": False})
        return attach_device_cookie(response, device_id, is_new)

    category, has_emotion = classify_message(patient_message)
    hard_high_risk = is_high_risk_medical(patient_message)  # deterministic, always checked
    hard_source_followup = is_source_followup_request(patient_message)  # deterministic backstop

    if category == "source_followup" or hard_source_followup:
        last_source = LAST_SOURCE_BY_DEVICE.get(device_id)
        if last_source:
            url_part = f"\nLink: {last_source['source_url']}" if last_source.get("source_url") else ""
            special_response = (
                f"That came from: {last_source['source_note']} "
                f"(topic: {last_source['topic']}){url_part}"
            )
        else:
            special_response = (
                "I haven't cited a specific source in our chat yet — ask me a factual question "
                "and I'll always tell you exactly where the information came from."
            )
        fake_plan = {"intent": "source_followup", "factual_ratio": 0, "empathetic_ratio": 0,
                     "use_not_sure_fallback": False, "high_risk_override": False}
        fake_verification = {"passed": True, "issues": [], "grounding_score": None}
        interaction_id = log_interaction(patient_message, fake_plan, special_response, fake_verification)
        response = jsonify({"response": special_response, "interaction_id": interaction_id, "flagged": False})
        return attach_device_cookie(response, device_id, is_new)
    if category in ("meta_about_app", "doc_prep", "doctor_directory_request"):
        special_response = get_special_response(category)
        fake_plan = {"intent": category, "factual_ratio": 0, "empathetic_ratio": 0,
                     "use_not_sure_fallback": False, "high_risk_override": False}
        fake_verification = {"passed": True, "issues": [], "grounding_score": None}
        interaction_id = log_interaction(patient_message, fake_plan, special_response, fake_verification)
        response = jsonify({"response": special_response, "interaction_id": interaction_id, "flagged": False})
        return attach_device_cookie(response, device_id, is_new)

    plan = planner.plan(patient_message, has_emotion_override=has_emotion, is_high_risk_override=hard_high_risk)
    factual_entry = plan["top_factual_match"]["entry"] if plan["top_factual_match"] else None
    empathetic_entries = [plan["top_empathetic_match"]] if plan["top_empathetic_match"] else []

    plan, medline_entry = try_augment_plan_with_medlineplus(patient_message, plan)
    if medline_entry:
        factual_entry = medline_entry

    avg = compute_avg_cycle_length(device_id)
    latest = get_latest_period_start(device_id)
    cycle_ctx = compute_cycle_context(latest, avg) if latest else None
    cycle_guidance = cycle_ctx["guidance_text"] if cycle_ctx else None

    try:
        result = generate_response(patient_message, plan, factual_entry, empathetic_entries,
                                    dry_run=False, cycle_context=cycle_guidance)
        raw_response = result["response_text"]
    except Exception as e:
        response = jsonify({
            "response": f"Sorry, I couldn't reach the AI model right now ({e}). Please check the server's .env setup.",
            "interaction_id": None, "flagged": False
        })
        return attach_device_cookie(response, device_id, is_new)

    verification = verify(raw_response, plan, factual_entry)
    final_response = verification["safe_response"]

    if factual_entry and verification["passed"] and not plan.get("use_not_sure_fallback") and not plan.get("high_risk_override"):
        LAST_SOURCE_BY_DEVICE[device_id] = {
            "source_note": factual_entry.get("source_note", "internal knowledge base"),
            "source_url": factual_entry.get("source_url"),
            "topic": factual_entry.get("content", "")[:80] + "...",
        }
    flagged = bool(plan.get("use_not_sure_fallback") or plan.get("high_risk_override") or not verification["passed"])

    interaction_id = log_interaction(patient_message, plan, final_response, verification)

    response = jsonify({"response": final_response, "interaction_id": interaction_id, "flagged": flagged})
    return attach_device_cookie(response, device_id, is_new)


@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json(force=True)
    interaction_id = data.get("interaction_id")
    rating = data.get("rating")
    comment = data.get("comment")
    if not interaction_id or rating not in ("up", "down"):
        return jsonify({"status": "error", "message": "invalid feedback payload"}), 400
    record = log_feedback(interaction_id, rating, comment)
    return jsonify({"status": "ok", "record": record})


if __name__ == "__main__":
    app.run(debug=True, port=5000)