"""Hadith provider/verifier. Text from fawazahmed0/hadith-api (GitHub raw), cached locally.
Policy: every hadith item ends in `needs_review` — automated checks cannot establish authenticity."""
from __future__ import annotations
import json, datetime as dt
from pathlib import Path
import requests
import re
from .textutil import strip_arabic_marks

BASE = "https://raw.githubusercontent.com/fawazahmed0/hadith-api/1/editions"
COLLECTION_NAMES = {"bukhari": "Sahih al-Bukhari", "muslim": "Sahih Muslim"}
GRADING_NOTE = {
    "bukhari": "Collection-level: Sahih al-Bukhari is the most authentic hadith collection by scholarly consensus. "
               "No narration-specific grading is attached by the data source; human review required.",
    "muslim": "Collection-level: Sahih Muslim is among the most authentic collections by scholarly consensus. "
              "No narration-specific grading is attached by the data source; human review required.",
}

class HadithError(Exception):
    pass

class Hadith:
    def __init__(self, cache_dir: Path, session=None):
        self.cache = Path(cache_dir) / "hadith"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.http = session or requests

    def fetch(self, lang: str, collection: str, number: int) -> dict:
        ed = f"{lang}-{collection}"
        p = self.cache / f"{ed}_{number}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        r = self.http.get(f"{BASE}/{ed}/{number}.json", timeout=30)
        if r.status_code != 200:
            raise HadithError(f"{ed}/{number}: HTTP {r.status_code}")
        p.write_text(r.text, encoding="utf-8")
        return r.json()

    @staticmethod
    def _slice(text: str, start: str, end: str) -> str | None:
        i = text.find(start)
        if i < 0:
            return None
        j = text.find(end, i)
        if j < 0:
            return None
        return text[i:j + len(end)].strip()

    @staticmethod
    def _slice_ar(text: str, start: str, end: str) -> str | None:
        """Marker search that ignores diacritics/format chars, returning the ORIGINAL (diacritized) slice."""
        keep, idx = [], []
        for i, ch in enumerate(text):
            if strip_arabic_marks(ch) and not re.match(r"[\u200b-\u200f\u202a-\u202e]", ch):
                keep.append(strip_arabic_marks(ch).replace("آ", "آ")); idx.append(i)
        flat = "".join(keep)
        norm = lambda m: "".join(c for c in strip_arabic_marks(m) if not re.match(r"[\u200b-\u200f\u202a-\u202e]", c))
        a, b = norm(start), norm(end)
        i = flat.find(a)
        if i < 0:
            return None
        j = flat.find(b, i)
        if j < 0:
            return None
        k = idx[j + len(b) - 1] + 1
        while k < len(text) and re.match(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]", text[k]):
            k += 1                                  # keep marks attached to the final letter
        return text[idx[i]:k].strip()

    def build(self, entry: dict) -> dict:
        """Return {'ok', 'problems', 'ar','ur','en', 'source'} for a catalog entry."""
        problems: list[str] = []
        col, num = entry["collection"], entry["number"]
        out: dict = {"ok": False, "problems": problems}
        try:
            docs = {l: self.fetch(l, col, num) for l in ("ara", "eng", "urd")}
        except Exception as e:                                   # network / missing
            problems.append(f"fetch failed: {e}")
            return out
        h = {l: d["hadiths"][0] for l, d in docs.items()}
        for l, x in h.items():
            if x["hadithnumber"] != num:
                problems.append(f"{l}: hadith number mismatch ({x['hadithnumber']} != {num})")
        ref = h["ara"].get("reference", {})
        if f"Book {ref.get('book')}, Hadith {ref.get('hadith')}" != entry["book_ref"]:
            problems.append(f"book reference mismatch: source says {ref}, catalog says {entry['book_ref']}")
        if entry["expect_en"].lower() not in h["eng"]["text"].lower():
            problems.append("English text does not contain the expected keyword (wrong number?)")
        ar = self._slice_ar(h["ara"]["text"], entry["ar_start"], entry["ar_end"])
        en = self._slice(h["eng"]["text"], entry["en_start"], entry["en_end"])
        ur = self._slice(h["urd"]["text"], entry["ur_start"], entry["ur_end"])
        for lang, v in (("Arabic", ar), ("English", en), ("Urdu", ur)):
            if not v:
                problems.append(f"{lang} matn markers not found in source text")
        grades = h["ara"].get("grades") or []
        out.update(ar=ar, en=en, ur=ur, ok=not problems, grades=grades,
                   source={"collection": COLLECTION_NAMES.get(col, col), "number": num, "book_ref": entry["book_ref"],
                           "grading": ("; ".join(f"{g.get('grade')} ({g.get('name')})" for g in grades)
                                       if grades else GRADING_NOTE.get(col, "ungraded")),
                           "text_source": f"{BASE}/ara-{col}/{num}.json", "verified_on": dt.date.today().isoformat(),
                           "translations": {"en": "Muhsin Khan (eng-%s)" % col, "ur": "urd-%s (Urdu edition of the data source)" % col}})
        return out
