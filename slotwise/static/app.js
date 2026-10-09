'use strict';
const $ = id => document.getElementById(id);
let config, session, busy = false, pollTimer;

async function api(path, data) {
  const response = await fetch(path, {method: data === undefined ? 'GET' : 'POST',
    headers: data === undefined ? {} : {'Content-Type': 'application/json',
      ...(path === '/api/evals' && config?.eval_requires_token ? {'X-Slotwise-Operator': $('operator-token').value} : {})},
    body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Invalid request. Please check your message.');
  return result;
}

function node(tag, text, cls) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (cls) element.className = cls;
  return element;
}

function slotTime(slot) {
  return new Intl.DateTimeFormat('en-IN', {timeZone:'Asia/Kolkata', weekday:'short',
    day:'numeric', month:'short', hour:'numeric', minute:'2-digit'}).format(new Date(slot.starts_at));
}

function setBusy(value) {
  busy = value;
  $('send').disabled = value || !config.ready;
  $('message').disabled = value || !config.ready;
  $('new-chat').disabled = value;
  $('send').firstChild.textContent = value ? 'Working… ' : 'Send ';
  for (const button of $('appointment-options').querySelectorAll('button')) button.disabled = value;
}

function renderChat() {
  $('messages').replaceChildren();
  for (const message of session.messages) {
    const item = node('div', undefined, 'message ' + (message.role === 'patient' ? 'patient' : 'assistant'));
    item.append(node('div', message.role === 'patient' ? 'YOU' : 'SLOTWISE', 'speaker'), node('div', message.text, 'bubble'));
    $('messages').append(item);
  }
  $('messages').scrollTop = $('messages').scrollHeight;
  $('state-label').textContent = session.state.replaceAll('_', ' ');
  $('appointment-options').replaceChildren();
  if (session.pending) {
    const box = node('div', undefined, 'confirmation-card');
    box.append(node('strong', 'Review your appointment'), node('p', `${session.pending.doctor} · ${slotTime(session.pending)} IST · 30 minutes`));
    const button = node('button', 'Confirm appointment', 'button primary');
    button.type = 'button';
    button.addEventListener('click', () => send('confirm appointment', {confirm_slot: session.pending.id}));
    box.append(button);
    $('appointment-options').append(box);
  } else if (session.state === 'offered') {
    for (const slot of session.offered) {
      const button = node('button', undefined, 'slot-option');
      button.type = 'button';
      const text = node('span');
      text.append(node('strong', slotTime(slot) + ' IST'), node('small', `${slot.doctor} · ${slot.specialty} · 30 min`));
      button.append(text, node('span', 'Review →'));
      button.addEventListener('click', () => send('Choose appointment', {select_slot: slot.id}));
      $('appointment-options').append(button);
    }
  }
  const detail = session.receipt || session.pending;
  $('visit-details').replaceChildren();
  const add = (label, value) => $('visit-details').append(node('dt', label), node('dd', value));
  add('Clinic timezone', 'Asia/Kolkata (IST)');
  if (detail) {
    add('Doctor', detail.doctor); add('Appointment', slotTime(detail));
    add('Specialty', detail.specialty); add('Location', detail.location);
    if (session.receipt) add('Booking reference', detail.id);
  }
  $('visit-description').textContent = session.receipt ? 'Your appointment is booked. Keep your reference.' :
    session.pending ? 'Check these details before confirming.' : 'We’ll confirm the doctor, date, time, and location together.';
  $('visit-title').textContent = session.receipt ? 'Your visit is confirmed.' : session.pending ? 'Ready to review.' : 'Details take shape here.';
}

async function newChat() {
  $('chat-error').textContent = '';
  try { session = await api('/api/session', {}); renderChat(); }
  catch (error) { $('chat-error').textContent = error.message; }
}

async function send(text, extras = {}) {
  if (busy || !text.trim()) return;
  setBusy(true);
  $('chat-error').textContent = '';
  const pending = node('div', undefined, 'message pending');
  pending.append(node('div', 'SLOTWISE', 'speaker'), node('div', 'Finding the next safe step…', 'bubble'));
  $('messages').append(pending);
  $('messages').scrollTop = $('messages').scrollHeight;
  try {
    session = await api('/api/message', {text, ...extras});
    $('message').value = '';
    renderChat();
  } catch (error) {
    pending.remove();
    $('chat-error').textContent = error.message;
  } finally { setBusy(false); $('message').focus(); }
}

function view(name) {
  $('chat-view').hidden = name !== 'chat'; $('eval-view').hidden = name !== 'eval';
  for (const key of ['chat', 'eval']) {
    $(key + '-nav').classList.toggle('active', key === name);
    if (key === name) $(key + '-nav').setAttribute('aria-current', 'page');
    else $(key + '-nav').removeAttribute('aria-current');
  }
  if (name === 'eval') refreshEval();
}

function resultLabel(result) { return `${result.score} · ${result.passed ? 'Pass' : 'Fail'}`; }

function showEvidence(before, after) {
  const panel = $('evidence-detail'); panel.hidden = false; panel.replaceChildren();
  const heading = node('div', undefined, 'evidence-heading');
  heading.append(node('h2', before.title));
  const close = node('button', 'Close evidence', 'button secondary');
  close.addEventListener('click', () => {panel.hidden = true;}); heading.append(close); panel.append(heading);
  const columns = node('div', undefined, 'evidence-columns');
  for (const [label, result] of [['Before', before], ['After', after]]) {
    const column = node('div');
    column.append(node('h3', `${label} · ${resultLabel(result)}`));
    if (result.failure_code) column.append(node('p', result.failure_code, 'result-fail'));
    for (const message of result.transcript) {
      const line = node('div', undefined, 'trace-transcript');
      line.append(node('strong', message.role === 'patient' ? 'Patient' : 'SlotWise'), node('p', message.text));
      column.append(line);
    }
    for (const [title, data] of [['Assertions', result.checks], ['Tool & consent events', result.events], ['Database rows', result.database]]) {
      const details = node('details'); details.append(node('summary', title), node('pre', JSON.stringify(data, null, 2))); column.append(details);
    }
    columns.append(column);
  }
  panel.append(columns); panel.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block:'start'});
}

function renderReport(report) {
  $('eval-empty').hidden = true; $('eval-results').hidden = false;
  $('evidence-label').textContent = report.evidence_notice + ' · ' + report.repeats + ' repetition(s) · ' + report.run_id;
  $('before-score').textContent = report.before.score + '/100'; $('after-score').textContent = report.after.score + '/100';
  $('before-pass').textContent = `${report.before.passed}/${report.before.total} scenarios passed`;
  $('after-pass').textContent = `${report.after.passed}/${report.after.total} scenarios passed`;
  $('promotion-state').textContent = report.promotion.accepted ? 'Promoted' : 'Rejected';
  $('regression-count').textContent = `${report.promotion.regressions.length} regressions · ${report.promotion.safety_ok ? 'safety checks passed' : 'safety gate failed'}`;
  $('patch-code').textContent = JSON.stringify(report.patch, null, 2);
  $('scenario-rows').replaceChildren();
  for (const before of report.before.results) {
    const after = report.after.results.find(r => r.scenario_id === before.scenario_id && r.repeat === before.repeat);
    const row = node('tr'), name = node('td');
    name.append(node('strong', before.title), node('small', `Run ${before.repeat + 1}`));
    row.append(name, node('td', before.split), node('td', resultLabel(before), before.passed ? 'result-pass' : 'result-fail'),
      node('td', resultLabel(after), after.passed ? 'result-pass' : 'result-fail'));
    const cell = node('td'), button = node('button', 'Inspect', 'evidence-button');
    button.setAttribute('aria-label', 'Inspect ' + before.title + ', run ' + (before.repeat + 1));
    button.addEventListener('click', () => showEvidence(before, after)); cell.append(button); row.append(cell);
    $('scenario-rows').append(row);
  }
}

async function refreshEval() {
  clearTimeout(pollTimer);
  try {
    const status = await api('/api/evals');
    $('eval-progress').textContent = status.job.progress;
    $('run-eval').disabled = status.job.status === 'running' || !config.ready || !config.eval_enabled;
    $('repeats').disabled = status.job.status === 'running';
    $('eval-error').textContent = status.job.error || '';
    if (status.report) {
      renderReport(status.report);
      if (status.saved_evidence) $('evidence-label').textContent += ' · saved run evidence';
    }
    if (status.job.status === 'running') pollTimer = setTimeout(refreshEval, 1200);
  } catch (error) { $('eval-error').textContent = error.message; }
}

$('chat-form').addEventListener('submit', event => {event.preventDefault(); send($('message').value);});
$('message').addEventListener('keydown', event => {if (event.key === 'Enter' && !event.shiftKey) {event.preventDefault(); send($('message').value);}});
$('new-chat').addEventListener('click', newChat);
$('chat-nav').addEventListener('click', () => view('chat'));
$('eval-nav').addEventListener('click', () => view('eval'));
$('run-eval').addEventListener('click', async () => {
  $('eval-error').textContent = ''; $('run-eval').disabled = true;
  try { await api('/api/evals', {repeats:Number($('repeats').value)}); refreshEval(); }
  catch (error) { $('eval-error').textContent = error.message; $('run-eval').disabled = false; }
});

(async () => {
  try {
    config = await api('/api/config');
    $('operator-controls').hidden = !config.eval_requires_token;
    $('mode-badge').textContent = config.mode === 'live' ? 'LIVE · ' + config.provider_label.toUpperCase() : 'OFFLINE · SCRIPTED';
    $('mode-notice').textContent = config.mode === 'offline' ?
      'Offline scripted demo. This exercises scheduling and eval mechanics; it does not measure LLM quality.' :
      config.ready ? `Live ${config.provider_label} · ${config.model} · synthetic patients only. Scheduling demo; no real clinic or staff connection.` :
      `${config.provider_label} key missing. Add ${config.key_name} to .env and restart. Live chat and evals are unavailable until configured.`;
    if (config.fresh_demo) $('mode-notice').textContent +=
      ' Recording mode: each new conversation has a separate clinic with fresh synthetic slots.';
    $('mode-notice').classList.toggle('warning', !config.ready || config.mode === 'offline');
    $('clinic-date').textContent = 'Clinic date: ' + config.today;
    await newChat(); setBusy(false);
  } catch (error) { $('mode-notice').textContent = error.message; }
})();
