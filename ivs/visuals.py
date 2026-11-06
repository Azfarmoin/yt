"""Pillow scene generation: generated geometric backgrounds (no third-party assets => no license exposure),
RTL-correct text via libraqm, auto-fit with a readability floor, and a glyph-coverage check."""
from __future__ import annotations
import math, random
from dataclasses import dataclass, field
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFont, features
from .config import ROOT
from .textutil import for_display_ar

FONTS = ROOT / "assets" / "fonts"
W, H = 1080, 1920
MARGIN = 90
PALETTES = {
    "default": ("#0b1f2a", "#12394a", "#d9b36a", "#f4efe6"),
    "emerald": ("#071e1a", "#0f3b33", "#e0c070", "#f2efe3"),
    "midnight": ("#0a0f24", "#1a2250", "#d8b66e", "#eeeaf5"),
    "editorial": ("#0d0e10", "#1b1d22", "#cfcfcf", "#f5f5f2"),        # minimal editorial: neutral, no gold
    "classical": ("#071e1a", "#0f3b33", "#d9b36a", "#f2efe3"),         # classical Islamic: deep green + gold
    "luxury": ("#0b0907", "#1f1710", "#e8d3a2", "#f7f1e3"),            # luxury documentary: warm black + champagne
    "calligraphic": ("#0a1030", "#232d63", "#e2bf6e", "#f1eefa"),      # cinematic calligraphy: indigo + gold
    "educational": ("#0f2230", "#1d4a5e", "#9fd0d8", "#f2f7f8"),       # modern educational: slate + teal
}
# (font file, start size, min readable size, line spacing)
STYLE = {
    "ar": ("Amiri-Regular.ttf", 124, 60, 1.55),
    "ur": ("NotoNastaliqUrdu.ttf", 68, 44, 2.05),
    "en": ("NotoSans.ttf", 60, 40, 1.35),
    "label": ("NotoSans.ttf", 38, 30, 1.2),
}

class LayoutError(Exception):
    pass

def require_raqm():
    if not features.check("raqm"):
        raise RuntimeError("Pillow was built without libraqm: Arabic/Urdu shaping would be wrong. "
                           "On Windows install the official Pillow wheel (bundles raqm); on Linux `apt install libraqm0`.")

def font(kind: str, size: int):
    return ImageFont.truetype(str(FONTS / STYLE[kind][0]), size)

def _dir(kind): return "rtl" if kind in ("ar", "ur") else "ltr"
def _lang(kind): return {"ar": "ar", "ur": "ur", "en": "en"}.get(kind)

def text_width(txt, f, kind):
    return f.getlength(txt, direction=_dir(kind), language=_lang(kind))

def wrap(txt: str, f, kind: str, maxw: int) -> list[str]:
    words, lines, cur = txt.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if text_width(t, f, kind) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def fit(txt: str, kind: str, maxw: int, maxh: int):
    """Largest size (down to the readability floor) whose wrapped block fits. None => caller must split."""
    _, start, floor, ls = STYLE[kind]
    for size in range(start, floor - 1, -2):
        f = font(kind, size)
        lines = wrap(txt, f, kind, maxw)
        if any(text_width(l, f, kind) > maxw for l in lines):
            continue
        h = int(len(lines) * size * ls)
        if h <= maxh:
            return f, lines, size, h
    return None

def split_to_fit(txt: str, kind: str, maxw: int, maxh: int) -> list[str]:
    """Split into the fewest word-balanced chunks that each fit above the readability floor."""
    words = txt.split()
    for n in range(1, len(words) + 1):
        per = math.ceil(len(words) / n)
        chunks = [" ".join(words[i:i + per]) for i in range(0, len(words), per)]
        if all(fit(c, kind, maxw, maxh) for c in chunks):
            return chunks
    raise LayoutError(f"cannot fit text legibly: {txt[:40]}")

def background(palette="default", seed=1) -> Image.Image:
    c1, c2, gold, _ = PALETTES[palette]
    img = Image.new("RGB", (W, H), c1)
    px = ImageDraw.Draw(img)
    # vertical gradient
    a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5)); b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    for y in range(H):
        t = y / H
        px.line([(0, y), (W, y)], fill=tuple(int(a[k] + (b[k] - a[k]) * (1 - abs(2 * t - 1))) for k in range(3)))
    # eight-pointed star lattice (two overlapped squares), very low contrast
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    g = tuple(int(gold[i:i + 2], 16) for i in (1, 3, 5))
    step, r = 180, 70
    for cy in range(-step, H + step, step):
        for cx in range(-step, W + step, step):
            ox = (cx + (step // 2 if (cy // step) % 2 else 0))
            for rot in (0, 45):
                pts = [(ox + r * math.cos(math.radians(rot + 90 * k + 45)), cy + r * math.sin(math.radians(rot + 90 * k + 45))) for k in range(4)]
                d.polygon(pts, outline=g + (26,))
    img = Image.alpha_composite(img.convert("RGBA"), ov)
    # vignette-ish gold frame
    fr = ImageDraw.Draw(img)
    fr.rounded_rectangle([40, 40, W - 40, H - 40], radius=28, outline=g + (120,), width=3)
    fr.rounded_rectangle([54, 54, W - 54, H - 54], radius=22, outline=g + (60,), width=1)
    return img.convert("RGB")

@dataclass
class TextBox:
    kind: str; text: str; x0: int; y0: int; x1: int; y1: int

@dataclass
class Scene:
    path: str
    duration: float
    boxes: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

class TextLayer:
    """Straight-alpha text layer (RGB + L alpha) so FFmpeg can animate text independently of the background."""
    def __init__(self):
        self.rgb = Image.new("RGB", (W, H)); self.alpha = Image.new("L", (W, H), 0)

    def _commit(self, mask: Image.Image, color):
        bb = mask.getbbox()
        if not bb: return
        solid = mask.point(lambda v: 255 if v else 0)
        self.rgb.paste(tuple(color[:3]), mask=solid)
        self.alpha = ImageChops.lighter(self.alpha, mask)

    def text(self, xy, txt, f, color, kind):
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).text(xy, txt, font=f, fill=255, anchor="mm", direction=_dir(kind), language=_lang(kind))
        self._commit(m, color)

    def line(self, pts, color, width):
        m = Image.new("L", (W, H), 0); ImageDraw.Draw(m).line(pts, fill=255, width=width); self._commit(m, color)

    def rgba(self) -> Image.Image:
        return Image.merge("RGBA", (*self.rgb.split(), self.alpha))

_MEASURE = ImageDraw.Draw(Image.new("L", (1, 1)))

def draw_block(layer, y, txt, kind, color, maxh, boxes, maxw=W - 2 * MARGIN):
    """Draws centered text block at top y; returns new y. Raises LayoutError if it can't fit legibly."""
    shown = for_display_ar(txt) if kind == "ar" else txt
    fm = fit(shown, kind, maxw, maxh)
    if not fm:
        raise LayoutError(f"{kind} text does not fit in {maxw}x{maxh}: {txt[:30]}")
    f, lines, size, h = fm
    ls = STYLE[kind][3]
    for i, line in enumerate(lines):
        cy = y + int((i + 0.5) * size * ls)
        layer.text((W // 2, cy), line, f, color, kind)
        bb = _MEASURE.textbbox((W // 2, cy), line, font=f, anchor="mm", direction=_dir(kind), language=_lang(kind))
        boxes.append(TextBox(kind, line, *bb))
    return y + h

def check_boxes(boxes) -> list[str]:
    bad = []
    for b in boxes:
        if b.x0 < MARGIN // 2 or b.x1 > W - MARGIN // 2 or b.y0 < 60 or b.y1 > H - 60:
            bad.append(f"{b.kind} line out of safe area: {b.text[:20]} ({b.x0},{b.y0},{b.x1},{b.y1})")
    return bad

def glyph_coverage(text: str, kind: str) -> list[str]:
    """Return characters the font renders as .notdef (compares each glyph's mask to a guaranteed-missing codepoint)."""
    f = font(kind, 80)
    def mask(ch):
        m = f.getmask(ch, direction=_dir(kind), language=_lang(kind))
        return (m.size, bytes(m))
    missing_ref = mask("\U0010FFFE")
    out = []
    for ch in sorted(set(text)):
        if ch.isspace() or ch in "\u200f\u200e\u200c\u200d":
            continue
        if mask(ch) == missing_ref:
            out.append(f"U+{ord(ch):04X}")
    return out

def _tint(hexc): return tuple(int(hexc[i:i + 2], 16) for i in (1, 3, 5))

_BG_CACHE: dict = {}

def render_scene(out: Path, kind: str, palette: str, duration: float, *, watermark="", footer="",
                 title="", ar="", ur="", en="", label="", extra_lines=()) -> Scene:
    """Writes <out> (flattened 1080x1920 PNG), <out>_bg.png and <out>_text.png (RGBA) so effects can animate layers."""
    require_raqm()
    c1, c2, gold, ink = PALETTES[palette]
    gold_c, ink_c = _tint(gold), _tint(ink)

    def layout(layer, y, boxes):
        if label:
            y = draw_block(layer, y, label, "label", gold_c, 140, boxes) + 30
        if title:
            y = draw_block(layer, y, title, "en", ink_c, 520, boxes) + 40
        if ar:
            y = draw_block(layer, y + 20, ar, "ar", ink_c, 640, boxes) + 50
        if ar and (ur or en):
            layer.line([(W // 2 - 90, y), (W // 2 + 90, y)], gold_c, 3)
        y += 50
        if ur:
            y = draw_block(layer, y, ur, "ur", (255, 224, 150), 560, boxes) + 20
        if en:
            y = draw_block(layer, y, en, "en", ink_c, 560, boxes) + 20
        for ln in extra_lines:
            y = draw_block(layer, y, ln, "label", gold_c, 200, boxes) + 10
        return y

    start = 190                               # dry run to measure, then draw vertically centred
    end = layout(TextLayer(), start, [])
    top = max(150, int((H - 260 - (end - start)) / 2) + 40)
    layer, boxes = TextLayer(), []
    layout(layer, top, boxes)
    if footer:
        draw_block(layer, H - 260, footer, "label", gold_c, 160, boxes)
    if watermark:
        layer.text((W // 2, H - 105), watermark, font("label", 32), gold_c, "en")
    problems = check_boxes(boxes)
    if problems:
        raise LayoutError("; ".join(problems))
    key = (palette,)
    if key not in _BG_CACHE:
        _BG_CACHE[key] = background(palette)
    bg = _BG_CACHE[key]
    out = Path(out)
    tl = layer.rgba()
    flat = Image.alpha_composite(bg.convert("RGBA"), tl).convert("RGB")
    flat.save(out, "PNG")
    bgp, txp = out.with_name(out.stem + "_bg.png"), out.with_name(out.stem + "_text.png")
    bg.save(bgp, "PNG"); tl.save(txp, "PNG")
    return Scene(str(out), duration, boxes, {"kind": kind, "bg": str(bgp), "text": str(txp)})
