"""Faceless animated scenery for stories. NO people, prophets or sacred figures are ever drawn: only landscape, sky, sea,
light and geometry. Layers are generated with Pillow/numpy (no assets, no licenses) and animated by FFmpeg overlay
expressions (parallax scroll, rising sun, drifting moon/clouds, twinkling stars)."""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from . import visuals as V
from .visuals import W, H
from .audio import run
from . import actors as AC

P = 1080                         # scroll period; tiles are 2*P wide so x = -mod(t*v, P) never shows a gap

def _hex(c): return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))

# tag -> scene spec. layers: (kind, rgb color, baseline fraction of H, amplitude px, speed px/s)
SCENES = {
    "desert_night": dict(sky=("#070b24", "#2a1b4d"), orb=("moon", 0.13), stars=True, layers=[
        ("dune", "#1b1740", 0.62, 90, 8), ("dune", "#150f33", 0.72, 110, 16), ("dune", "#0d0922", 0.83, 130, 28)]),
    "desert_dawn": dict(sky=("#1c3b57", "#f2a65a"), orb=("sun", 0.68), stars=False, layers=[
        ("dune", "#c97a43", 0.66, 90, 8), ("dune", "#a85d33", 0.76, 110, 16), ("dune", "#7a3f26", 0.86, 130, 28)]),
    "sea_calm": dict(sky=("#17496a", "#9fd3e6"), orb=("sun", 0.62), stars=False, layers=[
        ("wave", "#1f6f95", 0.66, 26, 30), ("wave", "#185a7c", 0.75, 34, 52), ("wave", "#103f59", 0.86, 40, 80)]),
    "sea_storm": dict(sky=("#0c1118", "#3b4756"), orb=None, stars=False, layers=[
        ("cloud", "#222c38", 0.20, 120, 22), ("wave", "#16303f", 0.66, 52, 70), ("wave", "#10222d", 0.76, 66, 110), ("wave", "#0a1720", 0.87, 78, 160)]),
    "night_sea": dict(sky=("#050914", "#142645"), orb=("moon", 0.13), stars=True, layers=[
        ("wave", "#0f2a4a", 0.68, 28, 26), ("wave", "#0b2039", 0.78, 36, 44), ("wave", "#071627", 0.88, 44, 66)]),
    "mountain_dawn": dict(sky=("#27456b", "#f0b98a"), orb=("sun", 0.66), stars=False, layers=[
        ("mountain", "#5d6f8f", 0.62, 220, 0), ("mist", "#f6e7d8", 0.66, 60, 14), ("mountain", "#3d4a66", 0.74, 260, 0), ("mist", "#f6e7d8", 0.80, 70, 22)]),
    "sky_stars": dict(sky=("#04061a", "#1b2250"), orb=("moon", 0.13), stars=True, layers=[
        ("cloud", "#232b5c", 0.30, 80, 10), ("cloud", "#1a2048", 0.55, 90, 18)]),
}
SCENES.update({
    "geometric_night": dict(sky=("#050b1a", "#16284a"), orb=None, stars=False, layers=[("pattern", "#d9b36a", 180, 46, 5), ("pattern", "#c9a45c", 120, 70, 11), ("pattern", "#e6c987", 360, 38, 3)]),
    "geometric_dawn":  dict(sky=("#1d3a4a", "#e7b77a"), orb=None, stars=False, layers=[("pattern", "#fff1d0", 180, 40, 6), ("pattern", "#f5d9a2", 120, 60, 12), ("pattern", "#ffffff", 360, 30, 3)]),
})
DEFAULT_TAG = "sky_stars"
FADE_COLOR = "black"      # set per film by the Director's transition family

def _gradient(top, bot) -> Image.Image:
    a, b = np.array(_hex(top), np.float32), np.array(_hex(bot), np.float32)
    t = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    arr = (a * (1 - t) + b * t) * np.ones((1, W, 1), np.float32)
    return Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")

def _ridge(kind, base, amp, seed):
    """periodic (period P) height function using integer harmonics => seamless scrolling"""
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 2 * np.pi, 4)
    ks = (1, 2, 3, 5) if kind == "dune" else (2, 3, 5, 8)
    wt = (1.0, 0.55, 0.3, 0.15)
    def f(x): return base - amp * sum(w * math.sin(2 * math.pi * k * x / P + p) for k, w, p in zip(ks, wt, ph)) / 2
    return f

def tile_layer(kind, color, base_frac, amp, seed=1) -> Image.Image:
    if kind == "pattern":                                      # Islamic geometric lattice: base_frac = cell px (divides P), amp = alpha
        from .assets import pattern_tile
        return pattern_tile(int(base_frac), color, int(amp), 2 * P, H, P)
    img = Image.new("RGBA", (2 * P, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img); c = _hex(color)
    if kind in ("dune", "wave"):
        f = _ridge(kind, base_frac * H, amp, seed)
        pts = [(x, f(x)) for x in range(0, 2 * P + 1, 6)]
        d.polygon(pts + [(2 * P, H), (0, H)], fill=c + (255,))
        if kind == "wave":                                      # soft crest highlight
            d.line(pts, fill=tuple(min(255, v + 45) for v in c) + (140,), width=3)
    elif kind in ("cloud", "mist"):
        rng = np.random.default_rng(seed + 11)
        n = 7 if kind == "cloud" else 5
        for i in range(n):
            cx = rng.uniform(0, P); cy = base_frac * H + rng.uniform(-amp, amp)
            rw, rh = rng.uniform(180, 340), rng.uniform(34, 70) * (1.0 if kind == "cloud" else 0.8)
            for off in (0, P):                                   # draw twice => seamless wrap
                d.ellipse([cx + off - rw, cy - rh, cx + off + rw, cy + rh], fill=c + (int(120 if kind == "cloud" else 90),))
        img = img.filter(ImageFilter.GaussianBlur(26))
    return img

def mountain_layer(color, base_frac, amp, seed=2) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img); c = _hex(color)
    rng = np.random.default_rng(seed); ph = rng.uniform(0, 2 * np.pi, 4)
    def f(x):
        v = sum(w * math.sin(2 * math.pi * k * x / (W * 1.3) + p) for k, w, p in zip((1, 2, 3, 5), (1, .6, .35, .18), ph))
        return base_frac * H - amp * (0.55 + 0.45 * abs(v) / 2.1)        # abs() => pointed peaks, soft valleys
    pts = [(x, f(x)) for x in range(-10, W + 11, 5)]
    d.polygon(pts + [(W + 10, H), (-10, H)], fill=c + (255,))
    return img.filter(ImageFilter.GaussianBlur(1.0))

def orb_image(kind) -> Image.Image:
    s = 460; img = Image.new("RGBA", (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    col = (255, 232, 170) if kind == "moon" else (255, 214, 140)
    for r, a in ((220, 18), (170, 34), (120, 60), (84, 120)):
        d.ellipse([s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r], fill=col + (a,))
    d.ellipse([s / 2 - 62, s / 2 - 62, s / 2 + 62, s / 2 + 62], fill=(255, 246, 215, 255) if kind == "moon" else (255, 236, 180, 255))
    if kind == "moon":                                           # crescent: cut with a sky-colored disc is avoided (would show a seam); keep full moon
        pass
    img = img.filter(ImageFilter.GaussianBlur(1.5))
    if kind == "moon":                                           # dimmer moon: dense verse text can sit over it
        img.putalpha(img.getchannel("A").point(lambda v: int(v * 0.55)))
    return img

def frame_layer() -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img); g = _hex("#d9b36a")
    d.rounded_rectangle([40, 40, W - 40, H - 40], radius=28, outline=g + (150,), width=3)
    d.rounded_rectangle([54, 54, W - 54, H - 54], radius=22, outline=g + (70,), width=1)
    return img

def scrim_layer() -> Image.Image:
    """soft dark band behind the text so it stays readable on any scenery"""
    a = np.zeros((H, W), np.float32); y = np.arange(H)
    a[:] = (np.exp(-((y - H * 0.47) / (H * 0.2)) ** 4) * 150)[:, None]
    im = Image.new("RGBA", (W, H), (4, 6, 16, 0)); im.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
    return im

def build_assets(cache: Path) -> dict:
    """Render every scenery layer once; returns {tag: spec with file paths}. Cached on disk."""
    d = Path(cache) / "anim"; d.mkdir(parents=True, exist_ok=True)
    out = {"frame": str(d / "frame.png"), "scrim": str(d / "scrim.png")}
    if not (d / "frame.png").exists(): frame_layer().save(d / "frame.png")
    if not (d / "scrim.png").exists(): scrim_layer().save(d / "scrim.png")
    for kind in ("moon", "sun"):
        p = d / f"orb_{kind}.png"
        if not p.exists(): orb_image(kind).save(p)
        out[f"orb_{kind}"] = str(p)
    for tag, spec in SCENES.items():
        sky = d / f"{tag}_sky.png"
        if not sky.exists(): _gradient(*spec["sky"]).save(sky)
        files = []
        for i, (kind, color, base, amp, speed) in enumerate(spec["layers"]):
            p = d / f"{tag}_L{i}.png"
            if not p.exists():
                (mountain_layer(color, base, amp, i + 3) if kind == "mountain" else tile_layer(kind, color, base, amp, i + 1)).save(p)
            files.append((str(p), kind, speed))
        out[tag] = {"sky": str(sky), "layers": files, "orb": spec["orb"], "stars": spec["stars"]}
    return out

def make_stars(path: Path, fps: int, n: int = 90, seed: int = 21) -> Path:
    """Seamless 6 s twinkling starfield (white/gold), screen-blended over the scene."""
    path = Path(path)
    if path.exists(): return path
    import subprocess
    rng = np.random.default_rng(seed); frames = 6 * fps
    x = rng.integers(40, W - 40, n); y = rng.integers(40, int(H * 0.55), n)      # stars live in the sky only
    ph = rng.uniform(0, 2 * np.pi, n); sz = rng.integers(1, 4, n)
    pr = subprocess.Popen(["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", str(path)],
                          stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for f in range(frames):
        t = 2 * np.pi * f / frames; c = np.zeros((H, W, 3), np.uint8)
        for i in range(n):
            a = 0.2 + 0.8 * (0.5 + 0.5 * math.sin(2 * t + ph[i]))
            v = int(255 * a); r = int(sz[i])
            c[y[i] - r:y[i] + r + 1, x[i] - r:x[i] + r + 1] = (v, v, int(v * 0.85))
        pr.stdin.write(c.tobytes())
    pr.stdin.close(); err = pr.stderr.read(); pr.wait()
    if pr.returncode: raise RuntimeError(err.decode()[-300:])
    return path

# ---- kinetic hook: words pop in one by one ------------------------------------------------------------------
def hook_layers(text: str, out_dir: Path, size: int = 88, start=0.35, step=0.42) -> list[tuple[str, float]]:
    """One transparent PNG per word at its final position (English, LTR). Returns [(png, start_time)]."""
    f = V.font("en", size)
    lines = V.wrap(text, f, "en", W - 2 * 110)
    lh = int(size * 1.4); top = int(H * 0.47 - len(lines) * lh / 2)
    out, k = [], 0
    for li, line in enumerate(lines):
        total = f.getlength(line); x = (W - total) / 2; y = top + li * lh + lh // 2
        words = line.split(" ")
        for wi, w in enumerate(words):
            pre = f.getlength(" ".join(words[:wi]) + (" " if wi else ""))
            m = Image.new("L", (W, H), 0); ImageDraw.Draw(m).text((x + pre, y), w, font=f, fill=255, anchor="lm")
            rgb = Image.new("RGB", (W, H), (244, 239, 230)); layer = Image.merge("RGBA", (*rgb.split(), m))
            p = Path(out_dir) / f"hook_w{k}.png"; layer.save(p); out.append((str(p), start + k * step)); k += 1
    return out

# ---- the animated scene ------------------------------------------------------------------------------------------
def scene_clip(assets: dict, tag: str, text_png: str, dur: float, fps: int, out: Path, stars: str | None,
               hook_words: list | None = None, index: int = 0) -> Path:
    spec = assets.get(tag) or assets[DEFAULT_TAG]
    inputs = ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", spec["sky"]]
    chain, cur, n = [], "[b0]", 1
    chain.append("[0:v]format=rgba[b0]")
    def add_input(path, loop=True):
        nonlocal n
        inputs.extend(["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", path]); n += 1
        return n - 1
    step = 0
    def overlay(src_idx, x="0", y="0", extra=""):
        nonlocal cur, step
        step += 1; nxt = f"[b{step}]"
        chain.append(f"{cur}[{src_idx}:v]overlay=x='{x}':y='{y}':format=auto{extra}{nxt}"); cur = nxt
    if spec["stars"] and stars:
        inputs.extend(["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", stars]); si = n; n += 1
        step += 1; nxt = f"[b{step}]"
        chain.append(f"{cur}format=gbrp[g];[{si}:v]format=gbrp[st];[g][st]blend=all_mode=screen:all_opacity=0.9,format=rgba{nxt}"); cur = nxt
    if spec["orb"]:
        kind, ybase = spec["orb"]; oi = add_input(assets[f"orb_{kind}"])
        if kind == "moon":
            overlay(oi, x=f"{W * 0.70:.0f}+60*sin(2*PI*t/40)", y=f"{H * ybase:.0f}-30*sin(2*PI*t/55)")
        else:                                                   # sun rises slowly during the scene
            overlay(oi, x=f"{W * 0.5 - 230:.0f}", y=f"{H * ybase - 230:.0f}-90*t/{max(dur, 1):.2f}")
    for path, kind, speed in spec["layers"]:
        li = add_input(path)
        if speed:
            sgn = 1 if (index + len(chain)) % 2 == 0 else -1  # alternate direction between layers for depth
            overlay(li, x=(f"-mod(t*{speed}\\,{P})" if sgn > 0 else f"mod(t*{speed}\\,{P})-{P}"), y="0")
        else:
            overlay(li)
    overlay(add_input(assets["scrim"]))
    overlay(add_input(assets["frame"]))
    # text: hook words (kinetic) or a normal reveal
    if hook_words:
        for wp, st in hook_words:
            wi = add_input(wp)
            chain.append(f"[{wi}:v]format=rgba,fade=t=in:st={st:.2f}:d=0.22:alpha=1[w{wi}]")
            step += 1; nxt = f"[b{step}]"
            chain.append(f"{cur}[w{wi}]overlay=x=0:y='round(26*pow(1-min(max(t-{st:.2f}\\,0)/0.3\\,1)\\,2))':format=auto{nxt}"); cur = nxt
    if text_png:
        ti = add_input(text_png)
        chain.append(f"[{ti}:v]format=rgba,fade=t=in:st=0.25:d=0.7:alpha=1[tx]")
        step += 1; nxt = f"[b{step}]"
        chain.append(f"{cur}[tx]overlay=x=0:y='round(40*pow(1-min(t/0.85\\,1)\\,2))':format=auto{nxt}"); cur = nxt
    fade = min(0.4, dur / 4)
    chain.append(f"{cur}fade=t=in:st=0:d={fade}:color={FADE_COLOR},fade=t=out:st={dur - fade:.3f}:d={fade}:color={FADE_COLOR},format=yuv420p[v]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", "[v]", "-r", str(fps), "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(out)])
    return out


# ---- actions: which faceless actors appear and how they move (generic people/animals only) ------------------------
# instance = (sprite, x0 px, feet_y fraction of H, scale, speed px/s (+ right / - left), flip)
ACTIONS = {
    "none": [], "ship_drift": [],
    "army_march": [("elephant", 120, 0.915, 0.62, 26, False), ("elephant", 560, 0.93, 0.5, 26, False),
                   ("spearman", 40, 0.92, 0.5, 26, False), ("spearman", 330, 0.935, 0.46, 26, False), ("spearman", 470, 0.925, 0.52, 26, False),
                   ("spearman", 800, 0.94, 0.47, 26, False)],
    "flock": [("bird", -120 + 140 * i, 0.15 + 0.035 * (i % 4), 0.9 - 0.06 * (i % 3), 70 + 6 * (i % 4), False) for i in range(9)],
    "caravan": [("traveller", 90, 0.925, 0.56, 30, False), ("traveller", 260, 0.935, 0.5, 30, False), ("walker", 420, 0.93, 0.54, 30, False),
                ("traveller", 600, 0.94, 0.48, 30, False), ("walker", 790, 0.93, 0.52, 30, False)],
    "crowd_gather": [("walker", 150, 0.925, 0.52, 18, False), ("walker", 330, 0.935, 0.48, -18, True), ("walker", 520, 0.93, 0.55, 18, False),
                     ("traveller", 700, 0.94, 0.5, -18, True), ("walker", 880, 0.925, 0.47, 18, False)],
}
FORBIDDEN_ACTORS = {"prophet", "sahabi", "companion", "allah", "angel", "messenger"}      # never exist; enforced in tests/validation

def scene_clip_actors(assets: dict, tag: str, text_png: str, dur: float, fps: int, out: Path, stars: str | None,
                      action: str, cache: Path, hook_words=None, index=0) -> Path:
    """Same as scene_clip but with faceless actors composited between the scenery and the scrim."""
    if action in (None, "", "none"):
        return scene_clip(assets, tag, text_png, dur, fps, out, stars, hook_words, index)
    spec = assets.get(tag) or assets[DEFAULT_TAG]
    inputs = ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", spec["sky"]]
    chain, n, step = ["[0:v]format=rgba[b0]"], 1, 0
    cur = "[b0]"
    def inp(path, loopmov=False):
        nonlocal n
        if loopmov: inputs.extend(["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", path])
        else:       inputs.extend(["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", path])
        n += 1; return n - 1
    def ov(i, x="0", y="0"):
        nonlocal cur, step
        step += 1; nxt = f"[b{step}]"; chain.append(f"{cur}[{i}:v]overlay=x='{x}':y='{y}':format=auto{nxt}"); cur = nxt
    if spec["stars"] and stars:
        si = n; inputs.extend(["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", stars]); n += 1
        step += 1; nxt = f"[b{step}]"
        chain.append(f"{cur}format=gbrp[g];[{si}:v]format=gbrp[st];[g][st]blend=all_mode=screen:all_opacity=0.9,format=rgba{nxt}"); cur = nxt
    if spec["orb"]:
        kind, yb = spec["orb"]; oi = inp(assets[f"orb_{kind}"])
        ov(oi, x=f"{W * 0.70:.0f}+60*sin(2*PI*t/40)" if kind == "moon" else f"{W * 0.5 - 230:.0f}",
           y=f"{H * yb:.0f}-30*sin(2*PI*t/55)" if kind == "moon" else f"{H * yb - 230:.0f}-90*t/{max(dur, 1):.2f}")
    for k, (path, kind, speed) in enumerate(spec["layers"]):
        li = inp(path)
        if speed: ov(li, x=(f"-mod(t*{speed}\\,{P})" if (index + k) % 2 == 0 else f"mod(t*{speed}\\,{P})-{P}"))
        else: ov(li)
    for sprite, x0, fy, sc, v, flip in ACTIONS[action]:
        mov = AC.build_sprite(sprite, cache, fps); w, h = AC.SPRITES[sprite][1]
        i = inp(mov, loopmov=True)
        k_ = 1.7 if sprite == "bird" else 1.35
        tw, th = int(w * sc * k_), int(h * sc * k_)
        chain.append(f"[{i}:v]format=rgba,scale={tw}:{th}{',hflip' if flip else ''}[a{i}]")
        step += 1; nxt = f"[b{step}]"
        chain.append(f"{cur}[a{i}]overlay=x='{x0}+({v})*t':y='{int(H * fy) - th}':format=auto{nxt}"); cur = nxt
    ov(inp(assets["scrim"])); ov(inp(assets["frame"]))
    if hook_words:
        for wp, st in hook_words:
            wi = inp(wp)
            chain.append(f"[{wi}:v]format=rgba,fade=t=in:st={st:.2f}:d=0.22:alpha=1[w{wi}]")
            step += 1; nxt = f"[b{step}]"
            chain.append(f"{cur}[w{wi}]overlay=x=0:y='round(26*pow(1-min(max(t-{st:.2f}\\,0)/0.3\\,1)\\,2))':format=auto{nxt}"); cur = nxt
    if text_png:
        ti = inp(text_png)
        chain.append(f"[{ti}:v]format=rgba,fade=t=in:st=0.25:d=0.7:alpha=1[tx]")
        step += 1; nxt = f"[b{step}]"
        chain.append(f"{cur}[tx]overlay=x=0:y='round(40*pow(1-min(t/0.85\\,1)\\,2))':format=auto{nxt}"); cur = nxt
    fade = min(0.4, dur / 4)
    chain.append(f"{cur}fade=t=in:st=0:d={fade}:color={FADE_COLOR},fade=t=out:st={dur - fade:.3f}:d={fade}:color={FADE_COLOR},format=yuv420p[v]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", "[v]", "-r", str(fps), "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(out)])
    return out


def scene_clip_3d(assets: dict, bg_mp4: str, text_png: str | None, dur: float, fps: int, out: Path, hook_words=None) -> Path:
    """Composite a pre-rendered Blender shot with the same scrim / frame / kinetic hook / subtitle layers used by the 2.5D engine."""
    inputs = ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", bg_mp4]
    chain, n, step = [f"[0:v]scale={W}:{H}:flags=lanczos,fps={fps},format=rgba[b0]"], 1, 0
    cur = "[b0]"
    def inp(path):
        nonlocal n
        inputs.extend(["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", path]); n += 1; return n - 1
    def ov(i):
        nonlocal cur, step
        step += 1; nxt = f"[b{step}]"; chain.append(f"{cur}[{i}:v]overlay=x=0:y=0:format=auto{nxt}"); cur = nxt
    ov(inp(assets["scrim"])); ov(inp(assets["frame"]))
    for wp, st in (hook_words or []):
        wi = inp(wp)
        chain.append(f"[{wi}:v]format=rgba,fade=t=in:st={st:.2f}:d=0.22:alpha=1[w{wi}]")
        step += 1; nxt = f"[b{step}]"
        chain.append(f"{cur}[w{wi}]overlay=x=0:y='round(26*pow(1-min(max(t-{st:.2f}\\,0)/0.3\\,1)\\,2))':format=auto{nxt}"); cur = nxt
    if text_png:
        ti = inp(text_png)
        chain.append(f"[{ti}:v]format=rgba,fade=t=in:st=0.25:d=0.7:alpha=1[tx]")
        step += 1; nxt = f"[b{step}]"
        chain.append(f"{cur}[tx]overlay=x=0:y='round(40*pow(1-min(t/0.85\\,1)\\,2))':format=auto{nxt}"); cur = nxt
    fade = min(0.4, dur / 4)
    chain.append(f"{cur}fade=t=in:st=0:d={fade}:color={FADE_COLOR},fade=t=out:st={dur - fade:.3f}:d={fade}:color={FADE_COLOR},format=yuv420p[v]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", "[v]", "-r", str(fps), "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(out)])
    return out
