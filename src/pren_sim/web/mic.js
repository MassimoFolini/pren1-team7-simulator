/* Live-Sprachbefehle über das Mikrofon des Bedieners (Web Speech API des Browsers).
 *
 * ACHTUNG Datenschutz/Offline: Die Spracherkennung von Chrome/Edge läuft über einen Online-Dienst des Browser-Anbieters
 * (der Ton verlässt den Rechner). Das ist nur eine Komfortfunktion für den Simulator. Der echte Roboter erkennt die
 * Befehle lokal (z. B. Vosk), siehe docs/ARCHITEKTUR.md. Funktioniert nur auf http://localhost (sicherer Kontext).
 */
'use strict';
const Mic = (() => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  // Wortformen, die Browser-Erkennungen für die vier Befehle (und den Zusatzbefehl) liefern können
  const VOCAB = {
    HIER: ['hier', 'hierher', 'hear', 'hia', 'hir', 'ier'],
    BRAV: ['brav', 'bravo', 'braf', 'brave', 'bra', 'braff', 'prav'],
    SITZ: ['sitz', 'sitzt', 'sitze', 'sits', 'sitzen', 'sitzend', 'zitz', 'sizz'],
    SUCH: ['such', 'suche', 'suchen', 'sucht', 'zuch', 'suck', 'zuck', 'suh', 'sook'],
    KUNSTSTUECK: ['kunststuck', 'kunststueck', 'kunst', 'trick', 'kunststucke'],
  };
  const norm = t => t.toLowerCase().replace(/ß/g, 'ss').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z\s]/g, ' ').trim();
  function match(text) {
    const toks = norm(text).split(/\s+/).filter(Boolean);
    for (let i = toks.length - 1; i >= 0; i--) {
      for (const [w, forms] of Object.entries(VOCAB)) if (forms.includes(toks[i])) return w;
    }
    return null;
  }

  let rec = null, enabled = false, fired = {}, cb = {};
  const supported = !!SR;

  function status(msg, level) { if (cb.status) cb.status(msg, level || 'info'); }

  function start(callbacks) {
    cb = callbacks || {};
    if (!SR) { status('Dieser Browser unterstützt keine Spracherkennung (bitte Chrome oder Edge verwenden).', 'bad'); return false; }
    if (!window.isSecureContext) { status('Mikrofon nur über http://localhost oder https erlaubt.', 'bad'); return false; }
    enabled = true;
    spawn();
    return true;
  }
  function stop() { enabled = false; if (rec) { try { rec.stop(); } catch (e) { /* egal */ } } status('Mikrofon aus', 'info'); }

  function spawn() {
    rec = new SR();
    rec.lang = 'de-DE'; rec.continuous = true; rec.interimResults = true; rec.maxAlternatives = 3;
    rec.onstart = () => { fired = {}; status('Mikrofon an – sprich: HIER · BRAV · SITZ · SUCH', 'ok'); };
    rec.onerror = e => {
      if (e.error === 'no-speech' || e.error === 'aborted') return;
      const m = { 'not-allowed': 'Mikrofon-Zugriff verweigert (Browser-Berechtigung prüfen).', 'service-not-allowed': 'Spracherkennung nicht erlaubt.',
        network: 'Spracherkennung braucht Internet (Browser-Dienst nicht erreichbar).', 'audio-capture': 'Kein Mikrofon gefunden.' }[e.error] || ('Fehler: ' + e.error);
      status(m, 'bad');
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed' || e.error === 'audio-capture') enabled = false;
    };
    rec.onend = () => { if (enabled) setTimeout(() => { try { spawn(); } catch (e) { status('Neustart fehlgeschlagen', 'bad'); } }, 150); };
    rec.onresult = ev => {
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const res = ev.results[i];
        let best = null, text = res[0].transcript;
        for (let a = 0; a < res.length; a++) { const w = match(res[a].transcript); if (w) { best = { w, text: res[a].transcript, conf: res[a].confidence }; break; } }
        if (cb.heard) cb.heard(text, !!best, res.isFinal);
        if (!best) continue;
        // Zwischenergebnisse haben meist keine echte Konfidenz: dann Annahme 0.8 (Latenz sparen)
        const conf = res.isFinal && best.conf > 0 ? best.conf : 0.8;
        if (fired[i] === best.w) continue;          // dieses Wort in dieser Äusserung schon gemeldet
        fired[i] = best.w;
        if (cb.word) cb.word(best.w, conf, best.text.trim());
      }
    };
    try { rec.start(); } catch (e) { status('Start fehlgeschlagen: ' + e.message, 'bad'); }
  }
  return { start, stop, supported, match, get on() { return enabled; } };
})();
