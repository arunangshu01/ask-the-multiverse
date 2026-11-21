import { useCallback, useEffect, useRef } from "react";

/*
 Original opening sequence in the style of a studio ident (no footage, logos or artwork from anyone else;
 every panel is generated). One canvas, one timeline, driven by requestAnimationFrame:
   0.0-3.0  comic pages flip faster and faster while the camera pulls back (motion-blur trails)
   2.6-3.2  hard-cut panel montage, light streaks, white flash
   3.0-5.1  "ASK THE MULTIVERSE" pulls back from huge, panels flickering inside the letters over a red glow
   5.1-5.7  a glossy red slab sweeps in behind the letters, the letters turn white
   5.5-6.6  a light sweep crosses the letters, a flare streaks across the screen
   5.6-7.0  the tagline settles into place
   6.9-7.6  fade into the site
 ?introAt=4.2 freezes the frame at 4.2 s (for visual checks); ?intro forces it to play.
*/
export const INTRO_MS = 7600;
const SEEN_KEY = "atm.intro.seen";
const WORDS = ["AVENGERS", "X-MEN", "THOR", "STORM", "LOKI", "WANDA", "THANOS", "DOOM", "VENOM", "GROOT", "MILES",
  "BLADE", "HULK", "SHURI", "KANG", "LOGAN", "GWEN", "STRANGE", "GAMORA", "MAGNETO", "JEAN", "ROCKET", "CAROL",
  "NAMOR", "GALACTUS", "ULTRON", "NOVA", "DAREDEVIL", "KATE", "SURFER"];
const SFX = ["KRAK!", "BOOM!", "THWIP!", "SNIKT!", "BAMF!", "ZZAK!", "FWOOSH!", "KA-POW!"];
const TITLE = "ASK THE MULTIVERSE";
const TAGLINE = "EVERY REALITY \u00b7 EVERY ERA";

export function shouldPlayIntro() {
  if (typeof window === "undefined") return false;
  const qs = window.location.search;
  if (qs.includes("introAt") || /[?&]intro\b/.test(qs)) return true;
  if (qs.includes("static")) return false;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return false;
  try { return !sessionStorage.getItem(SEEN_KEY); } catch { return true; }
}

// ---------------------------------------------------------------- helpers
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const prog = (t, a, b) => clamp((t - a) / (b - a));
const easeOut = (x) => 1 - Math.pow(1 - x, 3);
const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
function rng(seed) { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
function hue(str) { let h = 7; for (const c of str) h = (h * 31 + c.charCodeAt(0)) % 3600; return h % 360; }

let tile = null;
function halftoneTile() {
  if (tile) return tile;
  tile = document.createElement("canvas");
  tile.width = 14; tile.height = 14;
  const t = tile.getContext("2d");
  t.fillStyle = "rgba(0,0,0,.24)";
  [[0, 0], [14, 0], [0, 14], [14, 14], [7, 7]].forEach(([x, y]) => { t.beginPath(); t.arc(x, y, 1.4, 0, 6.283); t.fill(); });
  return tile;
}

/** One generated comic panel: palette gradient, burst or speed lines, halftone, caption. */
function makePanel(w, h, seed, label) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const g = c.getContext("2d");
  const r = rng(seed * 7919 + 13);
  const h1 = hue(label + seed), h2 = (h1 + 40 + Math.floor(r() * 120)) % 360;
  const bg = g.createLinearGradient(0, 0, w * r(), h);
  bg.addColorStop(0, `hsl(${h1},80%,${30 + r() * 25}%)`);
  bg.addColorStop(1, `hsl(${h2},75%,${12 + r() * 18}%)`);
  g.fillStyle = bg; g.fillRect(0, 0, w, h);
  const cx = w * (0.3 + r() * 0.4), cy = h * (0.3 + r() * 0.4);
  if (r() < 0.55) { // speed burst
    g.save(); g.translate(cx, cy);
    for (let i = 0; i < 48; i++) {
      g.rotate((Math.PI * 2) / 48);
      g.fillStyle = i % 2 ? `hsla(${h2},90%,70%,.35)` : "rgba(255,255,255,.08)";
      g.beginPath(); g.moveTo(0, 0); g.lineTo(w, -12); g.lineTo(w, 12); g.closePath(); g.fill();
    }
    g.restore();
  } else { // diagonal action lines
    g.strokeStyle = `hsla(${h2},90%,75%,.35)`; g.lineWidth = 2;
    for (let i = -h; i < w; i += 14) { g.beginPath(); g.moveTo(i, h); g.lineTo(i + h * 0.7, 0); g.stroke(); }
  }
  const glow = g.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w, h) * 0.55);
  glow.addColorStop(0, `hsla(${h1},100%,75%,.85)`); glow.addColorStop(1, "transparent");
  g.fillStyle = glow; g.fillRect(0, 0, w, h);
  // jagged impact burst (comic "explosion" balloon)
  const spikes = 11 + Math.floor(r() * 6), R = Math.min(w, h) * (0.22 + r() * 0.16);
  g.beginPath();
  for (let i = 0; i <= spikes * 2; i++) {
    const a = (i / (spikes * 2)) * Math.PI * 2, rr = i % 2 ? R * (0.45 + r() * 0.15) : R;
    g.lineTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr);
  }
  g.closePath();
  g.fillStyle = `hsla(${(h2 + 180) % 360},95%,62%,.85)`; g.fill();
  g.lineWidth = Math.max(3, R * 0.05); g.strokeStyle = "rgba(0,0,0,.75)"; g.stroke();
  // halftone (one small tile, repeated)
  g.fillStyle = g.createPattern(halftoneTile(), "repeat");
  g.fillRect(0, 0, w, h);
  // caption / sound effect
  const sfx = r() < 0.4;
  g.font = `700 ${Math.round(h * (sfx ? 0.2 : 0.17))}px Oswald, "Arial Narrow", Impact, sans-serif`;
  g.textBaseline = "bottom";
  g.lineWidth = Math.max(3, h * 0.02); g.strokeStyle = "#000"; g.fillStyle = sfx ? "#ffe14d" : "#fff";
  const text = sfx ? SFX[Math.floor(r() * SFX.length)] : label;
  const tx = w * 0.06, ty = sfx ? h * 0.32 : h * 0.95;
  g.save(); if (sfx) { g.translate(tx, ty); g.rotate(-0.12); g.strokeText(text, 0, 0); g.fillText(text, 0, 0); } else { g.strokeText(text, tx, ty); g.fillText(text, tx, ty); } g.restore();
  g.strokeStyle = "#0b0b0b"; g.lineWidth = Math.max(4, w * 0.012); g.strokeRect(0, 0, w, h);
  return c;
}

/** A comic page: cream paper with a 3-5 panel grid. */
const LAYOUTS = [[[0, 0, 2, 1], [0, 1, 1, 1], [1, 1, 1, 1]], [[0, 0, 1, 1], [1, 0, 1, 1], [0, 1, 2, 1]],
  [[0, 0, 1, 2], [1, 0, 1, 1], [1, 1, 1, 1]], [[0, 0, 2, 1], [0, 1, 2, 1]], [[0, 0, 1, 1], [1, 0, 1, 1], [0, 1, 1, 1], [1, 1, 1, 1]]];
function makePage(w, h, i) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const g = c.getContext("2d");
  g.fillStyle = "#f1e6cc"; g.fillRect(0, 0, w, h);
  const pad = w * 0.035, gap = w * 0.02, cw = (w - pad * 2 - gap) / 2, ch = (h - pad * 2 - gap) / 2;
  LAYOUTS[i % LAYOUTS.length].forEach(([x, y, sw, sh], k) => {
    const pw = cw * sw + gap * (sw - 1), ph = ch * sh + gap * (sh - 1);
    g.drawImage(makePanel(Math.round(pw), Math.round(ph), i * 10 + k, WORDS[(i * 3 + k) % WORDS.length]), pad + x * (cw + gap), pad + y * (ch + gap));
  });
  g.fillStyle = "rgba(120,90,40,.08)"; g.fillRect(0, 0, w, h);
  return c;
}

// ---------------------------------------------------------------- component
export default function Intro({ onDone }) {
  const root = useRef(null);
  const canvas = useRef(null);
  const doneRef = useRef(false);
  const rafRef = useRef(0);
  const doneCb = useRef(onDone);
  doneCb.current = onDone;

  const finish = useCallback(() => {
    if (doneRef.current) return;
    doneRef.current = true;
    cancelAnimationFrame(rafRef.current);
    try { sessionStorage.setItem(SEEN_KEY, "1"); } catch { /* private mode */ }
    root.current?.classList.add("out");
    document.body.classList.remove("lock");
    setTimeout(() => doneCb.current?.(), 700);
  }, []);

  useEffect(() => {
    const cv = canvas.current;
    const ctx = cv.getContext?.("2d");
    document.body.classList.add("lock");
    window.scrollTo(0, 0);
    const onKey = (e) => { if (e.key === "Escape") finish(); };
    window.addEventListener("keydown", onKey);
    root.current?.querySelector(".skip")?.focus({ preventScroll: true });
    if (!ctx) return () => window.removeEventListener("keydown", onKey); // jsdom
    const freeze = Number(new URLSearchParams(window.location.search).get("introAt"));
    let W = 0, H = 0, dpr = 1, pages = [], panels = [], start = 0, cancelled = false;
    const mask = document.createElement("canvas");

    const resize = () => {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      W = window.innerWidth; H = window.innerHeight;
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      cv.style.width = `${W}px`; cv.style.height = `${H}px`;
      if (lastT !== null) draw(lastT);
    };

    const titleSize = () => Math.min(W * 0.105, 170) * (W < 600 ? 0.92 : 1);

    const draw = (t) => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const bar = H * 0.09;
      // ---- background / trails
      if (t < 3.05) { ctx.fillStyle = `rgba(0,0,0,${t < 2.2 ? 0.55 : 0.32})`; ctx.fillRect(0, 0, W, H); }
      else {
        ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
        const gl = easeOut(prog(t, 3.05, 4.3));
        const rg = ctx.createRadialGradient(W / 2, H * 0.52, 0, W / 2, H * 0.52, Math.max(W, H) * 0.75);
        rg.addColorStop(0, `rgba(255,48,54,${gl})`); rg.addColorStop(0.3, `rgba(195,20,28,${gl})`);
        rg.addColorStop(0.65, `rgba(74,4,8,${gl})`); rg.addColorStop(1, "rgba(0,0,0,1)");
        ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
      }
      // ---- act 1: pages flipping, camera pulling back
      if (t < 3.05) {
        const cam = easeInOut(prog(t, 0, 3.0));
        const scale = 1.55 - 0.5 * cam, rot = (-4 + 4 * cam) * Math.PI / 180;
        const pw = Math.min(W * 0.86, H * 1.35), ph = pw * 0.66;
        ctx.save();
        ctx.translate(W / 2 + W * 0.06 * (1 - cam), H / 2); ctx.rotate(rot); ctx.scale(scale, scale);
        // flip schedule: accelerating
        let at = 0.25, idx = 0;
        const sched = [];
        for (let i = 0; i < pages.length; i++) { const d = Math.max(0.07, 0.42 - i * 0.022); sched.push([at, d]); at += Math.max(0.055, 0.26 - i * 0.013); }
        for (let i = 0; i < pages.length; i++) if (t >= sched[i][0] + sched[i][1]) idx = i + 1;
        // the page underneath, then the flipping one on top
        const under = pages[Math.min(idx + 1, pages.length - 1)], cur = pages[Math.min(idx, pages.length - 1)];
        ctx.drawImage(under, -pw / 2, -ph / 2, pw, ph);
        const [s0, d0] = sched[Math.min(idx, sched.length - 1)];
        const f = easeInOut(prog(t, s0, s0 + d0));
        const sx = Math.cos(f * Math.PI); // 1 -> -1 around the spine (left edge)
        ctx.save();
        ctx.translate(-pw / 2, 0); ctx.scale(sx, 1); ctx.translate(pw / 2, 0);
        ctx.drawImage(cur, -pw / 2, -ph / 2, pw, ph);
        ctx.fillStyle = `rgba(0,0,0,${0.55 * Math.sin(f * Math.PI)})`; ctx.fillRect(-pw / 2, -ph / 2, pw, ph);
        ctx.restore();
        ctx.shadowColor = "rgba(0,0,0,.6)";
        ctx.restore();
      }
      // ---- act 2a: hard-cut montage + streaks + flash
      if (t >= 2.55 && t < 3.25) {
        const p = panels[Math.floor(t * 14) % panels.length];
        const z = 1.08 + (t * 14 % 1) * 0.12;
        ctx.globalAlpha = 0.9;
        ctx.drawImage(p, W / 2 - (W * z) / 2, H / 2 - (H * z) / 2, W * z, H * z);
        ctx.globalAlpha = 1;
      }
      if (t >= 2.85 && t < 4.1) {
        const s = prog(t, 2.85, 4.1);
        ctx.save(); ctx.translate(W / 2, H / 2); ctx.rotate(s * 0.45);
        ctx.globalAlpha = s < 0.3 ? s / 0.3 : 1 - (s - 0.3) / 0.7;
        const R = Math.hypot(W, H) * (0.4 + s * 1.4);
        for (let i = 0; i < 40; i++) {
          ctx.rotate((Math.PI * 2) / 40);
          const grad = ctx.createLinearGradient(R * 0.15, 0, R, 0);
          grad.addColorStop(0, "rgba(255,80,80,0)"); grad.addColorStop(1, "rgba(255,110,110,.55)");
          ctx.fillStyle = grad;
          ctx.beginPath(); ctx.moveTo(R * 0.15, -2); ctx.lineTo(R, -R * 0.03); ctx.lineTo(R, R * 0.03); ctx.lineTo(R * 0.15, 2); ctx.fill();
        }
        ctx.restore(); ctx.globalAlpha = 1;
      }
      // ---- act 2b/3: title
      if (t >= 3.05) {
        const fs = titleSize();
        const pull = easeOut(prog(t, 3.05, 5.1));
        const sc = 5.5 - 4.5 * pull;
        ctx.save();
        ctx.translate(W / 2, H / 2 - fs * 0.15); ctx.scale(sc, sc);
        ctx.font = `700 ${fs}px Oswald, "Arial Narrow", Impact, sans-serif`;
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        const tw = ctx.measureText(TITLE).width, padX = fs * 0.26, padY = fs * 0.12;
        const slab = easeInOut(prog(t, 5.1, 5.65));
        if (slab > 0) { // glossy red slab sweeping out from the centre
          const sw = (tw + padX * 2) * slab, sh = fs + padY * 2;
          const sg = ctx.createLinearGradient(0, -sh / 2, 0, sh / 2);
          sg.addColorStop(0, "#ff4146"); sg.addColorStop(0.42, "#e62429"); sg.addColorStop(1, "#9b0f16");
          ctx.shadowColor = "rgba(0,0,0,.6)"; ctx.shadowBlur = fs * 0.4; ctx.shadowOffsetY = fs * 0.1;
          ctx.fillStyle = sg; ctx.fillRect(-sw / 2, -sh / 2, sw, sh);
          ctx.shadowColor = "transparent";
          ctx.fillStyle = "rgba(255,255,255,.35)"; ctx.fillRect(-sw / 2, -sh / 2, sw, Math.max(1, fs * 0.02));
        }
        const white = prog(t, 5.25, 5.55);
        // letters: montage masked to the glyphs (offscreen), cross-fading to white
        if (white < 1) {
          const bw = Math.ceil(tw + padX * 2), bh = Math.ceil(fs * 1.3);
          if (mask.width !== bw || mask.height !== bh) { mask.width = bw; mask.height = bh; }
          const m = mask.getContext("2d");
          m.globalCompositeOperation = "source-over"; m.clearRect(0, 0, bw, bh);
          m.font = ctx.font; m.textAlign = "center"; m.textBaseline = "middle"; m.fillStyle = "#fff";
          m.fillText(TITLE, bw / 2, bh / 2);
          m.globalCompositeOperation = "source-in";
          const p = panels[Math.floor(t * 11) % panels.length];
          m.drawImage(p, 0, 0, bw, bh);
          ctx.globalAlpha = 1 - white;
          ctx.drawImage(mask, -bw / 2, -bh / 2);
          ctx.globalAlpha = 1;
        }
        if (white > 0) {
          ctx.globalAlpha = white; ctx.fillStyle = "#fff";
          ctx.shadowColor = "rgba(0,0,0,.25)"; ctx.shadowOffsetY = fs * 0.02;
          ctx.fillText(TITLE, 0, 0); ctx.globalAlpha = 1; ctx.shadowColor = "transparent";
        }
        // light sweep across the letters
        const sh = prog(t, 5.55, 6.6);
        if (sh > 0 && sh < 1) {
          ctx.save();
          ctx.beginPath(); ctx.rect(-tw / 2 - padX, -fs / 2 - padY, tw + padX * 2, fs + padY * 2); ctx.clip();
          const x = -tw / 2 - padX + (tw + padX * 2) * (sh * 1.4 - 0.2);
          const lg = ctx.createLinearGradient(x - fs * 0.6, 0, x + fs * 0.6, 0);
          lg.addColorStop(0, "rgba(255,255,255,0)"); lg.addColorStop(0.5, "rgba(255,255,255,.6)"); lg.addColorStop(1, "rgba(255,255,255,0)");
          ctx.fillStyle = lg; ctx.transform(1, 0, -0.35, 1, 0, 0); ctx.fillRect(x - fs, -fs, fs * 2, fs * 2);
          ctx.restore();
        }
        ctx.restore();
        // flare streak across the screen
        const fl = prog(t, 5.15, 6.45);
        if (fl > 0 && fl < 1) {
          const len = W * 1.4 * Math.min(1, fl / 0.4) * (1 + Math.max(0, fl - 0.4) * 0.3);
          const a = fl < 0.4 ? 1 : 1 - (fl - 0.4) / 0.6;
          const y = H / 2 - fs * 0.15;
          const lg = ctx.createLinearGradient(W / 2 - len / 2, 0, W / 2 + len / 2, 0);
          lg.addColorStop(0, "rgba(255,200,200,0)"); lg.addColorStop(0.5, `rgba(255,255,255,${a})`); lg.addColorStop(1, "rgba(255,200,200,0)");
          ctx.save(); ctx.shadowColor = `rgba(255,60,60,${0.8 * a})`; ctx.shadowBlur = 30;
          ctx.fillStyle = lg; ctx.fillRect(W / 2 - len / 2, y - 1.5, len, 3); ctx.restore();
          const og = ctx.createRadialGradient(W / 2, y, 0, W / 2, y, fs * 1.2);
          og.addColorStop(0, `rgba(255,255,255,${0.35 * a})`); og.addColorStop(1, "rgba(255,255,255,0)");
          ctx.fillStyle = og; ctx.fillRect(0, y - fs * 1.2, W, fs * 2.4);
        }
        // tagline: letter-spacing tightens as it fades in
        const tg = easeOut(prog(t, 5.6, 7.0));
        if (tg > 0) {
          const ts = Math.max(11, Math.min(22, W * 0.015));
          const spacing = ts * (1.4 - 0.8 * tg);
          ctx.font = `400 ${ts}px Oswald, "Arial Narrow", sans-serif`;
          ctx.fillStyle = `rgba(255,255,255,${0.9 * tg})`; ctx.textBaseline = "middle";
          const chars = [...TAGLINE];
          const total = chars.reduce((s, ch) => s + ctx.measureText(ch).width + spacing, -spacing);
          let x = W / 2 - total / 2;
          const y = H / 2 - fs * 0.15 + fs * 0.62 + padY + ts * 1.6;
          for (const ch of chars) { ctx.fillText(ch, x, y); x += ctx.measureText(ch).width + spacing; }
        }
      }
      // white flash
      const fla = prog(t, 2.9, 3.4);
      if (fla > 0 && fla < 1) { ctx.fillStyle = `rgba(255,255,255,${0.85 * (1 - fla)})`; ctx.fillRect(0, 0, W, H); }
      // film grain
      ctx.fillStyle = "rgba(255,255,255,.035)";
      const gr = rng(Math.floor(t * 24) + 1);
      for (let i = 0; i < 140; i++) ctx.fillRect(gr() * W, gr() * H, 1.5, 1.5);
      // letterbox + final fade
      ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, bar); ctx.fillRect(0, H - bar, W, bar);
      const out = prog(t, 6.95, 7.6);
      if (out > 0) { ctx.fillStyle = `rgba(7,7,10,${out})`; ctx.fillRect(0, 0, W, H); }
    };

    let lastT = null;
    const loop = (now) => {
      if (cancelled) return;
      if (!start) start = now;
      const t = Number.isFinite(freeze) && freeze > 0 ? freeze : (now - start) / 1000;
      lastT = t;
      draw(t);
      if (!(freeze > 0) && t * 1000 >= INTRO_MS) { finish(); return; }
      rafRef.current = requestAnimationFrame(loop);
    };

    const boot = async () => {
      resize();
      ctx.fillStyle = "#000"; ctx.fillRect(0, 0, cv.width, cv.height);
      try { await Promise.race([document.fonts?.load(`700 120px Oswald`), new Promise((r) => setTimeout(r, 900))]); } catch { /* fallback font */ }
      if (cancelled) return;
      const pw = Math.round(Math.min(1100, W * 0.86)), ph = Math.round(pw * 0.66);
      pages = Array.from({ length: 22 }, (_, i) => makePage(pw, ph, i));
      panels = Array.from({ length: 24 }, (_, i) => makePanel(640, 400, 100 + i, WORDS[(i * 7) % WORDS.length]));
      rafRef.current = requestAnimationFrame(loop);
    };
    boot();
    window.addEventListener("resize", resize);
    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", resize);
      document.body.classList.remove("lock");
    };
  }, [finish]);

  return (
    <div id="intro" ref={root} role="dialog" aria-modal="true" aria-label="Opening sequence">
      <canvas ref={canvas} aria-hidden="true" />
      <span className="sr-only">Ask the Multiverse. Every reality, every era.</span>
      <button type="button" className="skip" onClick={finish}>SKIP &#9656;</button>
    </div>
  );
}
