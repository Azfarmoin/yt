// Headless JS effects renderer. Usage: node fx.mjs spec.json   (spec.mode: pixi | p5 | transition)
// Deterministic (seeded PRNG, time-driven), no network: all libraries are loaded from ./node_modules.
// Output: numbered PNG frames in spec.out (alpha preserved for pixi). Python (ivs/jsfx.py) encodes them with FFmpeg.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const here = path.dirname(new URL(import.meta.url).pathname);
const spec = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
fs.mkdirSync(spec.out, { recursive: true });
const W = spec.w, H = spec.h, N = Math.round(spec.seconds * spec.fps);
const lib = (p) => fs.readFileSync(path.join(here, "node_modules", p), "utf8");

const browser = await chromium.launch({
  executablePath: process.env.IVS_CHROME || undefined,
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox", "--allow-file-access-from-files"],
});
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
page.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 3; });
await page.setContent(`<html><body style="margin:0;background:transparent"><canvas id=c width=${W} height=${H}></canvas></body></html>`);
const save = async (i, opts = {}) => {
  const buf = await page.locator("#c").screenshot({ omitBackground: true, type: "png", ...opts });
  fs.writeFileSync(path.join(spec.out, String(i).padStart(5, "0") + ".png"), buf);
};

if (spec.mode === "pixi") {
  await page.addScriptTag({ content: lib("pixi.js/dist/pixi.min.js") });
  await page.evaluate(async ({ W, H, spec }) => {
    const rng = (s => () => { s |= 0; s = s + 0x6D2B79F5 | 0; let t = Math.imul(s ^ s >>> 15, 1 | s); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; })(spec.seed || 1);
    const app = new PIXI.Application();
    await app.init({ canvas: document.getElementById("c"), width: W, height: H, backgroundAlpha: 0, preference: "webgl", antialias: true, autoStart: false });
    app.ticker.stop();
    const L = spec.seconds, col = parseInt((spec.color || "#ffe9b0").slice(1), 16);
    const layer = new PIXI.Container(); app.stage.addChild(layer);
    // soft light rays (slow, periodic over L)
    const rays = []; const rayLayer = new PIXI.Container(); rayLayer.filters = [new PIXI.BlurFilter({ strength: 14, quality: 3 })]; layer.addChild(rayLayer);
    for (let i = 0; i < (spec.rays ?? 3); i++) {
      const g = new PIXI.Graphics(); const x0 = rng() * W, w = W * (0.10 + rng() * 0.14);
      g.poly([x0 - w * 0.2, -50, x0 + w * 0.2, -50, x0 + w * 1.4, H + 50, x0 - w * 1.0, H + 50]).fill({ color: col, alpha: 1 });
      g.blendMode = "add"; g._ph = rng() * Math.PI * 2; g._amp = spec.ray_alpha ?? 0.09; rayLayer.addChild(g); rays.push(g);
    }
    // drifting motes: integer wraps per loop => seamless loop
    const motes = [];
    for (let i = 0; i < (spec.motes ?? 70); i++) {
      const g = new PIXI.Graphics(); const r = 1 + rng() * 3.2;
      g.circle(0, 0, r * 2.4).fill({ color: col, alpha: 0.10 }); g.circle(0, 0, r).fill({ color: col, alpha: 0.8 });
      g.blendMode = "add"; g._x = rng() * W; g._y = rng() * H; g._kx = Math.round((rng() - 0.5) * 2); g._ky = -(1 + Math.floor(rng() * 2)) * (spec.rise ?? 1);
      g._ph = rng() * Math.PI * 2; g._sw = 6 + rng() * 22; g._tw = 1 + Math.floor(rng() * 3); layer.addChild(g); motes.push(g);
    }
    window.__draw = (t) => {
      const u = t / L, TAU = Math.PI * 2;
      for (const g of rays) g.alpha = Math.max(0, g._amp * (0.55 + 0.45 * Math.sin(TAU * u + g._ph)));
      for (const g of motes) {
        g.x = ((g._x + g._kx * W * u + Math.sin(TAU * u + g._ph) * g._sw) % W + W) % W;
        g.y = ((g._y + g._ky * H * u) % H + H) % H;
        g.alpha = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(TAU * g._tw * u + g._ph));
      }
      app.render();
    };
  }, { W, H, spec });
  for (let i = 0; i < N; i++) { await page.evaluate((t) => window.__draw(t), i / spec.fps); await save(i); }
} else if (spec.mode === "p5") {
  // generative Islamic star-polygon lattice (geometry only: no figures). noLoop + manual redraw => frame-exact.
  await page.addScriptTag({ content: lib("p5/lib/p5.min.js") });
  await page.evaluate(({ W, H, spec }) => {
    new p5((p) => {
      const c = document.getElementById("c");
      p.setup = () => { const cv = p.createCanvas(W, H); cv.elt.id = "c2"; c.replaceWith(cv.elt); cv.elt.id = "c"; p.noLoop(); p.pixelDensity(1); p.randomSeed(spec.seed || 1); };
      window.__draw = (t) => { p.redraw(); window.__t = t; };
      p.draw = () => {
        const t = window.__t || 0, u = t / spec.seconds, TAU = Math.PI * 2;
        const [bg, fg, acc] = spec.palette || ["#0b1a2b", "#d9b46a", "#3b7f8c"];
        p.background(bg);
        const cell = Math.max(W, H) / (spec.cells || 6), pts = spec.points || 8;
        p.noFill(); p.strokeWeight(Math.max(1.5, W / 360));
        for (let gy = -1; gy <= H / cell + 1; gy++) for (let gx = -1; gx <= W / cell + 1; gx++) {
          const cx = gx * cell + (gy % 2 ? cell / 2 : 0), cy = gy * cell * 0.88;
          const breathe = 0.82 + 0.12 * Math.sin(TAU * u + (gx + gy) * 0.7);
          const rot = TAU * u / pts;                       // one full star step per loop => seamless
          const R = cell * 0.5 * breathe, r = R * 0.52;
          p.stroke(fg); p.push(); p.translate(cx, cy); p.rotate(rot * (((gx + gy) & 1) ? 1 : -1));
          p.beginShape(); for (let k = 0; k < pts * 2; k++) { const a = (k * Math.PI) / pts, rr = k % 2 ? r : R; p.vertex(Math.cos(a) * rr, Math.sin(a) * rr); } p.endShape(p.CLOSE);
          p.stroke(acc); p.circle(0, 0, r * 1.3); p.pop();
        }
        const v = p.drawingContext.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.2, W / 2, H / 2, Math.max(W, H) * 0.75);
        v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, "rgba(0,0,0,0.55)"); p.drawingContext.fillStyle = v; p.drawingContext.fillRect(0, 0, W, H);
      };
    });
  }, { W, H, spec });
  await page.waitForFunction(() => typeof window.__draw === "function");
  for (let i = 0; i < N; i++) { await page.evaluate((t) => window.__draw(t), i / spec.fps); await save(i); }
} else if (spec.mode === "transition") {
  const T = require("gl-transitions").find((x) => x.name === spec.name);
  if (!T) { console.error("unknown transition " + spec.name); process.exit(2); }
  const toData = (f) => "data:image/png;base64," + fs.readFileSync(f).toString("base64");
  const A = spec.from.map(toData), B = spec.to.map(toData);      // N frames each (already time-aligned by Python)
  await page.evaluate(async ({ W, H, T, A, B }) => {
    const gl = document.getElementById("c").getContext("webgl", { preserveDrawingBuffer: true, premultipliedAlpha: false });
    const vs = "attribute vec2 p; varying vec2 _uv; void main(){ _uv = vec2(0.5,0.5)*(p+vec2(1.0)); gl_Position = vec4(p,0.0,1.0); }";
    const fs = `precision highp float; varying vec2 _uv; uniform sampler2D from, to; uniform float progress, ratio;
      vec4 getFromColor(vec2 uv){ return texture2D(from, uv); } vec4 getToColor(vec2 uv){ return texture2D(to, uv); }
      ${T.glsl}
      void main(){ gl_FragColor = transition(_uv); }`;
    const sh = (t, s) => { const o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o); if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(o)); return o; };
    const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(pr);
    if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr)); gl.useProgram(pr);
    const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.uniform1f(gl.getUniformLocation(pr, "ratio"), W / H); gl.uniform1i(gl.getUniformLocation(pr, "from"), 0); gl.uniform1i(gl.getUniformLocation(pr, "to"), 1);
    for (const [k, v] of Object.entries(T.defaultParams || {})) {          // transition-specific uniforms with their documented defaults
      const l = gl.getUniformLocation(pr, k); if (!l) continue; const ty = T.paramsTypes[k];
      if (ty === "float") gl.uniform1f(l, v); else if (ty === "int") gl.uniform1i(l, v); else if (ty === "bool") gl.uniform1i(l, v ? 1 : 0);
      else if (ty === "vec2") gl.uniform2fv(l, v); else if (ty === "vec3") gl.uniform3fv(l, v); else if (ty === "vec4") gl.uniform4fv(l, v);
    }
    const img = (s) => new Promise((r) => { const i = new Image(); i.onload = () => r(i); i.src = s; });
    const tex = (unit) => { const t = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE); return t; };
    tex(0); tex(1);
    const up = (unit, im) => { gl.activeTexture(gl.TEXTURE0 + unit); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, im); };
    const pl = gl.getUniformLocation(pr, "progress");
    window.__draw = async (i, n) => {
      up(0, await img(A[i])); up(1, await img(B[i]));
      const x = (i + 0.5) / n, e = x * x * (3 - 2 * x);                 // smoothstep progress
      gl.uniform1f(pl, e); gl.viewport(0, 0, W, H); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };
  }, { W, H, T: { glsl: T.glsl, defaultParams: T.defaultParams, paramsTypes: T.paramsTypes }, A, B });
  const n = A.length;
  for (let i = 0; i < n; i++) { await page.evaluate(([i, n]) => window.__draw(i, n), [i, n]); await save(i); }
} else { console.error("unknown mode " + spec.mode); process.exit(2); }
await browser.close();
console.log("ok " + spec.mode + " " + spec.out);
