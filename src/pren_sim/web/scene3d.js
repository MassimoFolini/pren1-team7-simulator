/* 3D-Ansicht des Digital Twins (three.js r128, lokal eingebunden – läuft offline).
 * Koordinaten: Welt (x, y) in m -> three (x, 0, -y); Roboter-Heading th -> rotation.y = th.
 * Zeigt Spielfeld, Roboter mit Haltungen, Schiedsrichter (Sprechblase, Gesten) und die Sicht der Roboter-Kamera (66°).
 */
'use strict';
const Scene3D = (() => {
  const T = THREE;
  let renderer, scene, camMain, camRobot, canvas, hud, hctx;
  let R = null;                       // Roboter-Teile
  let ref = null, bone = null, fovMesh, tofLine, detLine, targetRing, trailT, trailO, ghost, floorMat, floor, grid;
  let amb, sun, hemi;
  const orbit = { az: -2.35, el: 0.85, dist: 9.5, target: new T.Vector3(1.6, 0, 0), azOff: 0 };
  let mode = 'orbit';                 // orbit | follow | first
  let last = performance.now(), sm = null, inited = false, W = 10, H = 10, inset = { x: 0, y: 0, w: 0, h: 0 };
  const FIELD = { half: 15 * Math.PI / 180, radius: 5 };
  const POSE3 = { STAND: { rear: .18, front: .18 }, SITZ: { rear: .085, front: .18 }, PLATZ: { rear: .065, front: .065 } };

  const v3 = (x, y, z) => new T.Vector3(x, y, z);
  const wpos = (x, y, h = 0) => v3(x, h, -y);
  const lerp = (a, b, k) => a + (b - a) * k;
  const angLerp = (a, b, k) => a + Math.atan2(Math.sin(b - a), Math.cos(b - a)) * k;
  const mat = (c, o = {}) => new T.MeshLambertMaterial(Object.assign({ color: c }, o));
  const basic = (c, o = {}) => new T.MeshBasicMaterial(Object.assign({ color: c }, o));

  function lightFactor(lux) { return Math.max(0.05, Math.min(1, 0.25 + 0.75 * (Math.log10(Math.max(lux, 1)) - 1) / 1.5)); }

  // ---------------------------------------------------------------- Beschriftungen
  function label(text, w = 1.0, color = '#ffffff', bg = 'rgba(20,30,40,.78)') {
    const c = document.createElement('canvas'); c.width = 320; c.height = 80;
    const tex = new T.CanvasTexture(c);
    const sp = new T.Sprite(new T.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
    sp.scale.set(w, w * 0.25, 1); sp.renderOrder = 10;
    sp.userData = { c, tex, text: null, color, bg };
    setLabel(sp, text); return sp;
  }
  function setLabel(sp, text) {
    const u = sp.userData; if (u.text === text) return; u.text = text;
    const g = u.c.getContext('2d'); g.clearRect(0, 0, 320, 80);
    g.fillStyle = u.bg; g.beginPath(); g.roundRect(4, 10, 312, 60, 14); g.fill();
    g.fillStyle = u.color; g.font = 'bold 34px system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(text, 160, 42); u.tex.needsUpdate = true;
  }

  // ---------------------------------------------------------------- Aufbau
  function floorTexture() {
    const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d');
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, 256, 256);
    g.strokeStyle = 'rgba(120,110,90,.35)'; g.lineWidth = 3; g.strokeRect(0, 0, 256, 256);
    g.strokeStyle = 'rgba(120,110,90,.15)'; g.lineWidth = 2; g.beginPath(); g.moveTo(128, 0); g.lineTo(128, 256); g.moveTo(0, 128); g.lineTo(256, 128); g.stroke();
    const t = new T.CanvasTexture(c); t.wrapS = t.wrapT = T.RepeatWrapping; t.repeat.set(16, 12);
    t.anisotropy = renderer.capabilities.getMaxAnisotropy(); return t;
  }
  function tape(x1, y1, x2, y2, wdt = 0.03, col = 0xffffff, h = 0.004) {
    const L = Math.hypot(x2 - x1, y2 - y1), m = new T.Mesh(new T.BoxGeometry(L, 0.002, wdt), basic(col));
    m.position.set((x1 + x2) / 2, h, -(y1 + y2) / 2); m.rotation.y = Math.atan2(y2 - y1, x2 - x1); return m;
  }
  function buildField(F) {
    const g = new T.Group();
    const h = FIELD.half, Rr = FIELD.radius;
    const wedge = new T.Mesh(new T.CircleGeometry(Rr, 64, -h, 2 * h), basic(0x2f7fc4, { transparent: true, opacity: .16, depthWrite: false }));
    wedge.rotation.x = -Math.PI / 2; wedge.position.y = 0.003; g.add(wedge);
    g.add(tape(0, 0, Rr * Math.cos(h), Rr * Math.sin(h)), tape(0, 0, Rr * Math.cos(h), -Rr * Math.sin(h)));
    const arc = new T.Mesh(new T.RingGeometry(Rr - 0.015, Rr + 0.015, 96, 1, -h, 2 * h), basic(0xffffff)); arc.rotation.x = -Math.PI / 2; arc.position.y = 0.004; g.add(arc);
    for (const [px, py] of [[0, 0], [Rr * Math.cos(h), Rr * Math.sin(h)], [Rr * Math.cos(h), -Rr * Math.sin(h)]]) {       // Pylonen (FAQ 8)
      const cone = new T.Mesh(new T.ConeGeometry(0.05, 0.16, 14), mat(0xf57c00)); cone.position.set(px, 0.08, -py); g.add(cone);
    }
    // Startfeld 50 x 20 cm
    const sf = new T.Mesh(new T.PlaneGeometry(0.5, 0.2), basic(0xffffff, { transparent: true, opacity: .35 })); sf.rotation.x = -Math.PI / 2; sf.position.y = 0.003; g.add(sf);
    for (const [a, b, c, d] of [[-.25, -.1, .25, -.1], [-.25, .1, .25, .1], [-.25, -.1, -.25, .1], [.25, -.1, .25, .1]]) g.add(tape(a, b, c, d, 0.02, 0xffffff, 0.005));
    // Interaktionsbereich R 1.5 m
    const ring = new T.Mesh(new T.RingGeometry(1.5 - 0.008, 1.5 + 0.008, 96), basic(0x7a4bb5, { transparent: true, opacity: .45 })); ring.rotation.x = -Math.PI / 2; ring.position.y = 0.002; g.add(ring);
    return g;
  }
  function limb(r, len, col) { const m = new T.Mesh(new T.CylinderGeometry(r, r, 1, 10), mat(col)); m.scale.y = len; return m; }

  function buildRobot() {
    const root = new T.Group(), body = new T.Group();
    const green = 0x2f7d5b, dark = 0x23382f;
    const torso = new T.Mesh(new T.BoxGeometry(0.30, 0.10, 0.14), mat(green)); body.add(torso);
    const bellyStripe = new T.Mesh(new T.BoxGeometry(0.22, 0.012, 0.145), mat(0xdfeee6)); bellyStripe.position.y = 0.0; torso.add(bellyStripe);
    const head = new T.Group(); head.position.set(0.19, 0.055, 0); body.add(head);
    const skull = new T.Mesh(new T.BoxGeometry(0.10, 0.085, 0.10), mat(green)); head.add(skull);
    const snout = new T.Mesh(new T.BoxGeometry(0.07, 0.045, 0.06), mat(0xdfeee6)); snout.position.set(0.075, -0.015, 0); head.add(snout);
    const nose = new T.Mesh(new T.SphereGeometry(0.013, 10, 8), mat(0x111111)); nose.position.set(0.112, -0.003, 0); head.add(nose);
    for (const z of [-0.033, 0.033]) { const e = new T.Mesh(new T.SphereGeometry(0.011, 10, 8), mat(0xffffff)); e.position.set(0.05, 0.015, z); head.add(e); const p = new T.Mesh(new T.SphereGeometry(0.006, 8, 6), mat(0x111111)); p.position.set(0.058, 0.015, z); head.add(p); }
    const ears = [-1, 1].map(s => { const e = new T.Mesh(new T.BoxGeometry(0.035, 0.05, 0.012), mat(dark)); e.position.set(-0.01, 0.06, s * 0.05); head.add(e); return e; });
    const lens = new T.Mesh(new T.CylinderGeometry(0.012, 0.012, 0.014, 14), mat(0x111111)); lens.rotation.z = Math.PI / 2; lens.position.set(0.062, 0.058, 0); head.add(lens);
    const holder = new T.Group(); holder.position.set(0.07, 0.058, 0); holder.rotation.z = -0.14; head.add(holder);
    const cam = new T.PerspectiveCamera(51.3, 4 / 3, 0.04, 40); cam.rotation.y = -Math.PI / 2; holder.add(cam);
    const tail = new T.Group(); tail.position.set(-0.15, 0.02, 0); body.add(tail);
    const tailM = new T.Mesh(new T.BoxGeometry(0.11, 0.018, 0.018), mat(dark)); tailM.position.x = -0.055; tail.add(tailM);
    root.add(body);
    const legs = [];
    for (const [x, z, front] of [[0.11, -0.065, true], [0.11, 0.065, true], [-0.11, -0.065, false], [-0.11, 0.065, false]]) {
      const l = limb(0.016, 1, dark); root.add(l); const foot = new T.Mesh(new T.SphereGeometry(0.02, 10, 8), mat(0x111111)); root.add(foot); legs.push({ l, foot, x, z, front });
    }
    const wheels = [];
    for (const z of [-0.085, 0.085]) {                                // Antriebsräder (Differentialantrieb)
      const piv = new T.Group(); piv.position.set(0, 0.04, z);
      const tire = new T.Mesh(new T.CylinderGeometry(0.04, 0.04, 0.03, 24), mat(0x222222)); tire.rotation.x = Math.PI / 2; piv.add(tire);
      const hub = new T.Mesh(new T.BoxGeometry(0.075, 0.075, 0.032), mat(0xdddddd)); hub.scale.set(1, 0.18, 1); piv.add(hub);
      root.add(piv); wheels.push(piv);
    }
    const shadow = new T.Mesh(new T.CircleGeometry(0.22, 24), basic(0x000000, { transparent: true, opacity: .18, depthWrite: false })); shadow.rotation.x = -Math.PI / 2; shadow.scale.set(1, 0.55, 1); shadow.position.y = 0.002; root.add(shadow);
    const lab = label('INIT', 0.9); lab.position.set(0, 0.55, 0); root.add(lab);
    return { root, body, torso, head, ears, tail, legs, wheels, cam, lab, holder, mats: [torso.material, skull.material] };
  }

  function buildReferee() {
    const g = new T.Group(), skin = 0xe3bb94, shirt = 0x7a4bb5;
    const legs = new T.Mesh(new T.CylinderGeometry(0.09, 0.08, 0.8, 14), mat(0x2b2f45)); legs.position.y = 0.4; g.add(legs);
    const torso = new T.Mesh(new T.CylinderGeometry(0.15, 0.13, 0.6, 14), mat(shirt)); torso.position.y = 1.1; g.add(torso);
    const head = new T.Mesh(new T.SphereGeometry(0.11, 16, 12), mat(skin)); head.position.y = 1.55; g.add(head);
    const arm = new T.Group(); arm.position.set(0.0, 1.35, -0.18);                // rechter Arm (Gesten)
    const am = new T.Mesh(new T.CylinderGeometry(0.035, 0.03, 0.6, 10), mat(shirt)); am.position.y = -0.3; arm.add(am);
    const hand = new T.Mesh(new T.SphereGeometry(0.045, 10, 8), mat(skin)); hand.position.y = -0.62; arm.add(hand); g.add(arm);
    const arm2 = new T.Group(); arm2.position.set(0.0, 1.35, 0.18);
    const am2 = new T.Mesh(new T.CylinderGeometry(0.035, 0.03, 0.6, 10), mat(shirt)); am2.position.y = -0.3; arm2.add(am2); g.add(arm2);
    const name = label('Schiedsrichter', 1.3); name.position.y = 1.95; g.add(name);
    const bubble = label('', 1.1, '#1d252d', 'rgba(255,255,255,.95)'); bubble.position.set(0, 2.25, 0); g.add(bubble);
    return { g, arm, name, bubble };
  }

  function buildBone() {
    const g = new T.Group(), c = 0xc9a36b, L = 0.21;
    const shaft = new T.Mesh(new T.CylinderGeometry(0.011, 0.011, L, 10), mat(c)); shaft.rotation.z = Math.PI / 2; g.add(shaft);
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) { const k = new T.Mesh(new T.SphereGeometry(0.017, 10, 8), mat(c)); k.position.set(sx * L / 2, 0, sz * 0.012); g.add(k); }
    g.position.y = 0.017;
    const pulse = new T.Mesh(new T.RingGeometry(0.15, 0.17, 32), basic(0xe08a1e, { transparent: true, opacity: .8, side: T.DoubleSide })); pulse.rotation.x = -Math.PI / 2; pulse.position.y = 0.01;
    const lab = label('Knochen', 0.8); lab.position.y = 0.35;
    const wrap = new T.Group(); wrap.add(g); const fixed = new T.Group(); fixed.add(pulse, lab); wrap.userData = { bone: g, pulse, fixed };
    return { wrap, bone: g, pulse, lab, fixed };
  }

  function lineObj(n, color, dashed) {
    const geo = new T.BufferGeometry(); geo.setAttribute('position', new T.BufferAttribute(new Float32Array(n * 3), 3)); geo.setDrawRange(0, 0);
    const l = new T.Line(geo, new T.LineBasicMaterial({ color })); l.frustumCulled = false; return l;
  }
  function setLine(l, pts, h) {
    const a = l.geometry.attributes.position, n = Math.min(pts.length, a.count);
    for (let i = 0; i < n; i++) { a.array[i * 3] = pts[i][0]; a.array[i * 3 + 1] = h; a.array[i * 3 + 2] = -pts[i][1]; }
    a.needsUpdate = true; l.geometry.setDrawRange(0, n);
  }

  function init(cnv, hudCanvas) {
    canvas = cnv; hud = hudCanvas; hctx = hud.getContext('2d');
    renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    scene = new T.Scene(); scene.background = new T.Color(0xcfd8e0); scene.fog = new T.Fog(0xcfd8e0, 22, 48);
    camMain = new T.PerspectiveCamera(45, 1, 0.05, 80);
    amb = new T.AmbientLight(0xffffff, 0.7); sun = new T.DirectionalLight(0xffffff, 0.75); sun.position.set(-3, 8, 4); hemi = new T.HemisphereLight(0xffffff, 0x887766, 0.25);
    scene.add(amb, sun, hemi);
    floorMat = new T.MeshLambertMaterial({ map: floorTexture(), color: 0xd6ccb0 });
    floor = new T.Mesh(new T.PlaneGeometry(16, 12), floorMat); floor.rotation.x = -Math.PI / 2; floor.position.set(2.4, 0, 0); scene.add(floor);
    scene.add(buildField());
    R = buildRobot(); scene.add(R.root); camRobot = R.cam;
    ref = buildReferee(); scene.add(ref.g);
    bone = buildBone(); scene.add(bone.wrap, bone.fixed); bone.wrap.add(bone.bone);
    // Sichtfeld (Boden), Distanzstrahl, Detektion, Ziel
    const f = 33 * Math.PI / 180, Lf = 3.2, seg = 20, pos = [0, 0, 0];
    for (let i = 0; i <= seg; i++) { const a = -f + 2 * f * i / seg; pos.push(Lf * Math.cos(a), 0, -Lf * Math.sin(a)); }
    const idx = []; for (let i = 1; i <= seg; i++) idx.push(0, i, i + 1);
    const fg = new T.BufferGeometry(); fg.setAttribute('position', new T.Float32BufferAttribute(pos, 3)); fg.setIndex(idx);
    fovMesh = new T.Mesh(fg, basic(0xe0aa1e, { transparent: true, opacity: .16, side: T.DoubleSide, depthWrite: false })); fovMesh.position.y = 0.008; scene.add(fovMesh);
    tofLine = lineObj(2, 0xd32f2f); scene.add(tofLine); detLine = lineObj(2, 0xd4a000); scene.add(detLine);
    targetRing = new T.Mesh(new T.RingGeometry(0.09, 0.115, 24), basic(0xd4a000, { side: T.DoubleSide })); targetRing.rotation.x = -Math.PI / 2; targetRing.position.y = 0.012; scene.add(targetRing);
    trailT = lineObj(1000, 0x1f5f99); trailO = lineObj(1000, 0xe08a1e); scene.add(trailT, trailO);
    ghost = new T.LineSegments(new T.EdgesGeometry(new T.BoxGeometry(0.41, 0.1, 0.17)), new T.LineBasicMaterial({ color: 0xe08a1e })); scene.add(ghost);
    attachMouse(); inited = true;
  }

  // ---------------------------------------------------------------- Maus
  function attachMouse() {
    let drag = null;
    canvas.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, btn: e.button }; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener('pointerup', () => { drag = null; });
    canvas.addEventListener('pointermove', e => {
      if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY;
      if (mode === 'first') return;
      if (drag.btn === 2 || e.shiftKey) {
        if (mode !== 'orbit') return;
        const k = orbit.dist * 0.0016, c = Math.cos(orbit.az), sn = Math.sin(orbit.az);
        const rx = -sn, ry = c, lx = -c, ly = -sn;                      // rechts / blickrichtung (Welt)
        const wx = rx * (-dx * k) + lx * (dy * k), wy = ry * (-dx * k) + ly * (dy * k);
        orbit.target.x += wx; orbit.target.z -= wy;
      } else {
        if (mode === 'follow') orbit.azOff -= dx * 0.008; else orbit.az -= dx * 0.008;
        orbit.el = Math.max(0.08, Math.min(1.5, orbit.el + dy * 0.006));
      }
    });
    canvas.addEventListener('wheel', e => { e.preventDefault(); orbit.dist = Math.max(1.0, Math.min(22, orbit.dist * Math.exp(e.deltaY * 0.001))); }, { passive: false });
    canvas.addEventListener('contextmenu', e => e.preventDefault());
  }

  function resize() {
    if (!inited) return;
    const r = canvas.parentElement.getBoundingClientRect(); W = Math.max(10, r.width); H = Math.max(10, r.height);
    renderer.setSize(W, H, false); camMain.aspect = W / H; camMain.updateProjectionMatrix();
    hud.width = W * renderer.getPixelRatio(); hud.height = H * renderer.getPixelRatio();
    hctx.setTransform(renderer.getPixelRatio(), 0, 0, renderer.getPixelRatio(), 0, 0);
    const w = Math.min(340, W * 0.38); inset = { w, h: w * 0.75, x: W - w - 12, y: H - w * 0.75 - 12 };
  }

  // ---------------------------------------------------------------- Aktualisieren
  function poseParams(s, from) {
    const to = POSE3[s.robot.pose_to] || POSE3.STAND;
    if (s.robot.pose !== 'MOVING') return POSE3[s.robot.pose] || POSE3.STAND;
    const a = POSE3[from] || POSE3.STAND, p = s.robot.pose_prog, e = p * p * (3 - 2 * p);
    return { rear: lerp(a.rear, to.rear, e), front: lerp(a.front, to.front, e) };
  }

  function update(s, from, o, dt) {
    const k = 1 - Math.exp(-dt * 22), r = s.robot;
    if (!sm || Math.hypot(sm.x - r.x, sm.y - r.y) > 1.0) sm = { x: r.x, y: r.y, th: r.th, pl: r.phi_l, pr: r.phi_r };
    sm.x = lerp(sm.x, r.x, k); sm.y = lerp(sm.y, r.y, k); sm.th = angLerp(sm.th, r.th, k); sm.pl = lerp(sm.pl, r.phi_l, k); sm.pr = lerp(sm.pr, r.phi_r, k);
    R.root.position.set(sm.x, 0, -sm.y); R.root.rotation.y = sm.th;
    // Haltung
    const P = poseParams(s, from), len = 0.24;
    R.body.position.y = (P.rear + P.front) / 2; R.body.rotation.z = Math.atan2(P.front - P.rear, len);
    R.head.rotation.z = -R.body.rotation.z * 0.55;
    for (const lg of R.legs) { const h = lg.front ? P.front : P.rear; lg.l.scale.y = Math.max(0.02, h - 0.03); lg.l.position.set(lg.x, h / 2 - 0.005, lg.z); lg.foot.position.set(lg.x, 0.02, lg.z); }
    R.wheels[0].rotation.z = -sm.pl; R.wheels[1].rotation.z = -sm.pr;           // links = -z
    const wag = s.robot.show ? Math.sin(performance.now() / 65) * 0.7 : 0;
    R.tail.rotation.y = wag; R.tail.rotation.z = s.robot.show ? 0.5 : 0.15;
    R.ears[0].rotation.x = R.ears[1].rotation.x = s.robot.show ? -0.2 : 0.1;
    const stop = s.brain.state === 'NOT_AUS', flash = stop && (Math.floor(performance.now() / 300) % 2 === 0);
    for (const m of R.mats) m.color.setHex(flash ? 0xd32f2f : stop ? 0x8a2a24 : 0x2f7d5b);
    setLabel(R.lab, s.brain.state.replace('_', ' '));
    R.lab.position.y = 0.45 + (P.front - 0.18);
    // Schiedsrichter
    ref.g.position.set(s.referee.x, 0, -s.referee.y); ref.g.rotation.y = 0;         // blickt in +x (zum Hund)
    const g = s.referee.gesture, tgt = g === 'AUF' ? 2.7 : g === 'PLATZ' ? 0.55 : g === 'SITZ' ? 1.45 : 0.08;
    ref.arm.rotation.z = lerp(ref.arm.rotation.z, tgt, 1 - Math.exp(-dt * 10));
    setLabel(ref.name, 'Schiedsrichter ' + (-s.referee.x).toFixed(1) + ' m' + (g ? ' · Geste ' + g : ''));
    ref.bubble.visible = !!s.referee.say; if (s.referee.say) setLabel(ref.bubble, '«' + s.referee.say + '»');
    // Knochen
    const b = s.bone; bone.wrap.position.set(b.x, 0, -b.y); bone.wrap.rotation.y = b.th;
    bone.fixed.position.set(b.x, 0, -b.y); bone.pulse.scale.setScalar(1 + 0.18 * Math.sin(performance.now() / 300));
    setLabel(bone.lab, b.in_sector ? 'Knochen' : 'Knochen (ausserhalb)');
    // Hilfsgrafik
    fovMesh.visible = o.fov && s.env.camera_ok;
    const cp = R.cam.getWorldPosition(v3(0, 0, 0));
    fovMesh.position.set(sm.x + Math.cos(sm.th) * 0.18, 0.008, -(sm.y + Math.sin(sm.th) * 0.18)); fovMesh.rotation.y = sm.th;
    const nose = [sm.x + Math.cos(sm.th) * 0.2, sm.y + Math.sin(sm.th) * 0.2], L = s.tof === null ? 4 : s.tof;
    setLine(tofLine, [nose, [nose[0] + Math.cos(sm.th) * L, nose[1] + Math.sin(sm.th) * L]], 0.04);
    tofLine.material.opacity = 1; tofLine.material.transparent = s.tof === null; tofLine.material.opacity = s.tof === null ? 0.25 : 1;
    if (s.detect && s.env.camera_ok) { const a = sm.th + s.detect.bearing, c0 = [sm.x + Math.cos(sm.th) * 0.18, sm.y + Math.sin(sm.th) * 0.18]; setLine(detLine, [c0, [c0[0] + Math.cos(a) * s.detect.dist, c0[1] + Math.sin(a) * s.detect.dist]], 0.03); detLine.visible = true; } else detLine.visible = false;
    targetRing.visible = !!s.target; if (s.target) targetRing.position.set(s.target.x, 0.012, -s.target.y);
    trailT.visible = o.trail; trailO.visible = o.odom; ghost.visible = o.odom;
    if (o.trail) setLine(trailT, window.__trailTrue || [], 0.012); if (o.odom) setLine(trailO, window.__trailOdom || [], 0.016);
    ghost.position.set(s.odom.x, 0.05, -s.odom.y); ghost.rotation.y = s.odom.th;
    // Licht (Raumlicht-Regler wirkt auch auf die Kamera!)
    const lf = lightFactor(s.env.light_lux);
    amb.intensity = 0.08 + 0.42 * lf; sun.intensity = 0.05 + 0.42 * lf; hemi.intensity = 0.03 + 0.12 * lf;
    const bg = new T.Color().setHSL(0.58, 0.18, 0.1 + 0.7 * lf); scene.background.copy(bg); scene.fog.color.copy(bg);
    floorMat.color.set(0xd6ccb0).lerp(new T.Color(0xc9a36b), s.env.floor_similarity * 0.9);   // knochenfarbener Boden
    if (grid !== o.grid) { grid = o.grid; floorMat.map.repeat.set(grid ? 16 : 0.0001, grid ? 12 : 0.0001); }
    // Hauptkamera
    if (mode === 'follow') {
      const az = sm.th + Math.PI + orbit.azOff, d = Math.min(orbit.dist, 3.2) * 0.8, el = Math.max(0.2, orbit.el * 0.55);
      camMain.position.set(sm.x + d * Math.cos(el) * Math.cos(az), d * Math.sin(el) + 0.1, -(sm.y + d * Math.cos(el) * Math.sin(az)));
      camMain.lookAt(sm.x, 0.12, -sm.y);
    } else if (mode === 'orbit') {
      const d = orbit.dist, el = orbit.el, az = orbit.az;
      camMain.position.set(orbit.target.x + d * Math.cos(el) * Math.cos(az), d * Math.sin(el), orbit.target.z - d * Math.cos(el) * Math.sin(az));
      camMain.lookAt(orbit.target);
    }
  }

  // ---------------------------------------------------------------- Zeichnen
  function render(s, o) {
    const pr = renderer.getPixelRatio();
    renderer.setScissorTest(false); renderer.setViewport(0, 0, W, H); renderer.clear();
    let rect;
    if (mode === 'first') {
      const w = Math.min(W, H * 4 / 3), h = w * 0.75; rect = { x: (W - w) / 2, y: (H - h) / 2, w, h };
      renderer.setScissorTest(true); renderer.setViewport(rect.x, H - rect.y - rect.h, rect.w, rect.h); renderer.setScissor(rect.x, H - rect.y - rect.h, rect.w, rect.h);
      withoutLabels(() => { R.head.visible = false; renderer.render(scene, camRobot); R.head.visible = true; });
    } else {
      renderer.render(scene, camMain);
      rect = inset;
      renderer.clearDepth(); renderer.setScissorTest(true);
      renderer.setViewport(rect.x, H - rect.y - rect.h, rect.w, rect.h); renderer.setScissor(rect.x, H - rect.y - rect.h, rect.w, rect.h);
      withoutLabels(() => renderer.render(scene, camRobot)); renderer.setScissorTest(false);
    }
    drawHud(s, rect);
  }

  // Beschriftungen gehören nicht ins Kamerabild (die Kamera sieht keine Schilder)
  function withoutLabels(fn) {
    const ls = [R.lab, ref.name, ref.bubble, bone.lab], vis = ls.map(l => l.visible);
    ls.forEach(l => { l.visible = false; }); fn(); ls.forEach((l, i) => { l.visible = vis[i]; });
  }

  function proj(x, y, h, rect) {
    const p = v3(x, h, -y).project(camRobot);
    return { x: rect.x + (p.x + 1) / 2 * rect.w, y: rect.y + (1 - p.y) / 2 * rect.h, z: p.z, ok: p.z < 1 && Math.abs(p.x) <= 1.15 && Math.abs(p.y) <= 1.15 };
  }
  function drawHud(s, rect) {
    const g = hctx; g.clearRect(0, 0, W, H);
    g.save(); g.beginPath(); g.rect(rect.x, rect.y, rect.w, rect.h); g.clip();
    camRobot.updateMatrixWorld(true);
    const fpx = (rect.w / 2) / Math.tan(33 * Math.PI / 180);
    const b = s.bone;
    if (s.env.camera_ok) {
      const pb = proj(b.x, b.y, 0.017, rect);
      if (pb.ok && b.dist > 0.01) {                                // wahrer Knochen im Bild (grau gestrichelt = «nicht erkannt»)
        const wpx = Math.max(10, 0.21 * fpx / Math.max(b.dist, 0.2)) + 8, hpx = Math.max(10, wpx * 0.6);
        g.strokeStyle = 'rgba(255,255,255,.55)'; g.setLineDash([4, 4]); g.lineWidth = 1; g.strokeRect(pb.x - wpx / 2, pb.y - hpx / 2, wpx, hpx); g.setLineDash([]);
      }
      if (s.detect) {                                              // Detektion der Wahrnehmung (grün)
        const a = sm.th + s.detect.bearing, c0 = [sm.x + Math.cos(sm.th) * 0.18, sm.y + Math.sin(sm.th) * 0.18];
        const pd = proj(c0[0] + Math.cos(a) * s.detect.dist, c0[1] + Math.sin(a) * s.detect.dist, 0.017, rect);
        const wpx = Math.max(12, 0.21 * fpx / Math.max(s.detect.dist, 0.2)) + 10, hpx = Math.max(12, wpx * 0.6);
        g.strokeStyle = '#27d17f'; g.lineWidth = 2; g.strokeRect(pd.x - wpx / 2, pd.y - hpx / 2, wpx, hpx);
        g.fillStyle = '#27d17f'; g.font = 'bold 11px system-ui,sans-serif'; g.textAlign = 'left';
        const t = `Knochen ${s.detect.conf.toFixed(2)} · ${s.detect.dist.toFixed(1)} m`, tw = g.measureText(t).width + 8;
        g.fillRect(pd.x - wpx / 2, pd.y - hpx / 2 - 15, tw, 15); g.fillStyle = '#04210f'; g.fillText(t, pd.x - wpx / 2 + 4, pd.y - hpx / 2 - 4);
      }
      g.strokeStyle = 'rgba(255,255,255,.45)'; g.lineWidth = 1;                // Fadenkreuz
      const cx = rect.x + rect.w / 2, cy = rect.y + rect.h / 2; g.beginPath(); g.moveTo(cx - 10, cy); g.lineTo(cx + 10, cy); g.moveTo(cx, cy - 10); g.lineTo(cx, cy + 10); g.stroke();
    } else {
      g.fillStyle = '#000'; g.fillRect(rect.x, rect.y, rect.w, rect.h); g.fillStyle = '#d32f2f'; g.font = 'bold 14px system-ui,sans-serif'; g.textAlign = 'center';
      g.fillText('KAMERA AUSGEFALLEN', rect.x + rect.w / 2, rect.y + rect.h / 2);
    }
    g.restore();
    g.strokeStyle = '#111'; g.lineWidth = 3; g.strokeRect(rect.x, rect.y, rect.w, rect.h);
    g.fillStyle = 'rgba(0,0,0,.6)'; g.fillRect(rect.x, rect.y, rect.w, 18);
    g.fillStyle = '#fff'; g.font = '11px system-ui,sans-serif'; g.textAlign = 'left';
    g.fillText(`📷 Kamera 66° · 4:3 · ${Math.round(s.env.light_lux)} lx` + (s.tof !== null ? ` · Distanz ${s.tof.toFixed(2)} m` : ''), rect.x + 6, rect.y + 13);
  }

  function frame(s, from, o) {
    if (!inited || !s) return;
    const now = performance.now(), dt = Math.min(0.1, (now - last) / 1000); last = now;
    update(s, from, o, dt); render(s, o);
  }
  function setMode(m) { mode = m; if (m === 'orbit') orbit.az = orbit.az; }
  return { init, resize, frame, setMode, get mode() { return mode; } };
})();
