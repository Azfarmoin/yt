import json, subprocess
from pathlib import Path
import pytest
from ivs.pipeline import Pipeline
from ivs.db import DB
from ivs import audio as A, render as R

def mk(cfg):
    return Pipeline(cfg, DB(":memory:"))

def test_text_only_video_is_labeled_and_passes_qc(cfg):
    cfg["audio"]["recitation"]["enabled"] = False
    p = mk(cfg); i = p.make_next(); it = p.db.get_item(i)
    assert it["status"] == "rendered", it["error"]
    qc = json.loads((Path(it["video_path"]).parent / "qc_report.json").read_text())
    names = {c["name"]: c for c in qc["checks"]}
    assert names["recitation"]["status"] == "warn" and "text-only" in names["recitation"]["detail"]
    assert "text-only" in it["description"].lower()
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", it["video_path"]], capture_output=True, text=True).stdout)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)

def test_recitation_path_mixes_real_audio(cfg, tone_mp3, monkeypatch):
    cfg["audio"]["recitation"]["permission_verified"] = True
    # stand-in for a downloaded recitation file (a tone, because the sandbox cannot reach recitation hosts)
    monkeypatch.setattr(R, "fetch_recitation", lambda cfg, cache, s, a: {"path": str(tone_mp3), "duration": 6.0, "source_url": "test://tone",
                                                                         "reciter": "test", "license": "test-only"})
    p = mk(cfg); i = p.make_next(); it = p.db.get_item(i)
    assert it["status"] == "rendered", it["error"]
    qc = json.loads((Path(it["video_path"]).parent / "qc_report.json").read_text())
    st = {c["name"]: c["status"] for c in qc["checks"]}
    assert st["audio_audible"] == "pass" and st["recitation"] == "pass"
    assert p.db.conn.execute("select count(*) from assets_used where item_id=?", (i,)).fetchone()[0] == 2   # one per ayah, license recorded

def test_second_run_never_repeats_and_hadith_requires_review(cfg):
    cfg["audio"]["recitation"]["enabled"] = False
    cfg["schedule"]["categories"] = ["hadith", "quran_ayah"]
    p = mk(cfg)
    a = p.make_next(); b = p.make_next()
    assert p.db.get_item(a)["category"] == "hadith" and p.db.get_item(a)["status"] == "needs_review"
    assert p.db.get_item(b)["category"] == "quran_ayah"
    with pytest.raises(ValueError):
        p.db.set_status(a, "needs_review"); p.approve(a); p.approve(a)       # second approve must fail (already approved)

def test_skip_day_when_nothing_unique(cfg, monkeypatch):
    cfg["audio"]["recitation"]["enabled"] = False
    cfg["schedule"]["categories"] = ["story"]                                 # no story files exist -> nothing to publish
    p = mk(cfg); p.sel.stories_dir = Path(cfg["paths"]["cache"]) / "no_stories"
    assert p.make_next() is None
    assert p.db.conn.execute("select count(*) from content_items").fetchone()[0] == 0     # nothing fabricated

def test_resume_rerenders_stuck_generating_item(cfg):
    cfg["audio"]["recitation"]["enabled"] = False
    p = mk(cfg); i = p.make_next()
    p.db.set_status(i, "generating")                                           # simulate crash mid-render
    assert p.resume_incomplete() == [i]
    assert p.db.get_item(i)["status"] == "rendered"
    assert p.db.conn.execute("select count(*) from content_items").fetchone()[0] == 1    # no duplicate rows

def test_paused_pipeline_generates_nothing(cfg):
    p = mk(cfg); p.db.put_setting("paused", "1")
    assert p.make_next() is None
