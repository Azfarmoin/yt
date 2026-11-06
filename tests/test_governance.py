import json
from pathlib import Path
import pytest
from ivs import hooks, audio, engagement
from ivs.pipeline import Pipeline
from ivs.db import DB
from ivs.publish_youtube import YouTubePublisher, PublishError

def test_forbidden_hook_patterns_are_rejected():
    class C: theme = "patience"; reference_line = "x"; source = {}; segments = []; category = "quran_ayah"; hook = ""
    for bad in ("This secret will make you rich", "Guaranteed forgiveness in 10 seconds", "You won't believe what the Quran says about patience"):
        assert hooks.score_hook(bad, C, [])["rejected"]

def test_repeated_hook_pattern_is_rejected_by_history(db):
    class C: theme = "patience"; reference_line = "Surah Al-Baqarah (2:153)"; source = {}; segments = []; category = "quran_ayah"; hook = ""
    h = "What does the Quran teach us about patience?"
    assert not hooks.score_hook(h, C, [])["rejected"]
    db.conn.execute("INSERT INTO style_log(ts,kind,text,pattern) VALUES('t','hook',?,?)", (h, hooks.pattern(h))); db.conn.commit()
    assert hooks.score_hook("What does the Quran teach us about gratitude?", C, hooks.used(db, "hook"))["rejected"]

def test_recitation_not_used_without_verified_permission(cfg, monkeypatch):
    calls = []
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("must not download")))
    cfg["audio"]["recitation"]["enabled"] = True; cfg["audio"]["recitation"]["permission_verified"] = False
    assert audio.fetch_recitation(cfg, Path(cfg["paths"]["cache"]), 94, 5) is None and calls == []

def test_two_statuses_claims_and_publish_gate(cfg, monkeypatch):
    cfg["audio"]["recitation"]["enabled"] = False; cfg["script"]["require_review"] = True
    for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"): monkeypatch.setenv(k, "x")
    p = Pipeline(cfg, DB(":memory:")); i = p.make_next(); it = p.db.get_item(i)
    assert it["religious_verification"] == "NEEDS_HUMAN_REVIEW" and it["status"] == "needs_review"
    assert it["engagement_score"] is not None and json.loads(it["hook_candidates"])["candidates"]
    assert len(json.loads(it["title_candidates"])["candidates"]) == 5
    rows = p.db.conn.execute("select kind, reviewer_status, source_url, translator from claims where item_id=?", (i,)).fetchall()
    assert {r["kind"] for r in rows} >= {"quran_ayah", "script_context", "script_takeaway"} and all(r["reviewer_status"] != "human_approved" for r in rows)
    p.db.set_status(i, "approved")                                    # bypassing review must not allow publishing
    with pytest.raises(PublishError, match="gate"): YouTubePublisher(cfg, p.db, object()).publish(i)
    p.db.set_status(i, "needs_review"); p.approve(i)
    assert p.db.get_item(i)["religious_verification"] == "VERIFIED"
    assert all(r["reviewer_status"] == "human_approved" for r in p.db.conn.execute("select reviewer_status from claims where item_id=? and kind like 'quran%' or kind like 'script%'", (i,)))

def test_engagement_score_never_overrides_failed_verification():
    class C:
        script = {"context": {"en": "x"}, "takeaway": {"en": "y"}}; segments = [type("S", (), {"ar": "a"})()]
    r = {"timeline": [{"kind": k, "dur": 4} for k in ("hook", "script", "ayah", "translation", "script", "outro")], "vfx": True, "voices": ["en"]}
    good = engagement.score(C, r, {"score": 100, "criteria": {"emotion": 1.0}}, "cta", True)
    bad = engagement.score(C, r, {"score": 100, "criteria": {"emotion": 1.0}}, "cta", False)
    assert good["total"] >= 80 and bad["parts"]["religious_accuracy"] == 0 and good["total"] - bad["total"] == 20
