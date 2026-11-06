import json, shutil, datetime as dt
from pathlib import Path
import pytest
from ivs.config import load_config, ZeroCostViolation, enforce_zero_cost
from ivs.db import DB
from ivs.dedupe import DuplicateCheck, similarity
from ivs.quran import Quran, DATA
from ivs.textutil import skeleton_ar, for_display_ar
from ivs import visuals as V

def test_migrations_idempotent(tmp_path):
    p = tmp_path / "x.sqlite3"
    DB(p); d2 = DB(p)
    assert d2.conn.execute("PRAGMA user_version").fetchone()[0] == 4
    assert d2.conn.execute("select count(*) from sqlite_master where name='content_items'").fetchone()[0] == 1

def test_zero_cost_refuses_paid_provider(cfg):
    cfg["audio"]["narration"]["provider"] = "elevenlabs"
    with pytest.raises(ZeroCostViolation):
        enforce_zero_cost(cfg)
    cfg["audio"]["narration"].pop("provider"); cfg["zero_cost_mode"] = False
    with pytest.raises(ZeroCostViolation):
        enforce_zero_cost(cfg)

def _insert(db, key, text, ayat=()):
    from ivs.textutil import fingerprint
    cur = db.conn.execute("INSERT INTO content_items(category,key,status,text_fingerprint,script_text,created_at,updated_at) VALUES('quran_ayah',?,?,?,?,'t','t')",
                          (key, "published", fingerprint(text), text))
    for s, a in ayat: db.conn.execute("INSERT INTO used_ayat VALUES(?,?,?)", (s, a, cur.lastrowid))
    db.conn.commit()

def test_dedupe_rejects_key_fingerprint_ayah_overlap_and_near_duplicates(db):
    _insert(db, "quran:94:5-6", "with every difficulty there is relief", [(94, 5), (94, 6)])
    d = DuplicateCheck(db, 0.82)
    assert not d.check("quran:94:5-6", "x")[0]                                  # same key
    assert not d.check("other", "With every difficulty, there is relief!")[0]   # same normalized text
    assert not d.check("quran:94:6", "zzz unrelated", ayat=[(94, 6)])[0]          # ayah overlap
    ok, why = d.check("new", "with every difficulty there is relief indeed")
    assert not ok and "near-duplicate" in why
    assert d.check("fresh", "patience and prayer are help", ayat=[(2, 153)])[0]
    assert d.check("series", "with every difficulty there is relief indeed", allow_series=True)[0]   # admin-approved series

def test_quran_verify_passes_and_catches_tampering(tmp_path):
    q = Quran()
    assert q.verify(94, 5, 6)["ok"]
    assert not q.verify(94, 5, 9)["ok"]                      # outside surah
    # tamper: copy data, corrupt one ayah, keep manifest -> checksum mismatch must be reported
    shutil.copytree(DATA, tmp_path / "d")
    f = tmp_path / "d" / "ara-quranuthmanihaf.json"
    j = json.loads(f.read_text(encoding="utf-8")); j["quran"][0]["text"] += "x"; f.write_text(json.dumps(j), encoding="utf-8")
    bad = Quran(data_dir=tmp_path / "d").verify(1, 1, 1)
    assert not bad["ok"] and any("checksum" in p for p in bad["problems"])

def test_quran_crosscheck_detects_shifted_verse(tmp_path):
    shutil.copytree(DATA, tmp_path / "d")
    import hashlib
    f = tmp_path / "d" / "ara-quransimple.json"
    j = json.loads(f.read_text(encoding="utf-8"))
    idx = next(i for i, e in enumerate(j["quran"]) if (e["chapter"], e["verse"]) == (94, 6))
    j["quran"][idx]["text"] = j["quran"][idx + 1]["text"]    # simulate a verse-boundary shift
    f.write_text(json.dumps(j), encoding="utf-8")
    man = json.loads((tmp_path / "d" / "MANIFEST.json").read_text())
    man["editions"]["ara-quransimple"]["sha256"] = hashlib.sha256(f.read_bytes()).hexdigest()   # isolate the cross-check itself
    (tmp_path / "d" / "MANIFEST.json").write_text(json.dumps(man))
    r = Quran(data_dir=tmp_path / "d").verify(94, 6, 6)
    assert not r["ok"] and any("disagree" in p for p in r["problems"])

def test_every_ayah_in_corpus_passes_crosscheck():
    q = Quran()
    fails = [(s, a) for (s, a) in q.text["ar"] if not q.verify(s, a, a)["ok"]]
    assert fails == []

def test_display_normalization_keeps_stored_text():
    q = Quran(); raw = q.ayah("ar", 94, 6)
    assert "ࣰ" in raw and "ࣰ" not in for_display_ar(raw)

def test_glyph_check_detects_missing_glyphs():
    assert V.glyph_coverage("龍", "ar") != []                 # CJK is not in Amiri
    assert V.glyph_coverage("بِسْمِ ٱللَّهِ", "ar") == []

def test_text_fit_never_goes_below_floor():
    long_ar = " ".join(["وَٱلسَّمَآءَ"] * 60)
    assert V.fit(long_ar, "ar", 900, 640) is None             # must split, not shrink
    chunks = V.split_to_fit(long_ar, "ar", 900, 640)
    assert len(chunks) > 1 and all(V.fit(c, "ar", 900, 640) for c in chunks)

def test_scheduler_due_slots_karachi(cfg, db):
    from ivs.scheduler import due_slots
    cfg["schedule"]["times"] = ["18:00"]; cfg["schedule"]["videos_per_day"] = 1
    before = dt.datetime(2026, 10, 29, 12, 59, tzinfo=dt.timezone.utc)    # 17:59 PKT
    after = dt.datetime(2026, 10, 29, 13, 1, tzinfo=dt.timezone.utc)      # 18:01 PKT
    assert due_slots(cfg, before, db) == []
    assert due_slots(cfg, after, db) == ["2026-10-29T18:00"]
    db.conn.execute("INSERT INTO content_items(category,key,status,scheduled_for,created_at,updated_at) VALUES('x','k','queued','2026-10-29T18:00','t','t')"); db.conn.commit()
    assert due_slots(cfg, after, db) == []                                 # catch-up never double-fills a slot
