/* PREN1 Team 7 – Simulator-Oberfläche. Reines JavaScript, keine externen Bibliotheken (offline-fähig). */
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const fmt = (x, d = 2) => (x === null || x === undefined || Number.isNaN(x) ? '–' : Number(x).toFixed(d));
const deg = r => r * 180 / Math.PI;
const wrap = a => Math.atan2(Math.sin(a), Math.cos(a));

async function api(path, body) {
  try {
    const r = await fetch('/api/' + path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return await r.json();
  } catch (e) { console.warn(path, e); return null; }
}

/* ------------------------------------------------------------------ Zustand */
let snap = null;
let trailTrue = [], trailOdom = [], epoch = -1;
let logSeen = new Set(), logRows = [];
const srcOn = { SBC: true, MCU: true, REFEREE: true, WORLD: false, OPERATOR: true };
let prevPose = 'STAND', curPoseFrom = 'STAND', lastEdge = null, lastStateT = 0;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

/* ------------------------------------------------------------------ Verbindung */
function connect() {
  const es = new EventSource('/api/stream');
  es.onopen = () => setConn(true);
  es.onerror = () => setConn(false);
  es.onmessage = ev => { try { onSnap(JSON.parse(ev.data)); } catch (e) { console.error(e); } };
}
function setConn(ok) {
  const c = $('#conn'); c.textContent = ok ? '● verbunden' : '● getrennt'; c.className = 'chip ' + (ok ? 'ok' : 'bad');
}

function onSnap(s) {
  if (s.epoch !== epoch) {                   // Neustart / neues Szenario
    epoch = s.epoch; trailTrue = []; trailOdom = []; logSeen = new Set(); logRows = []; $('#logTbl tbody').innerHTML = '';
  }
  if (s.trail_true) { trailTrue = s.trail_true.slice(); trailOdom = s.trail_odom.slice(); }
  else {
    pushTrail(trailTrue, s.robot.x, s.robot.y); pushTrail(trailOdom, s.odom.x, s.odom.y);
  }
  if (snap && s.brain.state !== snap.brain.state) { lastEdge = [snap.brain.state, s.brain.state]; lastStateT = performance.now(); }
  if (snap && s.robot.pose !== 'MOVING' && s.robot.pose !== snap.robot.pose) curPoseFrom = snap.robot.pose === 'MOVING' ? curPoseFrom : snap.robot.pose;
  if (s.robot.pose !== 'MOVING') prevPose = s.robot.pose;
  snap = s;
  render();
}
function pushTrail(a, x, y) {
  const l = a[a.length - 1];
  if (!l || Math.hypot(l[0] - x, l[1] - y) > 0.02) { a.push([x, y]); if (a.length > 900) a.splice(0, 200); }
}

/* ------------------------------------------------------------------ Rendern (DOM) */
function render() {
  const s = snap; if (!s) return;
  $('#simtime').textContent = 't = ' + fmt(s.t, 1) + ' s';
  $('#load').textContent = 'CPU ' + Math.round(s.load * 100) + ' %';
  $('#btnPause').textContent = s.paused ? '▶ Weiter' : '⏸ Pause';
  const sp = $('#speed');
  if (document.activeElement !== sp) {
    if (![...sp.options].some(o => +o.value === s.speed)) sp.add(new Option(s.speed + '×', String(s.speed)));
    sp.value = String(s.speed);
  }

  const b = s.brain, st = b.state;
  const sb = $('#stateBadge'); sb.textContent = st; sb.classList.toggle('estop', st === 'NOT_AUS');
  $('#poseBadge').textContent = 'Haltung: ' + ({ STAND: 'Stand (AUF)', SITZ: 'Sitz', PLATZ: 'Platz', MOVING: 'Wechsel …' }[s.robot.pose] || s.robot.pose);
  const ob = $('#outBadge');
  if (b.output && s.t - b.output.t < 2.5 && b.output.t >= 0) { ob.hidden = false; ob.textContent = `♪ ${b.output.sound} · LED ${b.output.led} · Augen ${b.output.eyes}`; } else ob.hidden = true;
  const bn = $('#banner');
  if (st === 'NOT_AUS') { bn.hidden = false; bn.textContent = b.fault === 'LINK' ? 'FEHLER: Verbindung zum Mikrocontroller verloren' : 'NOT-AUS aktiv'; } else bn.hidden = true;
  $('#btnEstop').classList.toggle('pressed', s.mcu.hw_button);
  $('#estopActions').hidden = !(s.mcu.estop || s.mcu.hw_button);

  // Status wie Folie 8
  $('#statusBox').textContent = `command = ${b.command}\nrobot_state = ${b.robot_state}${b.sub ? '  (' + b.sub + ')' : ''}\ntarget = ${b.target}\nconfidence = ${fmt(b.confidence)}`;
  $('#confBar').style.width = Math.round(b.confidence * 100) + '%';

  renderFsm();
  renderKV('#percept', [
    ['zuletzt gehört', s.brain.heard.word ? `${s.brain.heard.word} (${fmt(s.brain.heard.conf)})` : '–'],
    ['Distanzsensor', s.tof === null ? 'kein Echo' : fmt(s.tof) + ' m'],
    ['Knochen im Bild', s.detect ? `${fmt(deg(s.detect.bearing), 0)}°, ${fmt(s.detect.dist)} m, ${fmt(s.detect.conf)}` : 'nein'],
    ['Ziel (Schätzung)', s.target ? `(${fmt(s.target.x)} | ${fmt(s.target.y)}) m` : '–'],
    ['Kamera / Mikrofon', (s.env.camera_ok ? 'ok' : 'AUS') + ' / ' + (s.env.mic_ok ? 'ok' : 'AUS'), !(s.env.camera_ok && s.env.mic_ok)],
  ]);
  const dpos = Math.hypot(s.odom.x - s.robot.x, s.odom.y - s.robot.y) * 100, dth = Math.abs(deg(wrap(s.odom.th - s.robot.th)));
  renderKV('#mcu', [
    ['Not-Aus', s.mcu.estop ? 'AUSGELÖST (' + s.mcu.estop_src + ')' : 'frei', s.mcu.estop],
    ['v / ω Soll', `${fmt(s.mcu.v_set)} m/s · ${fmt(s.mcu.w_set)} rad/s`],
    ['Räder L / R', `${fmt(s.robot.wl, 1)} / ${fmt(s.robot.wr, 1)} rad/s`],
    ['Duty L / R', `${fmt(s.mcu.u_l)} / ${fmt(s.mcu.u_r)}`],
    ['Odometrie-Fehler', `${fmt(dpos, 1)} cm · ${fmt(dth, 1)}°`],
    ['UART', s.mcu.link_up ? `ok (↑${s.mcu.tx} ↓${s.mcu.rx})` : 'GETRENNT', !s.mcu.link_up],
  ]);
  const avgW = s.t > 5 ? s.battery.wh / s.t * 3600 : s.battery.power_w;
  const mins = avgW > 0 ? 38.4 / avgW * 60 : 0;
  $('#socBar').style.width = Math.round(s.battery.soc * 100) + '%';
  renderKV('#energy', [
    ['Akku', `${fmt(s.battery.soc * 100, 1)} %  (${fmt(s.battery.wh, 2)} Wh verbraucht)`],
    ['Leistung', `${fmt(s.battery.power_w, 1)} W (Ø ${fmt(avgW, 1)} W)`],
    ['Laufzeit (Hochrechnung)', `${fmt(mins, 0)} min  (≥ 12 min gefordert)`, mins < 12],
  ]);

  syncControls(s);
  appendLog(s.events);
  renderReq(s);
  renderScenarioStatus(s);
}
function renderKV(sel, rows) {
  const el = $(sel); let h = '';
  for (const [k, v, bad] of rows) h += `<dt>${k}</dt><dd class="${bad ? 'bad' : ''}">${v}</dd>`;
  el.innerHTML = h;
}

/* ------------------------------------------------------------------ Zustandsautomat (SVG) */
const FSM = {
  INIT: [8, 6], BEREIT: [112, 6], PLATZ: [216, 6],
  HIER: [8, 62], DREHEN: [112, 62], SUCHEN: [216, 62],
  RUECKKEHR: [8, 118], FUND_MELDEN: [112, 118], ANFAHREN: [216, 118],
  KUNSTSTUECK: [8, 174], NOT_AUS: [216, 174],
};
const FW = 100, FH = 26;
const FSM_EDGES = [
  ['INIT', 'BEREIT', 'Selbsttest'], ['BEREIT', 'PLATZ', 'Geste PLATZ'], ['PLATZ', 'BEREIT', 'AUF / SITZ'],
  ['BEREIT', 'HIER', 'HIER'], ['HIER', 'BEREIT', 'am Ziel'], ['BEREIT', 'DREHEN', 'SUCH'], ['DREHEN', 'SUCHEN'],
  ['SUCHEN', 'ANFAHREN', 'Knochen'], ['ANFAHREN', 'FUND_MELDEN', 'berührt'], ['FUND_MELDEN', 'RUECKKEHR'],
  ['RUECKKEHR', 'BEREIT', 'sitzen'], ['BEREIT', 'KUNSTSTUECK', 'Zusatz'], ['KUNSTSTUECK', 'BEREIT'],
  ['ANFAHREN', 'SUCHEN', 'verloren'], ['NOT_AUS', 'BEREIT', 'Reset'],
];
function buildFsm() {
  const svg = $('#fsm');
  let h = `<defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="${css('--muted')}"/></marker>
  <marker id="arrHot" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="${css('--accent')}"/></marker></defs>`;
  const c = n => [FSM[n][0] + FW / 2, FSM[n][1] + FH / 2];
  const clip = (n, dx, dy) => {         // Schnittpunkt Strahl vom Zentrum mit dem Rechteck
    const sx = (FW / 2) / Math.abs(dx || 1e-9), sy = (FH / 2) / Math.abs(dy || 1e-9), k = Math.min(sx, sy);
    return [c(n)[0] + dx * k, c(n)[1] + dy * k];
  };
  FSM_EDGES.forEach(([a, b, lab], i) => {
    const [ax, ay] = c(a), [bx, by] = c(b); let dx = bx - ax, dy = by - ay; const len = Math.hypot(dx, dy) || 1;
    const px = -dy / len * 4, py = dx / len * 4;           // seitlicher Versatz gegen Überdeckung
    const p1 = clip(a, dx, dy), p2 = clip(b, -dx, -dy);
    const dash = a === 'NOT_AUS' ? ' dash' : '';
    h += `<path class="edge${dash}" id="e_${a}_${b}" d="M${p1[0] + px},${p1[1] + py} L${p2[0] + px},${p2[1] + py}"/>`;
    if (lab) h += `<text class="elabel" x="${(p1[0] + p2[0]) / 2 + px * 2.2}" y="${(p1[1] + p2[1]) / 2 + py * 2.2}">${lab}</text>`;
  });
  for (const [n, [x, y]] of Object.entries(FSM)) {
    h += `<g class="node" id="n_${n}"><rect x="${x}" y="${y}" width="${FW}" height="${FH}" rx="6"/><text x="${x + FW / 2}" y="${y + FH / 2}">${n.replace('_', ' ')}</text></g>`;
  }
  h += `<text class="elabel" x="165" y="207">Not-Aus wirkt aus jedem Zustand (Hardware im MCU)</text>`;
  svg.innerHTML = h;
}
function renderFsm() {
  const st = snap.brain.state;
  for (const n of Object.keys(FSM)) {
    const g = $('#n_' + n); if (!g) continue;
    g.classList.toggle('act', n === st && n !== 'NOT_AUS');
    g.classList.toggle('fail', n === st && n === 'NOT_AUS');
  }
  $$('#fsm .edge').forEach(e => e.classList.remove('hot'));
  if (lastEdge && performance.now() - lastStateT < 2500) { const e = $(`#e_${lastEdge[0]}_${lastEdge[1]}`); if (e) e.classList.add('hot'); }
}

/* ------------------------------------------------------------------ Bedienelemente */
function lightFromSlider(v) { return Math.round(Math.pow(10, 1 + v / 100 * 2.3)); }     // 10 .. 2000 lx
function sliderFromLight(l) { return Math.round((Math.log10(Math.max(l, 10)) - 1) / 2.3 * 100); }
let sliderLock = 0;
function syncControls(s) {
  if (performance.now() < sliderLock) return;
  const e = s.env;
  if (document.activeElement !== $('#rNoise')) { $('#rNoise').value = e.noise_db; }
  if (document.activeElement !== $('#rLight')) { $('#rLight').value = sliderFromLight(e.light_lux); }
  if (document.activeElement !== $('#rRef')) { $('#rRef').value = e.referee_distance; }
  if (document.activeElement !== $('#rFloor')) { $('#rFloor').value = e.floor_similarity * 100; }
  $('#oNoise').textContent = Math.round(e.noise_db) + ' dB'; $('#oLight').textContent = Math.round(e.light_lux) + ' lx';
  $('#oRef').textContent = fmt(e.referee_distance, 1) + ' m'; $('#oFloor').textContent = Math.round(e.floor_similarity * 100) + ' %';
  $$('[data-fail]').forEach(c => { c.checked = !e[c.dataset.fail]; });
}
function initControls() {
  $$('[data-say]').forEach(b => b.onclick = () => api('say', { word: b.dataset.say }));
  $$('[data-gesture]').forEach(b => b.onclick = () => api('gesture', { name: b.dataset.gesture }));
  $('#btnStart').onclick = () => api('button', {});
  $('#btnEstop').onclick = () => api('estop', {});
  $('#btnRelease').onclick = () => api('estop_release', {});
  $('#btnEstopReset').onclick = () => api('estop_reset', {});
  $('#btnPause').onclick = () => api('sim', { paused: !(snap && snap.paused) });
  $('#btnReset').onclick = () => api('sim', { reset: true, seed: snap ? snap.seed : null });
  $('#speed').onchange = e => api('sim', { speed: +e.target.value });
  $('#btnTheme').onclick = () => {
    const d = document.documentElement, cur = d.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    d.dataset.theme = cur === 'dark' ? 'light' : 'dark'; try { localStorage.setItem('theme', d.dataset.theme); } catch (e) { /* egal */ }
    buildFsm();
  };
  const bindSlider = (id, key, conv = v => +v) => {
    $(id).oninput = e => { sliderLock = performance.now() + 600; api('env', { [key]: conv(e.target.value) }); };
  };
  bindSlider('#rNoise', 'noise_db'); bindSlider('#rLight', 'light_lux', lightFromSlider);
  bindSlider('#rRef', 'referee_distance'); bindSlider('#rFloor', 'floor_similarity', v => v / 100);
  $$('[data-fail]').forEach(c => c.onchange = () => api('env', { [c.dataset.fail]: !c.checked }));
  $('#btnBoneRandom').onclick = () => api('bone', { random: true });
  $('#btnBoneFar').onclick = () => { const a = 0.22 * (Math.random() < .5 ? -1 : 1); api('bone', { x: 4.5 * Math.cos(a), y: 4.5 * Math.sin(a), th: Math.random() * 6.28 - 3.14 }); };
  $('#btnBoneOut').onclick = () => api('bone', { x: 1.5, y: 3.2, th: 0 });
  window.addEventListener('keydown', e => {
    if (/INPUT|SELECT|TEXTAREA/.test(e.target.tagName) && e.target.type !== 'range' && e.target.type !== 'checkbox') return;
    const k = e.key.toLowerCase();
    const m = { '1': ['say', { word: 'HIER' }], '2': ['say', { word: 'BRAV' }], '3': ['say', { word: 'SITZ' }], '4': ['say', { word: 'SUCH' }],
      '5': ['say', { word: 'KUNSTSTUECK' }], q: ['gesture', { name: 'SITZ' }], w: ['gesture', { name: 'PLATZ' }], e: ['gesture', { name: 'AUF' }],
      n: ['estop', {}], s: ['button', {}] }[k];
    if (m) { api(m[0], m[1]); e.preventDefault(); }
    if (k === ' ') { api('sim', { paused: !(snap && snap.paused) }); e.preventDefault(); }
  });
  // Tabs
  $$('#tabs button').forEach(b => b.onclick = () => {
    $$('#tabs button').forEach(x => x.classList.toggle('on', x === b));
    $$('.pane').forEach(p => p.classList.toggle('on', p.id === 'pane-' + b.dataset.tab));
  });
  // Log-Filter
  const f = $('#logFilters');
  for (const k of Object.keys(srcOn)) {
    const l = document.createElement('label'); l.textContent = k; l.className = srcOn[k] ? 'on' : '';
    l.onclick = () => { srcOn[k] = !srcOn[k]; l.classList.toggle('on', srcOn[k]); rebuildLog(); };
    f.appendChild(l);
  }
}

/* ------------------------------------------------------------------ Protokoll */
function logRowHtml(e) {
  const m = Math.floor(e.t / 60), sec = (e.t % 60).toFixed(1).padStart(4, '0');
  return `<tr class="k-${e.kind}"><td class="t">${m}:${sec}</td><td class="s src-${e.src}">${e.src}</td><td>${e.text.replace(/</g, '&lt;')}</td></tr>`;
}
function appendLog(evs) {
  const box = $('#logBox'), tb = $('#logTbl tbody');
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  let added = false;
  for (const e of evs) {
    if (logSeen.has(e.id)) continue; logSeen.add(e.id); logRows.push(e);
    if (srcOn[e.src]) { tb.insertAdjacentHTML('beforeend', logRowHtml(e)); added = true; }
  }
  if (logRows.length > 600) logRows.splice(0, logRows.length - 600);
  while (tb.rows.length > 600) tb.deleteRow(0);
  if (added && atBottom) box.scrollTop = box.scrollHeight;
}
function rebuildLog() { $('#logTbl tbody').innerHTML = logRows.filter(e => srcOn[e.src]).map(logRowHtml).join(''); const b = $('#logBox'); b.scrollTop = b.scrollHeight; }

/* ------------------------------------------------------------------ Anforderungen */
const STATUS = { pass: 'erfüllt', fail: 'nicht erfüllt', warn: 'Warnung', open: 'offen' };
function renderReq(s) {
  const sm = s.checks_summary;
  $('#reqCount').textContent = `${sm.pass}✓ ${sm.fail ? sm.fail + '✗' : ''}`.trim();
  $('#reqSum').innerHTML = `<span class="badge pass">${sm.pass} erfüllt</span><span class="badge fail">${sm.fail} nicht erfüllt</span><span class="badge warn">${sm.warn} Warnung</span><span class="badge open">${sm.open} offen</span>
    <span class="hint">Orientierungswert Wettbewerb (Annahme, ohne Publikumswertung): <b>${s.score.total_ohne_zusatz} / 80</b> Punkte (Grundbefehle ${s.score.grundbefehle}, Suche ${s.score.suche})</span>`;
  const key = JSON.stringify(s.checks);
  if (renderReq.key === key) return; renderReq.key = key;
  $('#reqTbl tbody').innerHTML = s.checks.map(c => `<tr><td class="mono">${c.anf}</td><td>${c.text}</td><td><span class="badge ${c.status}">${STATUS[c.status]}</span></td><td class="mono">${c.value}</td><td class="mono">${c.limit}</td></tr>`).join('');
}

/* ------------------------------------------------------------------ Szenarien */
let scenarios = [];
async function loadScenarios() {
  scenarios = (await api('scenarios')) || [];
  $('#scnBox').innerHTML = '<div class="cards">' + scenarios.map(sc => `<div class="scn"><h4>${sc.title}</h4><p>${sc.description}</p>
    <button class="btn cmd" data-scn="${sc.id}">▶ Szenario starten</button><div class="prog" id="prog_${sc.id}"></div></div>`).join('') + '</div>';
  $$('[data-scn]').forEach(b => b.onclick = () => api('scenario', { id: b.dataset.scn }));
}
function renderScenarioStatus(s) {
  $$('.prog').forEach(p => p.textContent = '');
  const sc = s.scenario; if (!sc) return;
  const cur = scenarios.find(x => sc.name === x.title); if (!cur) return;
  const el = $('#prog_' + cur.id); if (!el) return;
  let h = sc.running ? `läuft … Schritt ${sc.step}/${sc.steps}` : (sc.result ? (sc.result.passed ? '<b style="color:var(--ok)">BESTANDEN</b>' : '<b style="color:var(--bad)">NICHT BESTANDEN</b>') : 'beendet');
  h += '<br>' + sc.results.map(r => `${r.ok || r.optional ? '✓' : '✗'} ${r.step}${r.attempts > 1 ? ' (' + r.attempts + '×)' : ''}`).join('<br>');
  el.innerHTML = h;
}

/* ------------------------------------------------------------------ Tests */
let jobTimer = null;
async function startJob(kind) {
  const n = +$('#tN').value || 100;
  await api('test/' + kind, { n }); pollJobs(kind);
}
function pollJobs(kind) {
  clearInterval(jobTimer);
  jobTimer = setInterval(async () => {
    const jobs = await api('jobs'); const j = jobs && jobs[kind]; if (!j) return;
    $('#tState').textContent = j.state === 'running' ? `läuft … ${Math.round(j.progress * 100)} %` : (j.state === 'error' ? 'Fehler: ' + j.error : 'fertig');
    if (j.state !== 'running') { clearInterval(jobTimer); renderJob(j); }
  }, 600);
}
const heatCls = v => v >= .9 ? 'g' : v >= .6 ? 'y' : 'r';
function renderJob(j) {
  const r = j.result, o = $('#tOut'); if (!r) return;
  if (j.kind === 'voice' || j.kind === 'gesture') {
    const isV = j.kind === 'voice'; const items = isV ? [...new Set(r.rows.map(x => x.word))] : [...new Set(r.rows.map(x => x.gesture))];
    const conds = isV ? [...new Set(r.rows.map(x => x.noise_db))] : [...new Set(r.rows.map(x => x.light_lux))];
    const dists = [...new Set(r.rows.map(x => x.distance))];
    let h = `<p class="hint">Anf. ${r.anf} – Anteil korrekt erkannter Befehle (Schwelle ${Math.round(r.pass_rate * 100)} % = Annahme). Zellen: ${isV ? 'Lärm × Distanz' : 'Licht × Distanz'}.</p>`;
    h += '<table class="heat"><tr><th></th>' + conds.map(c => `<th colspan="${dists.length}">${isV ? c + ' dB(A)' : c + ' lx'}</th>`).join('') + '</tr><tr><th></th>' +
      conds.map(() => dists.map(d => `<th>${d} m</th>`).join('')).join('') + '</tr>';
    for (const it of items) {
      h += `<tr><th>${it}</th>`;
      for (const c of conds) for (const d of dists) {
        const x = r.rows.find(y => (isV ? y.word : y.gesture) === it && (isV ? y.noise_db : y.light_lux) === c && y.distance === d);
        h += `<td class="${heatCls(x.correct)}">${Math.round(x.correct * 100)} %</td>`;
      }
      h += '</tr>';
    }
    h += '</table>';
    if (!isV) h += `<p class="hint">Fehlauslösungen ohne Geste: ${r.false_triggers_per_10min} in 10 min.</p>`;
    o.innerHTML = h;
  } else {
    const s = r.summary;
    o.innerHTML = `<p class="hint">Anf. ${r.anf} – ${s.runs} zufällige Suchläufe (Knochenlage, Licht, Lärm, Referee-Abstand variiert).</p>
      <table class="heat"><tr><th>Gefunden</th><th>Abgeschlossen</th><th>Ø Suchzeit</th><th>max. Suchzeit</th><th>max. Meldeverzug</th><th>max. Abweichung Start</th><th>Läufe mit Feldverlassen</th><th>Rechenzeit</th></tr>
      <tr><td class="${heatCls(s.found_rate)}">${Math.round(s.found_rate * 100)} %</td><td class="${heatCls(s.completed_rate)}">${Math.round(s.completed_rate * 100)} %</td><td>${s.search_time_mean} s</td><td>${s.search_time_max} s</td><td>${s.report_latency_max} s</td><td>${s.return_cm_max} cm</td><td>${s.outside_runs}</td><td>${s.wall_s} s für ${s.sim_s_total} s Sim.</td></tr></table>`;
  }
}

/* ------------------------------------------------------------------ Info */
async function loadInfo() {
  const i = (await api('info')) || {};
  $('#infBox').innerHTML = `
  <h3>Was ist das?</h3>
  <p>Digital Twin des Hunde-Roboters nach <b>Variante V2 «Verteilte Architektur»</b> (MS2): Ein Einplatinenrechner (Raspberry Pi 5) übernimmt Wahrnehmung und Zustandsautomat,
  ein Mikrocontroller alle zeitkritischen Aufgaben (Regelung, Servos, Not-Aus). Beide sind über ein Textprotokoll (<code>DRIVE v w</code>, <code>POSE SITZ</code>, …) verbunden – im Simulator wie später am Roboter.
  Der Simulator dient der Softwareentwicklung unabhängig von der Hardware und dem Test kritischer Teilfunktionen (Anf. 8.1, Rückmeldung MS1).</p>
  <h3>Wichtige Annahmen (siehe docs/ANNAHMEN.md)</h3><ul>
  <li>Suchsegment: Scheitel im Startfeld, Achse +x, 30°, 5 m. Hund startet mit dem Rücken zum Suchbereich (FAQ 9), Schiedsrichter 0.5–2 m <i>vor</i> dem Gesicht (FAQ 14).</li>
  <li>Erkennungsmodelle (Sprache, Geste, Knochen) sind parametrische Platzhalter, bis echte Messungen mit Mikrofon/Kamera vorliegen.</li>
  <li>Das <b>Kunststück</b> (Zusatzbefehl) ist noch nicht definiert – hier nur ein Platzhalter (Drehung + Freude, ≤ 1 Min).</li>
  <li>Akku-, Antriebs- und Zeitwerte sind Schätzungen (38.4 Wh, 41 cm Länge, 17 cm Spur, Haltungswechsel 1.2–1.8 s).</li></ul>
  <h3>Bedienung</h3><ul><li>Tasten: <code>1–5</code> Sprache, <code>Q W E</code> Gesten, <code>S</code> Start-Taster, <code>N</code> Not-Aus, <code>Leertaste</code> Pause.</li>
  <li>Knochen und Schiedsrichter im Spielfeld ziehen; Doppelklick setzt den Knochen.</li></ul>
  <h3>System</h3><p class="mono">Simulator ${i.version || '?'} · Python ${i.python || '?'} · ${i.platform || ''} (${i.machine || ''})</p>`;
}

/* ------------------------------------------------------------------ Spielfeld (Canvas) */
const cv = $('#arena'), ctx = cv.getContext('2d');
let view = { s: 100, ox: 0, oy: 0, w: 0, h: 0 };
const XMIN = -3.0, XMAX = 5.8, YMAX = 3.2;
function resize() {
  const r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  cv.width = Math.max(10, r.width * dpr); cv.height = Math.max(10, r.height * dpr);
  view.w = r.width; view.h = r.height;
  view.s = Math.min(r.width / (XMAX - XMIN), r.height / (2 * YMAX));
  view.ox = (r.width - view.s * (XMAX - XMIN)) / 2 - XMIN * view.s; view.oy = r.height / 2;
  view.dpr = dpr;
}
const sx = x => view.ox + x * view.s, sy = y => view.oy - y * view.s;
const wx = px => (px - view.ox) / view.s, wy = py => (view.oy - py) / view.s;

function drawArena() {
  requestAnimationFrame(drawArena);
  ctx.setTransform(view.dpr, 0, 0, view.dpr, 0, 0);
  ctx.clearRect(0, 0, view.w, view.h);
  const s = snap; if (!s) return;
  const S = view.s;
  // Raster
  if ($('#vGrid').checked) {
    ctx.lineWidth = 1; ctx.font = '10px ' + css('--sans'); ctx.fillStyle = css('--muted'); ctx.textAlign = 'center';
    for (let x = Math.ceil(XMIN * 2) / 2; x <= XMAX; x += 0.5) { ctx.strokeStyle = css('--grid'); ctx.globalAlpha = x % 1 === 0 ? 1 : .5; ctx.beginPath(); ctx.moveTo(sx(x), 0); ctx.lineTo(sx(x), view.h); ctx.stroke(); if (x % 1 === 0) ctx.fillText(x + ' m', sx(x), view.h - 4); }
    for (let y = -3; y <= 3; y += 0.5) { ctx.strokeStyle = css('--grid'); ctx.globalAlpha = y % 1 === 0 ? 1 : .5; ctx.beginPath(); ctx.moveTo(0, sy(y)); ctx.lineTo(view.w, sy(y)); ctx.stroke(); }
    ctx.globalAlpha = 1;
  }
  const F = s.field, half = F.angle / 2 * Math.PI / 180, ax = F.axis * Math.PI / 180;
  // Suchsegment
  ctx.beginPath(); ctx.moveTo(sx(0), sy(0)); ctx.arc(sx(0), sy(0), F.radius * S, -(ax + half), -(ax - half)); ctx.closePath();
  ctx.fillStyle = css('--sector'); ctx.fill(); ctx.strokeStyle = css('--sector-line'); ctx.setLineDash([6, 5]); ctx.lineWidth = 1.5; ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle = css('--sector-line'); ctx.font = '11px ' + css('--sans'); ctx.textAlign = 'center';
  ctx.fillText('Suchbereich 30° · 5 m', sx(F.radius * .62), sy(F.radius * .62 * Math.tan(half)) - 8);
  // Interaktionsbereich
  ctx.beginPath(); ctx.arc(sx(0), sy(0), F.interaction * S, 0, 7); ctx.strokeStyle = css('--muted'); ctx.globalAlpha = .6; ctx.setLineDash([3, 5]); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1;
  ctx.fillStyle = css('--muted'); ctx.fillText('Interaktionsbereich R 1.5 m', sx(-F.interaction * .72), sy(F.interaction * .72) - 6);
  // Startfeld
  ctx.strokeStyle = css('--fg'); ctx.lineWidth = 2; ctx.strokeRect(sx(-F.start_l / 2), sy(F.start_w / 2), F.start_l * S, F.start_w * S);
  ctx.fillStyle = css('--fg'); ctx.font = '10px ' + css('--sans'); ctx.fillText('Startfeld 20×50 cm', sx(0), sy(-F.start_w / 2) + 13);

  // Spuren
  if ($('#vTrail').checked) { drawPath(trailTrue, css('--accent'), 2, []); }
  if ($('#vOdom').checked) { drawPath(trailOdom, '#e08a1e', 1.5, [4, 4]); }

  drawReferee(s); drawBone(s); drawTarget(s); drawRobot(s);
  // Not-Aus Rahmen
  if (s.brain.state === 'NOT_AUS') { ctx.strokeStyle = css('--bad'); ctx.lineWidth = 6; ctx.strokeRect(3, 3, view.w - 6, view.h - 6); }
  drawSide(s);
}
function drawPath(a, col, w, dash) {
  if (a.length < 2) return; ctx.beginPath(); ctx.moveTo(sx(a[0][0]), sy(a[0][1]));
  for (let i = 1; i < a.length; i++) ctx.lineTo(sx(a[i][0]), sy(a[i][1]));
  ctx.strokeStyle = col; ctx.lineWidth = w; ctx.setLineDash(dash); ctx.stroke(); ctx.setLineDash([]);
}
function drawReferee(s) {
  const x = sx(s.referee.x), y = sy(s.referee.y), r = 0.2 * view.s;
  ctx.fillStyle = '#7a4bb5'; ctx.globalAlpha = .85; ctx.beginPath(); ctx.ellipse(x, y, r * .8, r * 1.3, 0, 0, 7); ctx.fill();
  ctx.fillStyle = '#e9c9a6'; ctx.beginPath(); ctx.arc(x + r * .25, y, r * .55, 0, 7); ctx.fill(); ctx.globalAlpha = 1;
  ctx.fillStyle = css('--fg'); ctx.font = '11px ' + css('--sans'); ctx.textAlign = 'center';
  ctx.fillText(`Schiedsrichter ${fmt(-s.referee.x, 1)} m`, x, y - r * 1.6 - 4);
}
function drawBone(s) {
  const b = s.bone, L = s.field.bone_l * view.s, W = s.field.bone_w * view.s;
  const x = sx(b.x), y = sy(b.y);
  ctx.save(); ctx.translate(x, y); ctx.rotate(-b.th);
  ctx.fillStyle = css('--bone'); ctx.strokeStyle = '#fff'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.roundRect(-L / 2, -W / 4, L, W / 2, W / 4); ctx.fill();
  for (const sg of [-1, 1]) for (const k of [-1, 1]) { ctx.beginPath(); ctx.arc(sg * L / 2, k * W / 3, W / 2.6, 0, 7); ctx.fill(); }
  ctx.restore();
  ctx.beginPath(); ctx.arc(x, y, 13, 0, 7); ctx.strokeStyle = css('--bone'); ctx.lineWidth = 1.5; ctx.setLineDash([3, 3]); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle = css('--fg'); ctx.font = '11px ' + css('--sans'); ctx.textAlign = 'center';
  ctx.fillText('Knochen' + (b.in_sector ? '' : ' (ausserhalb)'), x, y - 18);
}
function drawTarget(s) {
  if (!s.target) return;
  const x = sx(s.target.x), y = sy(s.target.y);
  ctx.strokeStyle = '#d4a000'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, 9, 0, 7); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(x - 5, y); ctx.lineTo(x + 5, y); ctx.moveTo(x, y - 5); ctx.lineTo(x, y + 5); ctx.stroke();
}
function drawRobot(s) {
  const r = s.robot, d = s.robot_dim, S = view.s;
  const cx = sx(r.x), cy = sy(r.y);
  // Sichtfeld, Distanzsensor
  ctx.save(); ctx.translate(cx, cy); ctx.rotate(-r.th);
  if ($('#vFov').checked && s.env.camera_ok) {
    const f = d.fov * Math.PI / 360, L = 3.2 * S, cxo = 0.18 * S;
    ctx.beginPath(); ctx.moveTo(cxo, 0); ctx.arc(cxo, 0, L, -f, f); ctx.closePath();
    ctx.fillStyle = 'rgba(224,170,30,.10)'; ctx.fill(); ctx.strokeStyle = 'rgba(224,170,30,.55)'; ctx.lineWidth = 1; ctx.stroke();
  }
  {
    const L = (s.tof === null ? 4 : s.tof) * S; ctx.strokeStyle = s.tof === null ? 'rgba(200,50,50,.25)' : '#d32f2f'; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(d.nose * S, 0); ctx.lineTo(d.nose * S + L, 0); ctx.stroke();
    if (s.tof !== null) { ctx.fillStyle = '#d32f2f'; ctx.beginPath(); ctx.arc(d.nose * S + L, 0, 3, 0, 7); ctx.fill(); }
  }
  if (s.detect && s.env.camera_ok) {      // Detektion der Kamera
    const bx = (0.18 + s.detect.dist * Math.cos(s.detect.bearing)) * S, by = -s.detect.dist * Math.sin(s.detect.bearing) * S;
    ctx.strokeStyle = '#d4a000'; ctx.lineWidth = 1; ctx.setLineDash([2, 3]); ctx.beginPath(); ctx.moveTo(0.18 * S, 0); ctx.lineTo(bx, by); ctx.stroke(); ctx.setLineDash([]);
  }
  // Räder
  const wr = d.wheel_r * S, wl = d.track * S / 2;
  for (const [side, phi] of [[1, r.phi_l], [-1, r.phi_r]]) {
    ctx.fillStyle = '#333'; ctx.fillRect(-wr, -side * wl - 3, wr * 2, 6);
    ctx.fillStyle = '#ddd'; const m = ((phi * wr) % (wr * 2)); ctx.fillRect(-wr + (m + wr * 2) % (wr * 2) - 1, -side * wl - 3, 2, 6);
  }
  // Körper (Haltung: Länge/Farbe)
  const col = { STAND: css('--robot'), SITZ: '#c98a14', PLATZ: '#3b78b8', MOVING: '#8a8f94' }[r.pose] || css('--robot');
  const Lb = d.length * S, Wb = d.width * S;
  ctx.fillStyle = col; ctx.globalAlpha = .92; ctx.beginPath(); ctx.roundRect(-Lb / 2 + 0.02 * S, -Wb / 2, Lb - 0.06 * S, Wb, Wb / 3); ctx.fill(); ctx.globalAlpha = 1;
  ctx.fillStyle = col; ctx.strokeStyle = 'rgba(0,0,0,.35)'; ctx.lineWidth = 1;                      // Kopf
  ctx.beginPath(); ctx.arc(d.nose * S - 0.045 * S, 0, 0.07 * S, 0, 7); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(d.nose * S - 0.025 * S, -0.03 * S, 0.012 * S + 1, 0, 7); ctx.arc(d.nose * S - 0.025 * S, 0.03 * S, 0.012 * S + 1, 0, 7); ctx.fill();
  ctx.fillStyle = '#222'; ctx.beginPath(); ctx.arc(d.nose * S + 0.01 * S, 0, 0.012 * S + 1, 0, 7); ctx.fill();   // Nase
  ctx.fillStyle = col;                                                                               // Ohren
  ctx.beginPath(); ctx.ellipse(d.nose * S - 0.09 * S, -0.075 * S, 0.03 * S, 0.018 * S, 0.4, 0, 7); ctx.ellipse(d.nose * S - 0.09 * S, 0.075 * S, 0.03 * S, 0.018 * S, -0.4, 0, 7); ctx.fill();
  // Schwanz
  const wag = s.robot.show ? Math.sin(performance.now() / 70) * 0.7 : 0;
  ctx.strokeStyle = col; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(-Lb / 2 + 0.02 * S, 0); ctx.lineTo(-Lb / 2 - 0.07 * S, Math.sin(wag) * 0.05 * S + wag * 3); ctx.stroke();
  ctx.restore();
  // Odometrie-Geist
  if ($('#vOdom').checked) {
    ctx.save(); ctx.translate(sx(s.odom.x), sy(s.odom.y)); ctx.rotate(-s.odom.th); ctx.strokeStyle = '#e08a1e'; ctx.setLineDash([3, 3]); ctx.lineWidth = 1.2;
    ctx.strokeRect(-d.length * S / 2, -d.width * S / 2, d.length * S, d.width * S); ctx.restore(); ctx.setLineDash([]);
  }
  ctx.fillStyle = css('--fg'); ctx.font = 'bold 11px ' + css('--sans'); ctx.textAlign = 'center';
  ctx.fillText(s.brain.state, cx, cy - Math.max(d.length, d.width) * S * .75 - 8);
}

/* Seitenansicht der Haltung */
const sideCv = $('#side'), sctx = sideCv.getContext('2d');
const POSES = { STAND: { h: 1, tilt: 0, fl: 1, rl: 1 }, SITZ: { h: .72, tilt: -.45, fl: 1, rl: .3 }, PLATZ: { h: .3, tilt: 0, fl: .22, rl: .22 } };
function lerp(a, b, t) { return a + (b - a) * t; }
function drawSide(s) {
  const W = sideCv.width, H = sideCv.height, c = sctx; c.clearRect(0, 0, W, H);
  const from = POSES[curPoseFrom] || POSES.STAND, to = POSES[s.robot.pose_to] || POSES.STAND;
  const p = s.robot.pose === 'MOVING' ? s.robot.pose_prog : 1;
  const P = s.robot.pose === 'MOVING' ? { h: lerp(from.h, to.h, p), tilt: lerp(from.tilt, to.tilt, p), fl: lerp(from.fl, to.fl, p), rl: lerp(from.rl, to.rl, p) } : (POSES[s.robot.pose] || POSES.STAND);
  const gy = H - 18; c.strokeStyle = css('--line'); c.lineWidth = 2; c.beginPath(); c.moveTo(10, gy); c.lineTo(W - 10, gy); c.stroke();
  const bodyL = 120, legMax = 52, cx = W / 2, hipY = gy - 8 - legMax * P.rl * .9, shY = gy - 8 - legMax * P.fl * .9;
  const col = css('--robot'); c.strokeStyle = col; c.fillStyle = col; c.lineCap = 'round';
  const rx = cx - bodyL / 2, fx = cx + bodyL / 2 - 10;
  c.lineWidth = 7; c.beginPath(); c.moveTo(rx, hipY); c.lineTo(fx, shY); c.stroke();                 // Rumpf
  c.lineWidth = 5; c.beginPath(); c.moveTo(rx + 4, hipY); c.lineTo(rx + 4 - (1 - P.rl) * 14, gy - 4); c.moveTo(fx - 4, shY); c.lineTo(fx - 4, gy - 4); c.stroke();   // Beine
  c.beginPath(); c.arc(fx + 14, shY - 14 - (P.fl - .22) * 4, 9, 0, 7); c.fill();                      // Kopf
  c.lineWidth = 3; c.beginPath(); c.moveTo(rx, hipY); c.lineTo(rx - 14, hipY - 8 + (s.robot.show ? Math.sin(performance.now() / 70) * 6 : 0)); c.stroke();
  c.fillStyle = css('--muted'); c.font = '11px ' + css('--sans'); c.textAlign = 'left'; c.fillText('Seitenansicht · ' + ({ STAND: 'Stand', SITZ: 'Sitz', PLATZ: 'Platz', MOVING: 'Wechsel' }[s.robot.pose]), 10, 14);
}

/* Maus: Knochen / Schiedsrichter ziehen */
let drag = null, lastSend = 0;
function pointerWorld(e) { const r = cv.getBoundingClientRect(); return [wx(e.clientX - r.left), wy(e.clientY - r.top)]; }
cv.addEventListener('pointerdown', e => {
  if (!snap) return; const [x, y] = pointerWorld(e);
  const b = snap.bone, rf = snap.referee;
  if (Math.hypot(x - b.x, y - b.y) < 0.28) drag = 'bone'; else if (Math.hypot(x - rf.x, y - rf.y) < 0.4) drag = 'ref';
  if (drag) cv.setPointerCapture(e.pointerId);
});
cv.addEventListener('pointermove', e => {
  if (!drag) return; const [x, y] = pointerWorld(e); const now = performance.now(); if (now - lastSend < 80) return; lastSend = now;
  if (drag === 'bone') api('bone', { x, y }); else api('env', { referee_distance: Math.max(0.5, Math.min(2.0, -x)) });
});
cv.addEventListener('pointerup', e => { if (drag) { const [x, y] = pointerWorld(e); if (drag === 'bone') api('bone', { x, y }); drag = null; } });
cv.addEventListener('dblclick', e => { const [x, y] = pointerWorld(e); api('bone', { x, y, th: Math.random() * 6.28 - 3.14 }); });

/* ------------------------------------------------------------------ Start */
try { const t = localStorage.getItem('theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* egal */ }
window.addEventListener('resize', resize);
new ResizeObserver(resize).observe(cv.parentElement);
initControls(); buildFsm(); resize(); loadScenarios(); loadInfo();
$('#tVoice').onclick = () => startJob('voice'); $('#tGesture').onclick = () => startJob('gesture'); $('#tMC').onclick = () => { $('#tN').value = Math.min(+$('#tN').value, 100); startJob('montecarlo'); };
connect(); drawArena();
