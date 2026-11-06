"""Duplicate detection: exact fingerprints, ayah-level overlap, and a free local semantic-ish similarity
(character n-gram TF vectors + cosine; pure Python, no model download, no API)."""
from __future__ import annotations
import math, re
from collections import Counter
from .textutil import normalize_text, fingerprint

def ngrams(s: str, n: int = 3) -> Counter:
    s = f" {normalize_text(s)} "
    return Counter(s[i:i + n] for i in range(max(1, len(s) - n + 1)))

def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values())); nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0

def similarity(a: str, b: str) -> float:
    return cosine(ngrams(a), ngrams(b))

class DuplicateCheck:
    def __init__(self, db, threshold: float = 0.82):
        self.db, self.threshold = db, threshold

    def check(self, key: str, text: str, ayat: list[tuple[int, int]] | None = None, allow_series: bool = False):
        """Return (ok, reason). Rejects anything already in history unless an admin approved a series."""
        c = self.db.conn
        if c.execute("SELECT 1 FROM content_items WHERE key=?", (key,)).fetchone():
            return False, f"key already used: {key}"
        fp = fingerprint(text)
        if c.execute("SELECT key FROM content_items WHERE text_fingerprint=?", (fp,)).fetchone():
            return False, "identical normalized text already used"
        if ayat:
            for s, a in ayat:
                r = c.execute("SELECT item_id FROM used_ayat WHERE surah=? AND ayah=?", (s, a)).fetchone()
                if r:
                    return False, f"ayah {s}:{a} already used by item {r[0]}"
        if not allow_series:
            cand = ngrams(text)
            for row in c.execute("SELECT key, script_text FROM content_items WHERE script_text IS NOT NULL"):
                sim = cosine(cand, ngrams(row["script_text"]))
                if sim >= self.threshold:
                    return False, f"near-duplicate of {row['key']} (similarity {sim:.2f})"
        return True, "ok"
