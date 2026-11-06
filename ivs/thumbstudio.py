"""Thumbnail studio: builds several concepts from real frames of the finished film, scores them (legibility, subject clarity, composition)
and keeps the best. Wording is the verified source title only: no invented quotes, no clickbait."""
from __future__ import annotations
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from . import visuals as V

def _frame(video: str, t: float, out: Path) -> Image.Image:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", f"scale={V.W}:{V.H}", str(out)], check=True)
    return Image.open(out).convert("RGB")

def _concept(img: Image.Image, title: str, theme: str, layout: str, palette: str) -> Image.Image:
    c1, c2, gold, ink = V.PALETTES[palette]; im = img.convert("RGBA"); W, H = im.size
    cy = {"center": 0.47, "lower": 0.70, "upper": 0.26}[layout]
    band = Image.new("RGBA", im.size, (0, 0, 0, 0)); bd = ImageDraw.Draw(band)
    for y in range(int(H * (cy - 0.22)), int(H * (cy + 0.22))):
        a = int(185 * max(0.0, 1 - abs((y - H * cy) / (H * 0.22)) ** 2)); bd.line([(0, y), (W, y)], fill=(3, 5, 12, a))
    im = Image.alpha_composite(im, band); tl = V.TextLayer(); f = V.font("en", 124); lines = V.wrap(title, f, "en", W - 200)
    y0 = int(H * cy) - len(lines) * 80
    for i, ln in enumerate(lines): tl.text((W // 2, y0 + i * 165), ln, f, V._tint(ink) if hasattr(V, "_tint") else (255, 244, 220), "en")
    tl.text((W // 2, y0 + len(lines) * 165 + 40), theme.upper(), V.font("label", 46), V._tint(gold) if hasattr(V, "_tint") else (217, 179, 106), "en")
    return Image.alpha_composite(im, tl.rgba()).convert("RGB")

def score(img: Image.Image, layout: str) -> dict:
    g = np.asarray(img.convert("L").resize((108, 192)), np.float32) / 255.0
    cy = {"center": 0.47, "lower": 0.70, "upper": 0.26}[layout]; a, b = int(192 * (cy - 0.1)), int(192 * (cy + 0.1))
    text_band = g[a:b]; rest = np.concatenate([g[: max(a - 5, 0)], g[min(b + 5, 192):]]) if a > 5 else g[min(b + 5, 192):]
    legib = float(np.clip(text_band.max() - np.median(text_band), 0, 1))           # bright text against a dark band
    gy, gx = np.gradient(rest) if rest.size else (np.zeros(1), np.zeros(1)); clarity = float(np.clip(np.hypot(gx, gy).mean() * 12, 0, 1))
    balance = float(1 - abs(rest.mean() - 0.38) / 0.38) if rest.size else 0.0
    return {"legibility": round(legib, 3), "subject_clarity": round(clarity, 3), "balance": round(max(balance, 0), 3), "total": round(0.5 * legib + 0.3 * clarity + 0.2 * max(balance, 0), 3)}

def make(video: str, out_dir: Path, title: str, theme: str, palette: str, duration: float, hook_end: float = 3.0) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True); cands = []
    times = [min(hook_end * 0.6, duration * 0.1) + 0.4, duration * 0.35, duration * 0.62]; layouts = ["center", "lower", "upper"]
    for k, (t, lay) in enumerate(zip(times, layouts)):
        img = _concept(_frame(video, t, out_dir / f"raw{k}.png"), title, theme, lay, palette)
        p = out_dir / f"thumb_concept{k + 1}.jpg"; img.save(p, quality=90); cands.append({"file": str(p), "t": round(t, 1), "layout": lay, **score(img, lay)})
    best = max(cands, key=lambda c: c["total"])
    return {"chosen": best["file"], "candidates": cands}
