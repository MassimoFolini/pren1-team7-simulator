/* Live-Gesten mit der Webcam des Bedieners: MediaPipe Hand Landmarker (läuft LOKAL im Browser, WASM, offline).
 *
 * Das Kamerabild verlässt den Rechner nicht. Modell und Bibliothek liegen in web/vendor/mediapipe (Apache-2.0).
 * Gesten laut Aufgabenstellung (Folie 6):
 *   AUF   = Zeigefinger (bzw. «L») zeigt nach oben
 *   PLATZ = Zeigefinger zeigt zum Boden
 *   SITZ  = Handfläche waagerecht nach oben vor der Brust (offene Hand)
 * Die Regeln sind einfache Geometrie auf den 21 Handpunkten (siehe classify). NICHT mit vielen Personen getestet.
 */
'use strict';
const Hand = (() => {
  const BASE = 'vendor/mediapipe';
  const CONN = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12], [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]];
  const EXT = 1.35, CURL = 1.15;                     // Verhältnis Fingerspitze/PIP-Gelenk zum Handgelenk
  let landmarker = null, stream = null, video = null, overlay = null, running = false, loading = false, cb = {}, lastT = -1, lastSend = 0, raf = 0;

  const d3 = (a, b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
  const ratio = (w, tip, pip) => d3(w[tip], w[0]) / Math.max(1e-6, d3(w[pip], w[0]));

  /* Regelbasierte Klassifikation. lm = normierte Bildpunkte (x,y 0..1), wl = Weltpunkte in Metern (gleiche Achsen wie das Bild),
   * vw/vh = Videogrösse. Rückgabe: {label|null, conf 0..1, info{…}} */
  function classify(lm, wl, score, vw = 4, vh = 3) {
    const r = { idx: ratio(wl, 8, 6), mid: ratio(wl, 12, 10), rng: ratio(wl, 16, 14), pnk: ratio(wl, 20, 18) };
    const ext = k => r[k] > EXT, curl = k => r[k] < CURL;
    const vx = (lm[8].x - lm[5].x) * vw, vy = (lm[8].y - lm[5].y) * vh, vl = Math.hypot(vx, vy) || 1e-6;
    const up = -vy / vl, down = vy / vl;                                   // Richtung des Zeigefingers im Bild
    const a = { x: wl[5].x - wl[0].x, y: wl[5].y - wl[0].y, z: wl[5].z - wl[0].z }, b = { x: wl[17].x - wl[0].x, y: wl[17].y - wl[0].y, z: wl[17].z - wl[0].z };
    const n = { x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x };
    const palmV = Math.abs(n.y) / (Math.hypot(n.x, n.y, n.z) || 1e-6);       // 1 = Handfläche waagerecht
    const info = { ...r, up, down, palmV };
    let label = null, margin = 0;
    if (ext('idx') && curl('mid') && curl('rng') && curl('pnk')) {          // Zeigefinger allein
      if (up >= 0.6) { label = 'AUF'; margin = (up - 0.6) / 0.4; }
      else if (down >= 0.6) { label = 'PLATZ'; margin = (down - 0.6) / 0.4; }
    } else if (ext('idx') && ext('mid') && ext('rng') && ext('pnk') && palmV >= 0.6) {   // offene, waagerechte Hand
      label = 'SITZ'; margin = (palmV - 0.6) / 0.4;
    }
    const conf = label ? Math.max(0, Math.min(0.99, (score || 0.8) * (0.62 + 0.38 * Math.min(1, margin)))) : 0;
    return { label, conf, info };
  }

  function draw(lm, label) {
    if (!overlay) return; const g = overlay.getContext('2d'), W = overlay.width, H = overlay.height;
    g.clearRect(0, 0, W, H); if (!lm) return;
    g.strokeStyle = label ? '#27d17f' : '#e0aa1e'; g.lineWidth = 2;
    for (const [i, j] of CONN) { g.beginPath(); g.moveTo(lm[i].x * W, lm[i].y * H); g.lineTo(lm[j].x * W, lm[j].y * H); g.stroke(); }
    g.fillStyle = '#fff'; for (const p of lm) { g.beginPath(); g.arc(p.x * W, p.y * H, 2.5, 0, 7); g.fill(); }
  }

  async function load() {
    if (landmarker) return;
    cb.status && cb.status('Lade Handmodell (lokal) …', 'info');
    const mod = await import('./vendor/mediapipe/vision_bundle.mjs');
    const fs = await mod.FilesetResolver.forVisionTasks(BASE);
    landmarker = await mod.HandLandmarker.createFromOptions(fs, {
      baseOptions: { modelAssetPath: BASE + '/hand_landmarker.task', delegate: 'CPU' },
      runningMode: 'VIDEO', numHands: 1, minHandDetectionConfidence: 0.5, minHandPresenceConfidence: 0.5, minTrackingConfidence: 0.5,
    });
  }

  async function start(videoEl, overlayEl, callbacks) {
    cb = callbacks || {}; video = videoEl; overlay = overlayEl;
    if (running || loading) return running;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { cb.status && cb.status('Kamera nur über http://localhost oder https erlaubt.', 'bad'); return false; }
    if (!window.isSecureContext) { cb.status && cb.status('Kamera nur über http://localhost oder https erlaubt.', 'bad'); return false; }
    loading = true;
    try {
      await load();
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' }, audio: false });
      video.srcObject = stream; await video.play();
      overlay.width = video.videoWidth || 640; overlay.height = video.videoHeight || 480;
      running = true; loading = false; lastT = -1;
      cb.status && cb.status('Kamera an – zeige AUF (Zeigefinger hoch), PLATZ (Zeigefinger runter) oder SITZ (flache Hand, Handfläche oben).', 'ok');
      loop(); return true;
    } catch (e) {
      loading = false; stop();
      const m = e && e.name === 'NotAllowedError' ? 'Kamera-Zugriff verweigert (Browser-Berechtigung prüfen).' : e && e.name === 'NotFoundError' ? 'Keine Kamera gefunden.' : 'Fehler: ' + (e && e.message || e);
      cb.status && cb.status(m, 'bad'); return false;
    }
  }

  function loop() {
    if (!running) return;
    raf = requestAnimationFrame(loop);
    if (video.readyState < 2 || video.currentTime === lastT) return;
    lastT = video.currentTime;
    let res; try { res = landmarker.detectForVideo(video, performance.now()); } catch (e) { return; }
    const has = res.landmarks && res.landmarks.length > 0;
    let out = { label: null, conf: 0, info: null };
    if (has) {
      const score = res.handednesses && res.handednesses[0] && res.handednesses[0][0] ? res.handednesses[0][0].score : 0.8;
      out = classify(res.landmarks[0], res.worldLandmarks[0], score, video.videoWidth, video.videoHeight);
      draw(res.landmarks[0], out.label);
    } else draw(null);
    out.hand = has; cb.frame && cb.frame(out);
    const now = performance.now();
    if (now - lastSend >= 50) { lastSend = now; cb.send && cb.send(out.label, out.conf); }     // höchstens 20 Hz
  }

  function stop() {
    running = false; cancelAnimationFrame(raf);
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    if (video) video.srcObject = null; draw(null);
    cb.status && cb.status('Kamera aus', 'info');
  }
  return { start, stop, classify, get on() { return running; } };
})();
