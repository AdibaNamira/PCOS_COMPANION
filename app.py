"""
Full pipeline + MedlinePlus + special intents + voice input + real period
tracking (Part 13, SQLite-backed with anonymous device cookie).
"""

import uuid
from datetime import date, timedelta
import os
from datetime import timedelta
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template_string, render_template, redirect, session

from planner import ResponsePlanner
from generator import generate_response
from verifier import verify, log_interaction
from feedback import log_feedback
from medlineplus_client import try_augment_plan_with_medlineplus
from special_intents import get_special_response
from intent_classifier import classify_message, is_high_risk_medical, is_source_followup_request
from cycle_tracker import compute_cycle_context
from cycle_store import (log_period_start, get_period_history, compute_avg_cycle_length,
                         get_latest_period_start, delete_period_entry,
                         delete_history as delete_cycle_history)
from auth import auth_bp, login_required, current_user_id
import chat_store
import support_contact
from crisis_detector import detect_crisis
from mailer import send_support_alert
from admin import admin_bp
from research_store import is_admin

load_dotenv()

app = Flask(__name__)
planner = ResponsePlanner()

# Signs the session cookie. MUST be set in .env and MUST stay secret -
# anyone with this value can forge a logged-in session for any account.
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is not set. Add a long random value to your .env file.\n"
        "Generate one with:  python -c \"import secrets; print(secrets.token_hex(32))\""
    )

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Set to True once this is served over HTTPS. Leave False for local http.
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
)

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)


def ensure_device_id():
    """
    Kept for signature compatibility with the rest of app.py. Data is now
    keyed on the authenticated account instead of an anonymous cookie, so
    this returns the user id. Every route that calls it is @login_required,
    so current_user_id() is guaranteed non-None here.
    """
    return str(current_user_id()), False


def attach_device_cookie(response, device_id, is_new):
    # No-op now that identity comes from the signed session cookie.
    return response


INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>PCOS Companion</title>
<link rel="stylesheet" href="/static/theme.css">
<style>
  * { box-sizing: border-box; }
  body { font-family: var(--font-stack); background: var(--bg); margin: 0; display: flex; justify-content: center; color: var(--text); overflow: hidden; position: relative; }
  .blob { position: fixed; border-radius: 50%; filter: blur(60px); opacity: 0.35; z-index: 0; pointer-events: none; }
  .blob.one { width: 260px; height: 260px; background: var(--accent-soft); top: -80px; left: -60px; animation: floatOne 14s ease-in-out infinite; }
  .blob.two { width: 220px; height: 220px; background: var(--lavender); bottom: -60px; right: -60px; animation: floatTwo 16s ease-in-out infinite; }
  @keyframes floatOne { 0%, 100% { transform: translate(0,0);} 50% { transform: translate(30px,40px);} }
  @keyframes floatTwo { 0%, 100% { transform: translate(0,0);} 50% { transform: translate(-30px,-30px);} }
  #app { width: 100%; max-width: 600px; height: 100vh; display: flex; flex-direction: column; position: relative; z-index: 1; background: var(--card); box-shadow: 0 0 40px rgba(0,0,0,0.05); }
  header { padding: 14px 22px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  header .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); animation: pulse 2.2s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { transform: scale(1); opacity: 1;} 50% { transform: scale(1.4); opacity: 0.6;} }
  header .title { font-size: 1.15em; font-weight: 600; }
  header select { font-size: 0.8em; border-radius: 10px; border: 1px solid var(--border); padding: 3px 6px; background: var(--bg); color: var(--text); }
  header .subtitle { font-size: 0.8em; color: var(--text-soft); margin-left: auto; }
  #account-row { display: flex; align-items: center; gap: 10px; padding: 7px 22px; background: var(--bg);
                 border-bottom: 1px solid var(--border); font-size: 0.78em; color: var(--text-soft); }
  #account-email { font-weight: 500; color: var(--text); }
  #account-row .spacer { margin-left: auto; }
  #account-row button { border: none; background: transparent; color: var(--accent-dark); cursor: pointer;
                        font-size: 1em; font-family: inherit; padding: 3px 8px; border-radius: 8px; }
  #account-row button:hover { background: var(--accent-soft); }
  #account-row button.danger { color: #a94442; }
  #account-row button.danger:hover { background: #fdeaea; }
  #crisis-card { background: #fff5f6; border: 1px solid #f4c0d1; border-left: 4px solid var(--accent);
                 border-radius: 12px; padding: 13px 15px; margin: 8px 0; }
  #crisis-card .cta { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 11px; }
  #crisis-card button { border: none; border-radius: 10px; padding: 9px 14px; font-size: 0.82em;
                        cursor: pointer; font-family: inherit; }
  #crisis-card button.alert { background: var(--accent); color: #fff; }
  #crisis-card button.alert:hover { background: var(--accent-dark); }
  #crisis-card button.alert:disabled { opacity: 0.6; cursor: default; }
  #crisis-card button.setup { background: #fff; border: 1px solid var(--accent); color: var(--accent-dark); }
  #crisis-card .sent { font-size: 0.82em; color: var(--success-text); margin-top: 10px; }
  #modal-backdrop { position: fixed; inset: 0; background: rgba(44,42,56,0.45); display: none;
                    align-items: center; justify-content: center; padding: 20px; z-index: 50; }
  #modal-backdrop.open { display: flex; }
  #contact-modal { background: var(--card); border-radius: 16px; padding: 24px; width: 100%; max-width: 380px; }
  #contact-modal h3 { margin: 0 0 6px; font-size: 1.02em; }
  #contact-modal p.why { font-size: 0.78em; color: var(--text-soft); line-height: 1.5; margin: 0 0 16px; }
  #contact-modal label { display: block; font-size: 0.76em; color: var(--text-soft); margin-bottom: 5px; }
  #contact-modal input { width: 100%; padding: 9px 11px; margin-bottom: 12px; border: 1px solid var(--border);
                         border-radius: 10px; font-size: 0.9em; font-family: inherit; background: var(--bg); }
  #contact-modal .actions { display: flex; gap: 8px; margin-top: 6px; }
  #contact-modal .actions button { flex: 1; padding: 10px; border-radius: 10px; font-size: 0.85em;
                                   cursor: pointer; font-family: inherit; border: none; }
  #contact-modal .save { background: var(--accent); color: #fff; }
  #contact-modal .cancel { background: var(--bg); border: 1px solid var(--border); color: var(--text-soft); }
  #contact-modal .remove { background: none; border: none; color: var(--danger); font-size: 0.78em;
                           cursor: pointer; margin-top: 12px; padding: 4px; }
  #contact-modal .err { font-size: 0.78em; color: var(--danger); margin-bottom: 10px; }
  #history-divider { text-align: center; font-size: 0.72em; color: var(--text-soft); padding: 4px 0;
                     border-top: 1px dashed #e8e4e4; margin-top: 4px; }
  #cycle-badge { font-size: 0.78em; background: var(--iris-soft); color: var(--iris-text); padding: 4px 10px; border-radius: 12px; cursor: pointer; white-space: nowrap; }
  #cycle-panel { display: none; padding: 14px 18px; background: var(--accent-tint); border-bottom: 1px solid var(--border); flex-direction: column; gap: 10px; }
  #cycle-panel.open { display: flex; }
  #cycle-panel .row { display: flex; gap: 10px; align-items: flex-end; }
  #cycle-panel label { font-size: 0.82em; color: var(--text-soft); display: flex; flex-direction: column; gap: 4px; flex: 1; }
  #cycle-panel input { padding: 8px 10px; border-radius: 10px; border: 1px solid var(--border); font-size: 0.9em; }
  #cycle-panel button.log-btn { padding: 9px 16px; border-radius: 14px; border: none; background: var(--accent); color: white; cursor: pointer; font-size: 0.85em; height: 38px; }
  #cycle-panel .avg-line { font-size: 0.8em; color: var(--text-soft); }
  #cycle-history { font-size: 0.8em; color: var(--text-soft); }
  #cycle-panel .note { font-size: 0.72em; color: var(--text-soft); }
  #messages { flex: 1; overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 14px; }
  .msg { max-width: 80%; padding: 12px 16px; border-radius: 16px; line-height: var(--line-height-body); white-space: pre-wrap; font-size: 0.96em; animation: messageIn 0.28s ease-out; }
  @keyframes messageIn { from { opacity: 0; transform: translateY(8px);} to { opacity: 1; transform: translateY(0);} }
  .msg.user { align-self: flex-end; background: var(--rose); color: #fff; border-bottom-right-radius: 4px; }
  .msg.bot { align-self: flex-start; background: var(--bg); border-bottom-left-radius: 4px; }
  .msg.bot.flagged { border: 1.5px solid var(--warn-border); background: var(--warn-bg); }
  .feedback-row { display: flex; gap: 10px; margin-top: 8px; }
  .feedback-row button { border: none; background: transparent; cursor: pointer; font-size: 1.05em; opacity: 0.4; transition: transform 0.15s ease, opacity 0.15s ease; }
  .feedback-row button:hover { opacity: 0.9; transform: scale(1.15); }
  .feedback-row button.selected { opacity: 1; transform: scale(1.2); }
  #quick-replies { padding: 0 18px 12px; display: flex; flex-wrap: wrap; gap: 8px; }
  #quick-replies.hidden { display: none; }
  .quick-reply-btn {
    background: var(--bg); border: 1px solid var(--border); border-radius: 16px;
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
  #input-row input { flex: 1; padding: 12px 16px; border-radius: 22px; border: 1px solid var(--border); outline: none; font-size: 0.95em; background: var(--bg); }
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
    <span id="cycle-badge">📅 Check period dates</span>
    <div class="subtitle">prototype</div>
  </header>

  <div id="account-row">
    <span>Signed in as <span id="account-email">…</span></span>
    <span class="spacer"></span>
    <a id="admin-link" href="/admin" class="hidden-admin" style="display:none;font-size:1em;color:var(--accent-dark);text-decoration:none;padding:3px 8px;">Research</a>
    <button id="support-contact-btn" title="Someone you trust, who you can alert with one tap">Add a support source contact</button>
    <button class="danger" id="delete-data-btn" title="Permanently erase your chats and cycle data">Delete my data</button>
    <button id="logout-btn">Log out</button>
  </div>

  <div id="modal-backdrop">
    <div id="contact-modal">
      <h3>Support source contact</h3>
      <p class="why">One person you trust. If you're ever having a hard time, you can let them
        know with a single tap — nothing is ever sent without you pressing it, and your
        conversations are never shared with them.</p>
      <div class="err" id="contact-err" style="display:none"></div>
      <label for="contact-name">Their name</label>
      <input type="text" id="contact-name" placeholder="e.g. Ayesha">
      <label for="contact-email">Their email</label>
      <input type="email" id="contact-email" placeholder="them@example.com">
      <label for="contact-rel">Relationship (optional)</label>
      <input type="text" id="contact-rel" placeholder="e.g. sister, friend">
      <div class="actions">
        <button class="cancel" id="contact-cancel">Cancel</button>
        <button class="save" id="contact-save">Save</button>
      </div>
      <button class="remove" id="contact-remove" style="display:none">Remove this contact</button>
    </div>
  </div>

  <div id="cycle-panel">
    <div class="row">
      <label>Period start date
        <input type="date" id="cycle-date" />
      </label>
      <button class="log-btn" id="cycle-log-btn">Log period</button>
    </div>
    <div class="avg-line" id="cycle-avg-line">No history yet — log at least 2 periods for an accurate average.</div>
    <div id="cycle-history"></div>
    <div class="note">Stored on this server and linked to your account. The research team can review it as part of this study — no one else can. You can erase it at any time with "Delete my data" above.</div>
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
    cycleBadge.textContent = '📅 Check period dates';
  } else {
    cycleBadge.textContent = '📅 Check period dates';
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

cycleBadge.onclick = () => { window.location.href = '/calendar'; };

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

// --- Support source contact -----------------------------------------

const backdrop = document.getElementById('modal-backdrop');
let savedContact = null;

async function loadContact() {
  try {
    const res = await fetch('/support_contact');
    const data = await res.json();
    savedContact = (data.status === 'ok') ? data : null;
    document.getElementById('support-contact-btn').textContent =
      savedContact ? `Support: ${savedContact.name}` : 'Add a support source contact';
    document.getElementById('contact-remove').style.display = savedContact ? 'block' : 'none';
  } catch (e) { console.warn('contact load failed', e); }
}

function openContactModal() {
  document.getElementById('contact-err').style.display = 'none';
  document.getElementById('contact-name').value = savedContact ? savedContact.name : '';
  document.getElementById('contact-email').value = savedContact ? savedContact.email : '';
  document.getElementById('contact-rel').value = (savedContact && savedContact.relationship) || '';
  backdrop.classList.add('open');
}

document.getElementById('support-contact-btn').onclick = openContactModal;
document.getElementById('contact-cancel').onclick = () => backdrop.classList.remove('open');
backdrop.onclick = e => { if (e.target === backdrop) backdrop.classList.remove('open'); };

document.getElementById('contact-save').onclick = async () => {
  const payload = {
    name: document.getElementById('contact-name').value,
    email: document.getElementById('contact-email').value,
    relationship: document.getElementById('contact-rel').value
  };
  const res = await fetch('/support_contact', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (!res.ok) {
    const err = document.getElementById('contact-err');
    err.textContent = data.message; err.style.display = 'block';
    return;
  }
  backdrop.classList.remove('open');
  await loadContact();
};

document.getElementById('contact-remove').onclick = async () => {
  if (!confirm('Remove your support source contact?')) return;
  await fetch('/support_contact', { method: 'DELETE' });
  backdrop.classList.remove('open');
  await loadContact();
};

// --- Crisis card -----------------------------------------------------

function addCrisisCard(contactName) {
  const card = document.createElement('div');
  card.id = 'crisis-card';
  const cta = document.createElement('div');
  cta.className = 'cta';

  const alertBtn = document.createElement('button');
  alertBtn.className = 'alert';

  if (contactName) {
    alertBtn.textContent = `Let ${contactName} know I need help`;
    alertBtn.onclick = async () => {
      alertBtn.disabled = true;
      alertBtn.textContent = 'Sending…';
      try {
        const res = await fetch('/alert_support', { method: 'POST' });
        const data = await res.json();
        const note = document.createElement('div');
        note.className = 'sent';
        note.textContent = data.message;
        card.appendChild(note);
        alertBtn.textContent = res.ok ? 'Sent' : 'Try again';
        alertBtn.disabled = res.ok;
      } catch (e) {
        alertBtn.textContent = 'Try again';
        alertBtn.disabled = false;
      }
    };
  } else {
    alertBtn.textContent = 'Add someone I can alert';
    alertBtn.onclick = openContactModal;
  }
  cta.appendChild(alertBtn);
  card.appendChild(cta);
  messagesEl.appendChild(card);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// --- Account bar ---------------------------------------------------

async function loadAccount() {
  try {
    const res = await fetch('/me');
    const data = await res.json();
    if (!data.authenticated) { window.location.href = '/login'; return; }
    document.getElementById('account-email').textContent = data.email;
    if (data.is_admin) document.getElementById('admin-link').style.display = 'inline';
  } catch (e) {
    document.getElementById('account-email').textContent = 'unknown';
  }
}

document.getElementById('logout-btn').onclick = async () => {
  await fetch('/logout', { method: 'POST' });
  window.location.href = '/login';
};

document.getElementById('delete-data-btn').onclick = async () => {
  const sure = confirm('This permanently deletes your chat history and all logged period dates. Your account stays, but this cannot be undone. Continue?');
  if (!sure) return;
  const res = await fetch('/delete_my_data', { method: 'POST' });
  const data = await res.json();
  if (res.ok) {
    messagesEl.innerHTML = '';
    addBotMessage(data.message + " I'm still here whenever you want to talk.", null, false);
    refreshCycleStatus();
  } else {
    alert("Couldn't delete your data. Please try again.");
  }
};

// --- Replay past conversation on load -------------------------------

async function loadHistory() {
  try {
    const res = await fetch('/history');
    if (!res.ok) return;
    const data = await res.json();
    if (!data.messages || !data.messages.length) return;

    data.messages.forEach(turn => {
      addUserMessage(turn.patient_message);
      addBotMessage(turn.bot_response, turn.interaction_id, !!turn.flagged);
    });

    const divider = document.createElement('div');
    divider.id = 'history-divider';
    divider.textContent = '— earlier conversation —';
    messagesEl.appendChild(divider);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  } catch (e) {
    // History is a convenience, never a blocker - fail quietly.
    console.warn('Could not load history:', e);
  }
}

loadAccount();
loadHistory();
loadContact();

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
    if (data.crisis) addCrisisCard(data.support_contact_name);
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
@login_required
def index():
    return render_template_string(INDEX_HTML)


@app.route("/cycle_status")
@login_required
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
@login_required
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
@login_required
def chat():
    device_id, is_new = ensure_device_id()

    data = request.get_json(force=True)
    patient_message = (data.get("message") or "").strip()
    if not patient_message:
        response = jsonify({"response": "Please type something.", "interaction_id": None, "flagged": False})
        return attach_device_cookie(response, device_id, is_new)

    # --- Crisis check runs FIRST, before any other classification ---
    # A crisis response must not depend on the planner, the retriever, the
    # generator, or a model call succeeding. It is fixed, deterministic
    # text with real helpline numbers, so it cannot hallucinate and cannot
    # fail to appear. The conversation is never ended - the patient can
    # keep talking afterwards.
    crisis = detect_crisis(patient_message)
    if crisis:
        contact = support_contact.get_contact(device_id)
        crisis_text = CRISIS_RESPONSES[crisis]
        interaction_id = str(uuid.uuid4())
        chat_store.save_turn(device_id, patient_message, crisis_text,
                             interaction_id=interaction_id, flagged=True)
        response = jsonify({
            "response": crisis_text,
            "interaction_id": interaction_id,
            "flagged": True,
            "crisis": crisis,
            "support_contact_name": contact["contact_name"] if contact else None,
        })
        return attach_device_cookie(response, device_id, is_new)

    category, has_emotion = classify_message(patient_message)
    hard_high_risk = is_high_risk_medical(patient_message)  # deterministic, always checked
    hard_source_followup = is_source_followup_request(patient_message)  # deterministic backstop

    if category == "source_followup" or hard_source_followup:
        last_source = chat_store.get_last_source(device_id)
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

    source_note = None
    if factual_entry and verification["passed"] and not plan.get("use_not_sure_fallback") and not plan.get("high_risk_override"):
        source_note = {
            "source_note": factual_entry.get("source_note", "internal knowledge base"),
            "source_url": factual_entry.get("source_url"),
            "topic": factual_entry.get("content", "")[:80] + "...",
        }
    flagged = bool(plan.get("use_not_sure_fallback") or plan.get("high_risk_override") or not verification["passed"])

    interaction_id = log_interaction(patient_message, plan, final_response, verification)
    chat_store.save_turn(device_id, patient_message, final_response,
                         interaction_id=interaction_id, source_note=source_note, flagged=flagged)

    response = jsonify({"response": final_response, "interaction_id": interaction_id, "flagged": flagged})
    return attach_device_cookie(response, device_id, is_new)


@app.route("/feedback", methods=["POST"])
@login_required
def feedback():
    data = request.get_json(force=True)
    interaction_id = data.get("interaction_id")
    rating = data.get("rating")
    comment = data.get("comment")
    if not interaction_id or rating not in ("up", "down"):
        return jsonify({"status": "error", "message": "invalid feedback payload"}), 400
    record = log_feedback(interaction_id, rating, comment)
    return jsonify({"status": "ok", "record": record})


CRISIS_RESPONSES = {
    "self_harm": (
        "I'm really glad you told me. What you're feeling sounds incredibly heavy, "
        "and you shouldn't have to carry it on your own right now.\n\n"
        "I'm a chatbot, so I'm not the right kind of help for this — but people who "
        "are trained for exactly this are available, and talking to them costs nothing.\n\n"
        "**Kaan Pete Roi** — emotional support and suicide prevention helpline\n"
        "**09612-119911**, open daily 3pm–3am\n\n"
        "**999** — national emergency services, any time\n\n"
        "I'm still here. You can keep talking to me too."
    ),
    "medical_emergency": (
        "That sounds frightening, and it isn't something to wait out or manage alone.\n\n"
        "I'm a chatbot and I can't assess what's happening in your body — please get "
        "medical help now rather than later.\n\n"
        "**999** — national emergency services\n\n"
        "If you can, go to the nearest hospital emergency department, or ask someone "
        "near you to take you.\n\n"
        "I'm here when you're ready to talk again."
    ),
}


@app.route("/support_contact", methods=["GET", "POST", "DELETE"])
@login_required
def support_contact_route():
    user_id, _ = ensure_device_id()

    if request.method == "GET":
        contact = support_contact.get_contact(user_id)
        if not contact:
            return jsonify({"status": "none"})
        return jsonify({"status": "ok", "name": contact["contact_name"],
                        "email": contact["contact_email"],
                        "relationship": contact["relationship"]})

    if request.method == "DELETE":
        support_contact.delete_contact(user_id)
        return jsonify({"status": "ok"})

    data = request.get_json(force=True)
    saved, error = support_contact.save_contact(
        user_id, data.get("name"), data.get("email"), data.get("relationship"))
    if not saved:
        return jsonify({"status": "error", "message": error}), 400
    return jsonify({"status": "ok"})


@app.route("/alert_support", methods=["POST"])
@login_required
def alert_support():
    """
    Fires ONLY when the patient presses the button. Nothing in this app
    calls it automatically - see the consent note in support_contact.py.
    """
    user_id, _ = ensure_device_id()
    contact = support_contact.get_contact(user_id)
    if not contact:
        return jsonify({"status": "error", "message": "No support contact saved yet."}), 400

    if support_contact.recently_alerted(user_id):
        return jsonify({"status": "ok", "already_sent": True,
                        "message": f"{contact['contact_name']} was already contacted "
                                   "in the last few minutes. They know."})

    patient_label = session.get("email", "Someone you know")
    sent, error = send_support_alert(contact["contact_email"], contact["contact_name"], patient_label)
    support_contact.log_alert(user_id, contact["contact_email"], sent)

    if not sent:
        return jsonify({"status": "error", "message":
                        f"I couldn't send that email ({error}). Please call or message "
                        f"{contact['contact_name']} directly if you can."}), 502

    return jsonify({"status": "ok", "message":
                    f"I've let {contact['contact_name']} know you'd like their support. "
                    "You don't have to explain anything to them — they just know you reached out."})


@app.route("/calendar")
@login_required
def calendar_page():
    return render_template("calendar.html")


@app.route("/cycle_data")
@login_required
def cycle_data():
    """
    Everything the calendar needs in one call: full logged history, the
    computed average, current phase, and projected future start dates.

    Projections are explicitly labelled as estimates. PCOS cycles are
    frequently irregular, so these are a planning aid, not a prediction
    the patient should rely on - the UI says so too.
    """
    user_id, _ = ensure_device_id()
    history = get_period_history(user_id, limit=60)
    avg = compute_avg_cycle_length(user_id)
    latest = get_latest_period_start(user_id)
    context = compute_cycle_context(latest, avg) if latest else None

    projected = []
    if latest:
        start = date.fromisoformat(latest)
        for i in range(1, 4):
            projected.append((start + timedelta(days=avg * i)).isoformat())

    payload = {
        "status": "ok" if context else "no_data",
        "history": history,
        "avg_cycle_length": avg,
        "has_enough_history": len(history) >= 2,
        "projected": projected,
        "today": date.today().isoformat(),
    }
    if context:
        payload.update({
            "phase": context["phase"],
            "cycle_day": context["cycle_day"],
            "days_late": context["days_late"],
            "next_expected_date": context["next_expected_date"],
        })
    return jsonify(payload)


@app.route("/cycle_delete", methods=["POST"])
@login_required
def cycle_delete():
    user_id, _ = ensure_device_id()
    data = request.get_json(force=True)
    target = data.get("period_start_date")
    if not target:
        return jsonify({"status": "error", "message": "No date given."}), 400
    delete_period_entry(user_id, target)
    return jsonify({"status": "ok"})


@app.route("/history")
@login_required
def history():
    """Past conversation for this account, so the transcript survives a reload."""
    user_id, _ = ensure_device_id()
    return jsonify({"status": "ok", "email": session.get("email"),
                    "messages": chat_store.get_history(user_id)})


@app.route("/delete_my_data", methods=["POST"])
@login_required
def delete_my_data():
    """
    Participants were promised control over their own data - this makes
    that real rather than a claim in the privacy copy.
    """
    user_id, _ = ensure_device_id()
    chat_store.delete_history(user_id)
    delete_cycle_history(user_id)
    return jsonify({"status": "ok", "message": "Your chat history and cycle data have been deleted."})


if __name__ == "__main__":
    app.run(debug=True, port=5000)