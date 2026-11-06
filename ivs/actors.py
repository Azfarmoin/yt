"""Faceless silhouette actors (generated with Pillow, animated as looping alpha clips). Pure dark shapes: no faces, no
features, no clothing detail. SAFETY RULE: only generic crowds/soldiers/travellers/animals exist here. Prophets, the
Companions, Allah and other sacred figures are never drawn (anim.ACTIONS has no such actor, and tests enforce it)."""
from __future__ import annotations
import math, subprocess
from pathlib import Path
from PIL import Image, ImageDraw

INK = (6, 8, 18, 255)
SS = 3                                   # supersampling

def _canvas(w, h): return Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
def _fin(img, w, h): return img.resize((w, h), Image.LANCZOS)

def walker(ph: float, spear=False, staff=False, w=120, h=220) -> Image.Image:
    im = _canvas(w, h); d = ImageDraw.Draw(im); s = SS
    cx, hip, sh = 60 * s, 118 * s, 62 * s
    sw = math.sin(2 * math.pi * ph); bob = abs(math.sin(2 * math.pi * ph)) * 3 * s
    def limb(x0, y0, ang, length, width):
        x1, y1 = x0 + length * math.sin(ang), y0 + length * math.cos(ang)
        d.line([(x0, y0), (x1, y1)], fill=INK, width=int(width * s)); d.ellipse([x1 - width * s / 2, y1 - width * s / 2, x1 + width * s / 2, y1 + width * s / 2], fill=INK)
    for side in (1, -1):                                   # legs
        limb(cx, hip - bob, side * sw * 0.55, 92 * s, 15)
    d.polygon([(cx - 20 * s, sh - bob), (cx + 20 * s, sh - bob), (cx + 14 * s, hip - bob), (cx - 14 * s, hip - bob)], fill=INK)   # torso
    d.ellipse([cx - 14 * s, sh - 36 * s - bob, cx + 14 * s, sh - 8 * s - bob], fill=INK)                                          # head (blank)
    d.rectangle([cx - 5 * s, sh - 12 * s - bob, cx + 5 * s, sh - bob], fill=INK)
    limb(cx, sh + 6 * s - bob, -sw * 0.5, 62 * s, 12)       # arms
    if spear or staff:
        top = 8 * s if spear else 40 * s
        x = cx + 30 * s; d.line([(x, top), (x - 4 * s, 205 * s)], fill=INK, width=int(5 * s))
        if spear: d.polygon([(x - 6 * s, top + 10 * s), (x + 6 * s, top + 10 * s), (x, top - 12 * s)], fill=INK)
        limb(cx, sh + 6 * s - bob, 0.25, 55 * s, 12)
    else:
        limb(cx, sh + 6 * s - bob, sw * 0.5, 62 * s, 12)
    return _fin(im, w, h)

def elephant(ph: float, w=360, h=300) -> Image.Image:
    im = _canvas(w, h); d = ImageDraw.Draw(im); s = SS
    sw = math.sin(2 * math.pi * ph); bob = abs(sw) * 4 * s
    for k, off in enumerate((0, 0.5, 0.25, 0.75)):         # four legs, staggered
        a = math.sin(2 * math.pi * (ph + off)) * 0.35; x0 = (110 + 38 * k + (0 if k < 2 else 50)) * s - (20 * s if k < 2 else 0)
        y0 = 180 * s - bob; x1, y1 = x0 + 60 * s * math.sin(a), y0 + 100 * s * math.cos(a)
        d.line([(x0, y0), (x1, y1)], fill=INK, width=int(30 * s)); d.ellipse([x1 - 15 * s, y1 - 12 * s, x1 + 15 * s, y1 + 12 * s], fill=INK)
    d.ellipse([70 * s, 80 * s - bob, 300 * s, 210 * s - bob], fill=INK)                         # body
    d.ellipse([255 * s, 70 * s - bob, 345 * s, 160 * s - bob], fill=INK)                        # head
    tr = [((335 + 9 * i) * s, (125 + 24 * i) * s - bob + 8 * s * math.sin(2 * math.pi * ph + i * .7)) for i in range(0, 6)]
    d.line(tr, fill=INK, width=int(24 * s), joint="curve")                        # trunk
    d.ellipse([228 * s, 62 * s - bob, 285 * s, 135 * s - bob], fill=INK)                        # ear
    d.polygon([(76 * s, 130 * s - bob), (50 * s, 190 * s - bob), (84 * s, 170 * s - bob)], fill=INK)   # tail
    d.rounded_rectangle([130 * s, 52 * s - bob, 245 * s, 86 * s - bob], radius=10 * s, fill=INK)         # howdah/saddle block (abstract)
    return _fin(im, w, h)

def bird(ph: float, w=90, h=60) -> Image.Image:
    im = _canvas(w, h); d = ImageDraw.Draw(im); s = SS
    f = math.sin(2 * math.pi * ph); cx, cy = 45 * s, 32 * s
    d.ellipse([cx - 12 * s, cy - 5 * s, cx + 12 * s, cy + 5 * s], fill=INK)
    d.polygon([(cx + 10 * s, cy - 3 * s), (cx + 24 * s, cy), (cx + 10 * s, cy + 3 * s)], fill=INK)
    for side in (-1, 1):
        tip = (cx + side * 40 * s, cy - 24 * s * f)
        d.polygon([(cx + side * 4 * s, cy - 3 * s), tip, (cx + side * 14 * s, cy + 4 * s - 6 * s * f)], fill=INK)
    return _fin(im, w, h)

def ship(w=380, h=300) -> Image.Image:
    """Empty boat: hull + mast + sail. No crew."""
    im = _canvas(w, h); d = ImageDraw.Draw(im); s = SS
    d.polygon([(30 * s, 190 * s), (350 * s, 190 * s), (310 * s, 250 * s), (80 * s, 250 * s)], fill=INK)
    d.line([(190 * s, 190 * s), (190 * s, 25 * s)], fill=INK, width=int(7 * s))
    d.polygon([(198 * s, 35 * s), (198 * s, 175 * s), (310 * s, 175 * s)], fill=INK)
    d.polygon([(182 * s, 55 * s), (182 * s, 175 * s), (110 * s, 175 * s)], fill=INK)
    return _fin(im, w, h)

SPRITES = {  # name -> (frame function, size, frames per cycle)
    "walker": (lambda p: walker(p), (120, 220), 24),
    "spearman": (lambda p: walker(p, spear=True), (120, 220), 24),
    "traveller": (lambda p: walker(p, staff=True), (120, 220), 24),
    "elephant": (elephant, (360, 300), 36),
    "bird": (bird, (90, 60), 12),
}

def build_sprite(name: str, cache: Path, fps: int = 24) -> str:
    """Looping alpha clip (QuickTime RLE ARGB). Cycle length is the frame count / fps."""
    out = Path(cache) / "actors" / f"{name}.mov"
    if out.exists(): return str(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fn, (w, h), n = SPRITES[name]
    pr = subprocess.Popen(["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                           "-c:v", "qtrle", "-pix_fmt", "argb", str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for i in range(n): pr.stdin.write(fn(i / n).tobytes())
    pr.stdin.close(); err = pr.stderr.read(); pr.wait()
    if pr.returncode: raise RuntimeError(err.decode()[-300:])
    return str(out)

def build_ship(cache: Path) -> str:
    p = Path(cache) / "actors" / "ship.png"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True); ship().save(p)
    return str(p)
