"""Optional JS effects layer (all free/open source, rendered headless, deterministic, nothing fetched at render time):
  PixiJS (MIT)          animated light rays + drifting motes overlay (alpha loop)
  HyperFrames (Apache)  HTML/GSAP composition -> alpha MOV: animated geometric frame overlay (loop)
  gl-transitions (MIT)  GLSL transitions rendered between scenes (duration-preserving)
  p5.js (LGPL-2.1)      generative star-lattice backgrounds for the geometric scenes (used unmodified, loaded from node_modules)
Everything degrades gracefully: if Node >= 22, `npm ci` in js/, or Chromium are missing, available() is False and the engine renders exactly as before."""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, tempfile
from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "js"
GOOD_TRANSITIONS = ["CrossWarp", "Dreamy", "DreamyZoom", "SimpleZoom", "CrossZoom", "BloomDissolve", "GlowDissolve", "SmokeDissolve", "DefocusBlur", "DirectionalWarp"]

def _env() -> dict:
    e = dict(os.environ, HYPERFRAMES_NO_TELEMETRY="1", DO_NOT_TRACK="1")
    if e.get("IVS_CHROME"):
        e.setdefault("PRODUCER_HEADLESS_SHELL_PATH", e["IVS_CHROME"]); e.setdefault("PUPPETEER_EXECUTABLE_PATH", e["IVS_CHROME"])
    return e

def available() -> tuple[bool, str]:
    node = shutil.which("node")
    if not node: return False, "node not installed"
    try: major = int(subprocess.run([node, "-v"], capture_output=True, text=True).stdout.strip().lstrip("v").split(".")[0])
    except Exception: return False, "cannot read node version"
    if major < 22: return False, f"node {major} < 22"
    if not (JS / "node_modules" / "pixi.js").exists(): return False, "run `npm ci` in js/"
    return True, "ok"

def enabled(cfg: dict) -> bool:
    j = (cfg.get("js_fx") or {}); v = j.get("enabled", "auto")
    if v is False: return False
    ok, _ = available()
    return ok

def _node(spec: dict) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f: json.dump(spec, f); p = f.name
    try:
        r = subprocess.run(["node", str(JS / "fx.mjs"), p], capture_output=True, text=True, env=_env(), timeout=1500)
        if r.returncode != 0: raise RuntimeError(f"fx.mjs {spec['mode']} failed: {(r.stderr or r.stdout)[-400:]}")
    finally: os.unlink(p)

def _ff(*a):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *map(str, a)], capture_output=True, text=True)
    if r.returncode: raise RuntimeError("ffmpeg: " + r.stderr[-400:])

def _key(*a) -> str: return hashlib.sha1(json.dumps(a, sort_keys=True, default=str).encode()).hexdigest()[:12]

def pixi_loop(cache: Path, w: int, h: int, fps: int, color="#ffe9b0", seed=1, seconds=6, **kw) -> Path:
    out = cache / "jsfx" / f"pixi_{w}x{h}_{fps}_{_key(color, seed, seconds, kw)}.mov"
    if out.exists(): return out
    out.parent.mkdir(parents=True, exist_ok=True); d = Path(tempfile.mkdtemp())
    _node({"mode": "pixi", "w": w, "h": h, "fps": fps, "seconds": seconds, "seed": seed, "color": color, "out": str(d), **kw})
    _ff("-framerate", fps, "-i", d / "%05d.png", "-c:v", "png", "-pix_fmt", "rgba", out); shutil.rmtree(d, ignore_errors=True); return out

def frame_loop(cache: Path, w: int, h: int, fps: int, color="#d9b46a", seconds=6) -> Path:
    """HyperFrames: render js/hf_frame (portrait 1080x1920, transparent) to an alpha MOV loop, then scale to the video size."""
    out = cache / "jsfx" / f"frame_{w}x{h}_{fps}_{_key(color, seconds)}.mov"
    if out.exists(): return out
    out.parent.mkdir(parents=True, exist_ok=True); proj = Path(tempfile.mkdtemp()); src = JS / "hf_frame"
    for n in ("hyperframes.json", "meta.json"): shutil.copy(src / n, proj / n)
    shutil.copy(JS / "node_modules" / "gsap" / "dist" / "gsap.min.js", proj / "gsap.min.js")
    (proj / "index.html").write_text((src / "index.template.html").read_text().replace("__DUR__", str(seconds)).replace("__COLOR__", color), encoding="utf-8")
    raw = proj / "frame.mov"
    r = subprocess.run(["npx", "--no-install", "hyperframes", "render", str(proj), "-o", str(raw), "--format", "mov", "-q", "draft", "-f", str(fps)],
                       cwd=JS, capture_output=True, text=True, env=_env(), timeout=1500)
    if r.returncode or not raw.exists(): raise RuntimeError("hyperframes render failed: " + (r.stderr or r.stdout)[-400:])
    _ff("-i", raw, "-vf", f"scale={w}:{h}:flags=lanczos,format=rgba", "-c:v", "png", "-pix_fmt", "rgba", "-an", out); shutil.rmtree(proj, ignore_errors=True); return out

def p5_clip(cache: Path, w: int, h: int, fps: int, seconds: float, palette=("#0b1a2b", "#d9b46a", "#3b7f8c"), seed=1, points=8) -> Path:
    sec = max(2, int(seconds + 0.999))
    out = cache / "jsfx" / f"p5_{w}x{h}_{fps}_{_key(palette, seed, sec, points)}.mp4"
    if out.exists(): return out
    out.parent.mkdir(parents=True, exist_ok=True); d = Path(tempfile.mkdtemp())
    _node({"mode": "p5", "w": w, "h": h, "fps": fps, "seconds": sec, "seed": seed, "palette": list(palette), "points": points, "out": str(d)})
    _ff("-framerate", fps, "-i", d / "%05d.png", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out); shutil.rmtree(d, ignore_errors=True); return out

def _size(p: Path) -> tuple[int, int]:
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout.strip().split(",")
    return int(o[0]), int(o[1])

def transition_pass(video: Path, out: Path, boundaries: list[float], fps: int, seed: str, seconds=0.6, names=None) -> Path:
    """Replace a window centred on each scene boundary with a GL-Transitions render of (end of A -> start of B). Duration and audio sync are unchanged."""
    names = names or GOOD_TRANSITIONS; w, h = _size(video); k = max(2, round(seconds * fps / 2)); work = Path(tempfile.mkdtemp())
    cuts = [round(b * fps) for b in boundaries]; cuts = [c for c in cuts if c - k > 0]
    total = int(subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip() or 0)
    pieces, pos = [], 0
    def seg(a, b, name):
        p = work / name
        _ff("-i", video, "-vf", f"select='between(n\\,{a}\\,{b - 1})',setpts=N/{fps}/TB", "-an", "-r", fps, "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", p); return p
    for i, c in enumerate(cuts):
        if c + k > total or c - k < pos: continue
        if c - k > pos: pieces.append(seg(pos, c - k, f"s{i}a.mp4"))
        da, db = work / f"a{i}", work / f"b{i}"; da.mkdir(); db.mkdir()
        _ff("-i", video, "-vf", f"select='between(n\\,{c - k}\\,{c - 1})'", "-vsync", "0", da / "%05d.png")
        _ff("-i", video, "-vf", f"select='between(n\\,{c}\\,{c + k - 1})'", "-vsync", "0", db / "%05d.png")
        A = sorted(da.glob("*.png")); B = sorted(db.glob("*.png"))
        if len(A) < k or len(B) < k: continue
        nm = names[int(hashlib.sha1(f"{seed}:{i}".encode()).hexdigest(), 16) % len(names)]
        od = work / f"t{i}"
        _node({"mode": "transition", "name": nm, "w": w, "h": h, "fps": fps, "seconds": 2 * k / fps, "out": str(od),
               "from": [str(A[min(j, k - 1)]) for j in range(2 * k)], "to": [str(B[max(j - k, 0)]) for j in range(2 * k)]})
        t = work / f"t{i}.mp4"; _ff("-framerate", fps, "-i", od / "%05d.png", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", t)
        pieces.append(t); pos = c + k; shutil.rmtree(da); shutil.rmtree(db); shutil.rmtree(od)
    if not pieces: shutil.rmtree(work, ignore_errors=True); return video
    if pos < total: pieces.append(seg(pos, total, "tail.mp4"))
    lst = work / "l.txt"; lst.write_text("".join(f"file '{p}'\n" for p in pieces))
    _ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out); shutil.rmtree(work, ignore_errors=True); return out

def overlay_pass(video: Path, out: Path, layers: list[Path], fps: int) -> Path:
    """Composite looping alpha overlays (pixi / hyperframes) over the whole video."""
    if not layers: return video
    inp, chain, last = ["-i", str(video)], [], "0:v"
    for i, l in enumerate(layers, 1):
        inp += ["-stream_loop", "-1", "-i", str(l)]
        chain.append(f"[{last}][{i}:v]overlay=format=auto:shortest=1[v{i}]"); last = f"v{i}"
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip()
    _ff(*inp, "-filter_complex", ";".join(chain) + f";[{last}]format=yuv420p[vout]", "-map", "[vout]", "-t", dur, "-r", fps, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", out)
    return out
