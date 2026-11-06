"""Restrained visual effects, all generated locally (no stock footage, no licenses):
  * slow Ken-Burns zoom/drift on the background layer
  * drifting, twinkling gold dust (seamless looping particle clip, screen-blended)
  * text reveal: fade-in + short upward ease, independent of the background
Text stays pixel-sharp (it is never scaled)."""
from __future__ import annotations
import subprocess
from pathlib import Path
import numpy as np
from .visuals import W, H, PALETTES
from .audio import run

LOOP_SECONDS = 8

FADE_COLOR = "black"

def _sprite(r: int) -> np.ndarray:
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return np.exp(-(x * x + y * y) / (2 * (r / 2.2) ** 2)).astype(np.float32)

def make_particles(path: Path, palette: str = "default", fps: int = 24, n: int = 70, seed: int = 7) -> Path:
    """8-second seamless loop (all motion is periodic with the loop length)."""
    path = Path(path)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    gold = np.array([int(PALETTES[palette][2][i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
    x0 = rng.uniform(60, W - 60, n); y0 = rng.uniform(60, H - 60, n)
    ax = rng.uniform(10, 38, n); ay = rng.uniform(18, 60, n)
    ph = rng.uniform(0, 2 * np.pi, (n, 3)); rad = rng.integers(3, 9, n)
    sprites = {int(r): _sprite(int(r)) for r in set(rad)}
    frames = LOOP_SECONDS * fps
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", str(path)]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for f in range(frames):
        t = 2 * np.pi * f / frames
        canvas = np.zeros((H, W, 3), np.float32)
        for i in range(n):
            x = int(x0[i] + ax[i] * np.sin(t + ph[i, 0])); y = int(y0[i] + ay[i] * np.sin(2 * t + ph[i, 1]))
            a = 0.25 + 0.75 * (0.5 + 0.5 * np.sin(3 * t + ph[i, 2]))          # twinkle (integer harmonic => loops)
            r = int(rad[i]); sp = sprites[r]
            ys, xs = slice(max(0, y - r), min(H, y + r + 1)), slice(max(0, x - r), min(W, x + r + 1))
            sub = sp[(ys.start - (y - r)):(ys.stop - (y - r)), (xs.start - (x - r)):(xs.stop - (x - r))]
            canvas[ys, xs] += sub[..., None] * gold * a * 0.8
        pr.stdin.write((np.clip(canvas, 0, 1) * 255).astype(np.uint8).tobytes())
    pr.stdin.close(); err = pr.stderr.read(); pr.wait()
    if pr.returncode != 0:
        raise RuntimeError(err.decode()[-400:])
    return path

def scene_clip(bg: str, text: str, particles: str | None, dur: float, fps: int, out: Path, index: int = 0,
               kenburns=True, reveal=True) -> Path:
    """One animated clip. Zoom direction alternates per scene so consecutive scenes don't feel identical."""
    n = max(1, int(round(dur * fps)))
    zin = (index % 2 == 0)
    z = f"1+0.05*on/{n}" if zin else f"1.05-0.05*on/{n}"
    drift = 14 if index % 3 else -14
    inputs = ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", bg,
              "-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", text]
    if particles:
        inputs += ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", particles]
    fade = min(0.35, dur / 4)
    if kenburns:
        bgf = (f"[0:v]scale=2160:3840,zoompan=z='{z}':x='iw/2-(iw/zoom/2)+({drift}*on/{n})':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps},"
               f"format=gbrp[bgz]")
    else:
        bgf = f"[0:v]format=gbrp[bgz]"
    if particles:
        mix = "[2:v]format=gbrp[pt];[bgz][pt]blend=all_mode=screen:all_opacity=0.85[bp]"
    else:
        mix = "[bgz]null[bp]"
    if reveal:
        txf = "[1:v]format=rgba,fade=t=in:st=0.15:d=0.7:alpha=1[tx]"
        pos = "y='round(46*pow(1-min(t/0.85\\,1)\\,2))'"
    else:
        txf = "[1:v]format=rgba[tx]"; pos = "y=0"
    fc = (f"{bgf};{mix};{txf};[bp][tx]overlay=x=0:{pos}:format=auto,"
          f"fade=t=in:st=0:d={fade}:color={FADE_COLOR},fade=t=out:st={dur - fade:.3f}:d={fade}:color={FADE_COLOR},format=yuv420p[v]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[v]", "-r", str(fps), "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(out)])
    return out
