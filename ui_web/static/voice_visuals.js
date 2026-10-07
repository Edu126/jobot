/* Voice-only coach visuals (REQ-047). Each factory has the SAME interface:
 *   makeX(canvas) -> { frame(state, level, t), destroy() }
 *   state: 'idle' | 'speaking' (coach) | 'listening' (candidate) | 'thinking'
 *   level: 0..1 audio energy (coach RMS when speaking, mic RMS when listening)
 *   t: seconds
 * Canvas 2D only, no dependency. Colours come from the jobot tokens (--p hunter
 * green, --a salmon). Swapping the winner into practice_live.html = call
 * VoiceVisuals.make('wave', canvas) instead of voiceOrb's own drawing.
 */
(function () {
  const TAU = Math.PI * 2;
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function token(name) {
    return (getComputedStyle(document.documentElement).getPropertyValue(name) || '').trim();
  }
  // oklch() from a daisyUI "L C H" token; falls back to plain green/salmon.
  function colour(name, alpha, fallback) {
    const v = token(name);
    return v ? `oklch(${v} / ${alpha})` : `rgba(${fallback}, ${alpha})`;
  }
  const green = (a) => colour('--p', a, '40,90,70');
  const salmon = (a) => colour('--a', a, '240,130,110');
  // state -> { tint, energy floor, motion speed, level gain }
  const MOOD = {
    idle:      { tint: green,  base: 0.05, speed: 0.5, gain: 0.0 },
    speaking:  { tint: green,  base: 0.18, speed: 1.0, gain: 1.0 },
    listening: { tint: salmon, base: 0.12, speed: 0.8, gain: 1.0 },
    thinking:  { tint: green,  base: 0.10, speed: 1.6, gain: 0.0 },
  };

  // shared canvas plumbing: DPR-aware sizing + smoothed level + state blend
  function base(canvas) {
    const ctx = canvas.getContext('2d');
    const s = { ctx, W: 0, H: 0, env: 0, mood: MOOD.idle, calm: reduced() };
    const resize = () => {
      const r = canvas.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.max(1, Math.round(r.width * dpr));
      canvas.height = Math.max(1, Math.round(r.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      s.W = r.width; s.H = r.height;
    };
    resize();
    let ro = null;
    try { ro = new ResizeObserver(resize); ro.observe(canvas); } catch (_) {}
    s.begin = (state, level) => {
      s.mood = MOOD[state] || MOOD.idle;
      const target = s.mood.base + clamp(level, 0, 1) * s.mood.gain * (s.calm ? 0.5 : 1);
      s.env += (target - s.env) * (s.calm ? 0.04 : 0.14);
      ctx.clearRect(0, 0, s.W, s.H);
      return s.env;
    };
    s.time = (t) => t * s.mood.speed * (s.calm ? 0.2 : 1);
    s.destroy = () => { try { ro && ro.disconnect(); } catch (_) {} ctx.clearRect(0, 0, s.W, s.H); };
    return s;
  }

  /* 1. WAVE — Siri-style layered sine ribbons, tapered at the ends. */
  function makeWave(canvas) {
    const s = base(canvas);
    const layers = [
      { f: 1.2, p: 0.0, sp: 0.9, a: 1.00, alpha: 0.55 },
      { f: 1.8, p: 1.3, sp: -1.1, a: 0.80, alpha: 0.40 },
      { f: 2.6, p: 2.4, sp: 1.4, a: 0.55, alpha: 0.28 },
      { f: 3.4, p: 4.0, sp: -0.7, a: 0.38, alpha: 0.20 },
    ];
    return {
      frame(state, level, t) {
        const env = s.begin(state, level), { ctx, W, H } = s, tt = s.time(t);
        const tint = s.mood.tint, mid = H / 2, maxA = H * 0.38 * env;
        const think = state === 'thinking';
        layers.forEach((L, i) => {
          ctx.beginPath();
          const steps = Math.max(40, Math.round(W / 6));
          for (let k = 0; k <= steps; k++) {
            const x = k / steps;
            const taper = Math.pow(Math.sin(Math.PI * x), 2);            // 0 at both ends
            let amp = maxA * L.a * taper;
            if (think) amp = H * 0.05 * L.a * taper * (0.6 + 0.4 * Math.sin(tt * 2 + i));
            const y = mid + Math.sin(x * TAU * L.f + L.p + tt * L.sp * 2.2) * amp;
            k ? ctx.lineTo(x * W, y) : ctx.moveTo(x * W, y);
          }
          ctx.lineTo(W, mid); ctx.lineTo(0, mid); ctx.closePath();
          ctx.fillStyle = tint(L.alpha * 0.55);
          ctx.fill();
          // mirrored reflection gives the ribbon its soft body
          ctx.save(); ctx.translate(0, mid * 2); ctx.scale(1, -1); ctx.fillStyle = tint(L.alpha * 0.55); ctx.fill(); ctx.restore();
        });
      },
      destroy: s.destroy,
    };
  }

  /* 2. ETHEREAL — blurred gradient blobs that breathe and swell with voice. */
  function makeEthereal(canvas) {
    const s = base(canvas);
    const blobs = Array.from({ length: 6 }, (_, i) => ({
      a: i * 1.047, r: 0.55 + (i % 3) * 0.12, sp: 0.18 + i * 0.05, ph: i * 1.7, warm: i % 3 === 2,
    }));
    return {
      frame(state, level, t) {
        const env = s.begin(state, level), { ctx, W, H } = s, tt = s.time(t);
        const R = Math.min(W, H);
        const breath = 0.5 + 0.5 * Math.sin(tt * 0.9);
        const think = state === 'thinking';
        blobs.forEach((b) => {
          const orbit = R * (0.06 + 0.10 * env + (think ? 0.04 : 0));
          const ang = b.a + tt * b.sp * (think ? 2.2 : 1);
          const x = W / 2 + Math.cos(ang + b.ph) * orbit * b.r * 2;
          const y = H / 2 + Math.sin(ang * 1.3 + b.ph) * orbit * b.r * 1.6;
          const rad = R * (0.20 + 0.10 * breath + 0.38 * env) * (0.8 + 0.4 * b.r);
          const col = (b.warm && state !== 'speaking') || (b.warm && env > 0.5) ? salmon : s.mood.tint;
          const g = ctx.createRadialGradient(x, y, 0, x, y, rad);
          g.addColorStop(0, col(0.34)); g.addColorStop(0.55, col(0.12)); g.addColorStop(1, col(0));
          ctx.fillStyle = g;
          ctx.fillRect(0, 0, W, H);
        });
      },
      destroy: s.destroy,
    };
  }

  /* 3. GEOMETRIC — rotating wireframe icosahedron + pulse rings (echoes .gen-orb). */
  function makeGeometric(canvas) {
    const s = base(canvas);
    const p = (1 + Math.sqrt(5)) / 2;
    const raw = [[-1, p, 0], [1, p, 0], [-1, -p, 0], [1, -p, 0], [0, -1, p], [0, 1, p],
                 [0, -1, -p], [0, 1, -p], [p, 0, -1], [p, 0, 1], [-p, 0, -1], [-p, 0, 1]];
    const n = Math.hypot(1, p);
    const V = raw.map((v) => v.map((c) => c / n));
    const E = [];
    for (let i = 0; i < 12; i++) for (let j = i + 1; j < 12; j++) {
      const d = Math.hypot(V[i][0] - V[j][0], V[i][1] - V[j][1], V[i][2] - V[j][2]);
      if (d < 1.1) E.push([i, j]);
    }
    let rot = 0;
    return {
      frame(state, level, t) {
        const env = s.begin(state, level), { ctx, W, H } = s, tt = s.time(t);
        const R = Math.min(W, H), cx = W / 2, cy = H / 2, tint = s.mood.tint;
        const think = state === 'thinking';
        rot += (s.calm ? 0.002 : 0.005) * s.mood.speed * (1 + env * 2 + (think ? 1.5 : 0));
        // rings: three expanding, fading circles, phase-shifted like .gen-orb
        for (let i = 0; i < 3; i++) {
          const ph = ((tt * (think ? 0.55 : 0.35 + env * 0.5) + i / 3) % 1);
          ctx.beginPath(); ctx.arc(cx, cy, R * (0.14 + 0.36 * ph), 0, TAU);
          ctx.lineWidth = 1.4; ctx.strokeStyle = tint((1 - ph) * (0.18 + env * 0.4)); ctx.stroke();
        }
        // wireframe
        const sc = R * (0.17 + 0.07 * env), cr = Math.cos(rot), sr = Math.sin(rot), cx2 = Math.cos(rot * 0.6), sx = Math.sin(rot * 0.6);
        const P = V.map(([x, y, z]) => {
          const x1 = x * cr + z * sr, z1 = -x * sr + z * cr;
          const y2 = y * cx2 - z1 * sx, z2 = y * sx + z1 * cx2;
          const k = 1 / (1 - z2 * 0.35);                                   // gentle perspective
          return [cx + x1 * sc * k * 1.6, cy + y2 * sc * k * 1.6, z2];
        });
        ctx.lineWidth = 1.2; ctx.lineCap = 'round';
        E.forEach(([a, b]) => {
          const depth = (P[a][2] + P[b][2]) / 2;                           // -1 back .. 1 front
          ctx.strokeStyle = tint(0.22 + 0.4 * (depth * 0.5 + 0.5) + env * 0.2);
          ctx.beginPath(); ctx.moveTo(P[a][0], P[a][1]); ctx.lineTo(P[b][0], P[b][1]); ctx.stroke();
        });
        P.forEach((q) => {
          ctx.fillStyle = tint(0.35 + 0.5 * (q[2] * 0.5 + 0.5));
          ctx.beginPath(); ctx.arc(q[0], q[1], 1.8 + 1.2 * (q[2] * 0.5 + 0.5), 0, TAU); ctx.fill();
        });
      },
      destroy: s.destroy,
    };
  }

  /* 4. MINIMAL — one breathing circle with a soft halo. Nothing else. */
  function makeMinimal(canvas) {
    const s = base(canvas);
    let swell = 0;
    return {
      frame(state, level, t) {
        const env = s.begin(state, level), { ctx, W, H } = s, tt = s.time(t);
        const R = Math.min(W, H);
        const breath = state === 'thinking' ? 0.5 + 0.5 * Math.sin(tt * 1.6) : 0.5 + 0.5 * Math.sin(tt * 0.9);
        swell += (env - swell) * 0.2;
        const r = R * (0.12 + 0.015 * breath + 0.12 * swell);
        const tint = s.mood.tint, cx = W / 2, cy = H / 2;
        const halo = ctx.createRadialGradient(cx, cy, r * 0.6, cx, cy, r * (2.0 + swell * 1.4));
        halo.addColorStop(0, tint(0.16)); halo.addColorStop(1, tint(0));
        ctx.fillStyle = halo; ctx.fillRect(0, 0, W, H);
        ctx.fillStyle = tint(0.92);
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, TAU); ctx.fill();
      },
      destroy: s.destroy,
    };
  }

  const FACTORIES = { wave: makeWave, ethereal: makeEthereal, geometric: makeGeometric, minimal: makeMinimal };
  window.VoiceVisuals = {
    makeWave, makeEthereal, makeGeometric, makeMinimal,
    names: Object.keys(FACTORIES),
    make(name, canvas) { return (FACTORIES[name] || makeMinimal)(canvas); },
  };
})();
