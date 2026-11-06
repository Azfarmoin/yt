import json, pytest
from ivs import direction as D
from ivs.content import load_stories
from pathlib import Path

STORIES = load_stories(Path(__file__).resolve().parent.parent / "content" / "stories")

def test_migration_3_tables(db):
    names = {r[0] for r in db.conn.execute("select name from sqlite_master where type='table'")}
    assert {"direction_log", "storyboards"} <= names

@pytest.mark.parametrize("st", STORIES, ids=lambda s: s["id"])
def test_storyboard_passes_qc(db, st):
    sb = D.build_storyboard(st, db); qc = D.qc_storyboard(sb, db)
    assert qc["ok"], qc
    assert sb["scenes"][0]["role"] == "hook"
    assert all(s["camera"] in D.CAMERAS for s in sb["scenes"])

def test_no_consecutive_repeat_and_hook_differs_between_videos(db):
    hooks = []
    for st in STORIES:
        sb = D.build_storyboard(st, db); D.save(db, st, sb, D.qc_storyboard(sb, db)); hooks.append(sb["scenes"][0]["camera"])
        cams = [s["camera"] for s in sb["scenes"]]; assert all(a != b for a, b in zip(cams, cams[1:]))
    assert len(set(hooks)) == len(hooks)          # anti-repetition across videos

def test_character_design_consistent_per_story(db):
    st = STORIES[0]; sb = D.build_storyboard(st, db); D.save(db, st, sb, {"ok": True})
    assert D.build_storyboard(st, db)["characters"]["palette_name"] == sb["characters"]["palette_name"]

def test_qc_rejects_forbidden_actor_and_prophet_text(db):
    sb = D.build_storyboard(STORIES[0], db)
    sb["scenes"][1]["actors"] = [{"type": "prophet", "count": 1}]
    assert any("not allowed" in p for p in D.qc_storyboard(sb)["problems"])
    sb = D.build_storyboard(STORIES[0], db); sb["scenes"][1]["visual"] = "a prophet standing"
    assert any("forbidden" in p for p in D.qc_storyboard(sb)["problems"])

def test_qc_rejects_repetitive_camera(db):
    sb = D.build_storyboard(STORIES[0], db)
    for s in sb["scenes"]: s["camera"] = "orbit"
    assert not D.qc_storyboard(sb)["ok"]

def test_no_actor_for_prophets_exists():
    assert D.ALLOWED_ACTORS == {"walker", "spearman", "traveller", "elephant", "camel", "ship", "bird"}
    assert all(t in D.ALLOWED_ACTORS for v in D.ACTION_ACTORS.values() for t, _ in v)
