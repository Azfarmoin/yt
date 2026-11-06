"""Quran text provider + verifier.

Provenance: Arabic = Quran Complex 'Uthmani Hafs' v13 (via fawazahmed0/quran-api, redistributed Tanzil-style data),
Urdu = Fateh Muhammad Jalandhry, English = Abdullah Yusuf Ali. Files are pinned by SHA-256 in assets/data/MANIFEST.json.
"""
from __future__ import annotations
import json, datetime as dt
from pathlib import Path
from .config import ROOT
from .textutil import sha256_file, cross_key, BASMALA_KEY
from .dedupe import similarity

DATA = ROOT / "assets" / "data"
TOTAL_AYAT = 6236
CROSSCHECK_MIN = 0.70   # corpus-wide minimum observed agreement between the two editions is 0.73; shifted/corrupted verses score far lower
SURAH_NAMES = {106: "Quraysh", 105: "Al-Fil", 21: "Al-Anbiya", 37: "As-Saffat", 18: "Al-Kahf", 71: "Nuh", 105: "Al-Fil",  # English transliterations for display (subset is fine; fallback = "Surah N")
    1: "Al-Fatihah", 2: "Al-Baqarah", 3: "Ali 'Imran", 13: "Ar-Ra'd", 14: "Ibrahim", 29: "Al-'Ankabut", 39: "Az-Zumar",
    49: "Al-Hujurat", 55: "Ar-Rahman", 65: "At-Talaq", 93: "Ad-Duha", 94: "Ash-Sharh", 103: "Al-'Asr", 112: "Al-Ikhlas",
    20: "Ta-Ha", 16: "An-Nahl", 17: "Al-Isra", 25: "Al-Furqan", 31: "Luqman", 59: "Al-Hashr", 64: "At-Taghabun",
    9: "At-Tawbah", 8: "Al-Anfal", 57: "Al-Hadid", 24: "An-Nur", 23: "Al-Mu'minun", 7: "Al-A'raf", 11: "Hud", 12: "Yusuf",
}

class QuranError(Exception):
    pass

class Quran:
    def __init__(self, cfg: dict | None = None, data_dir: Path | None = None):
        q = (cfg or {}).get("quran", {})
        self.dir = Path(data_dir) if data_dir else DATA
        self.ed = {
            "ar": q.get("arabic_edition", "ara-quranuthmanihaf"),
            "ar_check": q.get("crosscheck_edition", "ara-quransimple"),
            "ur": q.get("urdu_edition", "urd-fatehmuhammadja"),
            "en": q.get("english_edition", "eng-abdullahyusufal"),
        }
        self.manifest = json.loads((self.dir / "MANIFEST.json").read_text(encoding="utf-8"))
        self.text: dict[str, dict[tuple[int, int], str]] = {}
        self.checksum_ok: dict[str, bool] = {}
        for lang, name in self.ed.items():
            self._load(lang, name)

    def _load(self, lang: str, name: str) -> None:
        p = self.dir / f"{name}.json"
        want = self.manifest["editions"].get(name, {}).get("sha256")
        got = sha256_file(p)
        self.checksum_ok[lang] = (want == got)
        d = json.loads(p.read_text(encoding="utf-8"))["quran"]
        self.text[lang] = {(e["chapter"], e["verse"]): e["text"] for e in d}

    # ---- access
    def ayah(self, lang: str, s: int, a: int) -> str:
        try:
            return self.text[lang][(s, a)]
        except KeyError:
            raise QuranError(f"No {lang} text for {s}:{a}")

    def verse_count(self, s: int) -> int:
        return sum(1 for (c, _) in self.text["ar"] if c == s)

    def range_text(self, lang: str, s: int, a1: int, a2: int) -> list[str]:
        return [self.ayah(lang, s, a) for a in range(a1, a2 + 1)]

    # ---- verification (returns a report; raises nothing)
    def verify(self, s: int, a1: int, a2: int) -> dict:
        problems: list[str] = []
        if not all(self.checksum_ok.values()):
            problems.append("data file checksum differs from pinned manifest: " +
                            ", ".join(k for k, v in self.checksum_ok.items() if not v))
        for lang, tbl in self.text.items():
            if len(tbl) != TOTAL_AYAT:
                problems.append(f"{lang}: expected {TOTAL_AYAT} ayat, found {len(tbl)}")
        n = self.verse_count(s)
        if not (1 <= s <= 114) or n == 0:
            problems.append(f"invalid surah {s}")
        elif not (1 <= a1 <= a2 <= n):
            problems.append(f"ayah range {a1}-{a2} outside surah {s} (1..{n})")
        if not problems:
            for a in range(a1, a2 + 1):
                ar = self.ayah("ar", s, a)
                if not ar.strip():
                    problems.append(f"{s}:{a} empty Arabic text")
                    continue
                for lang in ("ur", "en"):
                    if not self.ayah(lang, s, a).strip():
                        problems.append(f"{s}:{a} missing {lang} translation")
                # independent cross-check against a second Arabic edition (skeleton similarity)
                other = cross_key(self.ayah("ar_check", s, a))
                if a == 1 and s not in (1, 9) and other.startswith(BASMALA_KEY):
                    other = other[len(BASMALA_KEY):]      # the Tanzil 'simple' edition prepends the basmala to ayah 1
                sim = similarity(cross_key(ar), other)
                if sim < CROSSCHECK_MIN:
                    problems.append(f"{s}:{a} Arabic editions disagree (similarity {sim:.2f})")
        return {
            "ok": not problems, "problems": problems,
            "verified_on": dt.date.today().isoformat(),
            "editions": {k: self.manifest["editions"].get(v, {}) | {"name": v} for k, v in self.ed.items()},
        }

def build_manifest(data_dir: Path = DATA) -> dict:
    """Run once after (re)downloading data to pin checksums."""
    meta = {
        "ara-quranuthmanihaf": ("Quran Uthmani Hafs v13, King Fahd Quran Complex", "https://qurancomplex.gov.sa/"),
        "ara-quransimple": ("Quran Simple (Tanzil)", "https://tanzil.net/"),
        "urd-fatehmuhammadja": ("Urdu: Fateh Muhammad Jalandhry (Tanzil)", "https://tanzil.net/"),
        "eng-abdullahyusufal": ("English: Abdullah Yusuf Ali (Tanzil)", "https://tanzil.net/"),
    }
    man = {"mirror": "https://github.com/fawazahmed0/quran-api", "editions": {}}
    for name, (desc, src) in meta.items():
        man["editions"][name] = {"description": desc, "origin": src, "sha256": sha256_file(data_dir / f"{name}.json")}
    (data_dir / "MANIFEST.json").write_text(json.dumps(man, indent=2), encoding="utf-8")
    return man
