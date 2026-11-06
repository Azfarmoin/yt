from __future__ import annotations
import re, unicodedata, hashlib

# The Quran Complex Uthmani text uses U+08F0..08F2 for open tanween. Common fonts lack these glyphs,
# so they are mapped to the standard tanween code points at DISPLAY time only. Stored/verified text is untouched.
DISPLAY_MAP = {0x08F0: 0x064B, 0x08F1: 0x064C, 0x08F2: 0x064D}

def for_display_ar(text: str) -> str:
    return text.translate(DISPLAY_MAP)

_AR_MARKS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ࣓-ࣿـ]")
_AR_VARIANTS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ی": "ي", "ؤ": "و", "ئ": "ي", "ة": "ه", "ک": "ك"})

def strip_arabic_marks(s: str) -> str:
    return _AR_MARKS.sub("", s)

def skeleton_ar(s: str) -> str:
    """Rasm-level skeleton for cross-checking two Arabic editions (marks removed, letter variants folded)."""
    s = unicodedata.normalize("NFKD", s)
    s = strip_arabic_marks(s).translate(_AR_VARIANTS)
    s = re.sub(r"[^ء-ي ]", "", s)
    return re.sub(r"\s+", " ", s).strip()

def normalize_text(s: str) -> str:
    s = skeleton_ar(s) if re.search(r"[؀-ۿ]", s) else s
    s = s.lower()
    s = re.sub(r"[^\w\s؀-ۿ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def fingerprint(s: str) -> str:
    return hashlib.sha256(normalize_text(s).encode("utf-8")).hexdigest()

def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cross_key(s: str) -> str:
    """Spelling-tolerant key for comparing two Arabic Quran editions: skeleton minus spaces, alefs, hamza and ya
    (editions differ on dagger-alef vs written alef, e.g. والصفت / والصافات)."""
    return re.sub("[اءيى]", "", skeleton_ar(s).replace(" ", ""))

BASMALA_KEY = cross_key("بسم الله الرحمن الرحيم")
