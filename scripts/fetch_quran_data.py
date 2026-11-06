"""Download the four Quran editions the engine pins, validate them, and verify against assets/data/MANIFEST.json.

usage: python scripts/fetch_quran_data.py [--base-url URL] [--force]

Trust model (read this):
  * If assets/data/MANIFEST.json exists (committed to your repo), every downloaded file MUST match its SHA-256.
    A mismatch deletes the file and exits 1 - nothing unverified is ever used.
  * If no manifest exists (first run ever), the script validates structure (6,236 ayat, 114 surahs, consecutive
    numbering, no empty text) and then WRITES a manifest from what it downloaded. That is trust-on-first-use:
    review the printed hashes, run `python -m ivs verify-data` (cross-checks two Arabic editions), compare a few
    verses with a printed mushaf, and COMMIT assets/data/ so CI is pinned from then on.
Only the standard library is used (no network library needed beyond urllib).
"""
from __future__ import annotations
import argparse, hashlib, json, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "assets" / "data"
EDITIONS = ["ara-quranuthmanihaf", "ara-quransimple", "urd-fatehmuhammadja", "eng-abdullahyusufal"]
BASES = [
    "https://cdn.jsdelivr.net/gh/fawazahmed0/quran-api@1/editions",
    "https://raw.githubusercontent.com/fawazahmed0/quran-api/1/editions",
]
TOTAL_AYAT = 6236


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def validate_structure(raw: bytes, name: str) -> list[str]:
    """Returns a list of problems (empty = structurally sound)."""
    try:
        rows = json.loads(raw.decode("utf-8"))["quran"]
    except Exception as e:  # noqa: BLE001
        return [f"{name}: not valid JSON / missing 'quran' key ({e})"]
    problems: list[str] = []
    if len(rows) != TOTAL_AYAT:
        problems.append(f"{name}: expected {TOTAL_AYAT} ayat, found {len(rows)}")
    seen: dict[int, list[int]] = {}
    for r in rows:
        try:
            c, v, t = int(r["chapter"]), int(r["verse"]), r["text"]
        except Exception:  # noqa: BLE001
            problems.append(f"{name}: malformed row {r!r}"[:120]); break
        if not (1 <= c <= 114):
            problems.append(f"{name}: chapter {c} out of range"); break
        if not isinstance(t, str) or not t.strip():
            problems.append(f"{name}: empty text at {c}:{v}"); break
        seen.setdefault(c, []).append(v)
    if len(seen) != 114:
        problems.append(f"{name}: {len(seen)} surahs present, expected 114")
    for c, vs in seen.items():
        if vs != list(range(1, len(vs) + 1)):
            problems.append(f"{name}: surah {c} verse numbering not 1..{len(vs)} consecutive"); break
    return problems


def download(name: str, bases: list[str]) -> bytes:
    last = None
    for b in bases:
        url = f"{b}/{name}.json"
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e; print(f"  {url} failed: {e}")
    raise SystemExit(f"could not download {name}: {last}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", help="override mirror (also accepts file:///path/to/dir)")
    ap.add_argument("--force", action="store_true", help="re-download even if the file already verifies")
    a = ap.parse_args()
    bases = [a.base_url.rstrip("/")] if a.base_url else BASES
    DATA.mkdir(parents=True, exist_ok=True)
    man_path = DATA / "MANIFEST.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else None
    new_hashes: dict[str, str] = {}
    for name in EDITIONS:
        dest = DATA / f"{name}.json"
        want = manifest["editions"].get(name, {}).get("sha256") if manifest else None
        if dest.exists() and not a.force:
            have = sha256_bytes(dest.read_bytes())
            if want is None or have == want:
                if not validate_structure(dest.read_bytes(), name):
                    print(f"have {name} ({have[:12]}…)"); new_hashes[name] = have; continue
            print(f"{name}: existing file does not verify, re-downloading")
        print(f"downloading {name}")
        raw = download(name, bases)
        probs = validate_structure(raw, name)
        if probs:
            print("\n".join("  FAIL " + p for p in probs)); return 1
        got = sha256_bytes(raw)
        if want is not None and got != want:
            print(f"  FAIL {name}: sha256 {got} != pinned {want}. Refusing to use it."); return 1
        dest.write_bytes(raw); new_hashes[name] = got
    if manifest is None:
        sys.path.insert(0, str(ROOT))
        from ivs.quran import build_manifest
        build_manifest(DATA)
        print("\nNO MANIFEST WAS PRESENT -> created one from this download (trust-on-first-use).")
        print("Next: python -m ivs verify-data ; spot-check verses against a printed mushaf ; then COMMIT assets/data/.")
    else:
        print("\nAll editions match the pinned manifest.")
    for k, v in new_hashes.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
