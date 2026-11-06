import json, yaml
from pathlib import Path
from ivs import ci

def test_parse_command_strict():
    assert ci.parse_command("/approve 12") == ("approve", 12)
    assert ci.parse_command("/skip 3\nthanks") == ("skip", 3)
    for bad in ["/approve 12; rm -rf /", "/approve", "/approve -1", "approve 1", "/approve 1 2", "", "x\n/approve 1", "/approve $(id)"]:
        assert ci.parse_command(bad) is None

def test_overrides_need_all_secrets():
    cfg = ci.apply_overrides({}, {"YOUTUBE_CLIENT_ID": "a"})
    assert cfg["publishing"]["platforms"]["youtube"]["enabled"] is False and cfg["three_d"]["enabled"] is False
    full = {"YOUTUBE_CLIENT_ID": "a", "YOUTUBE_CLIENT_SECRET": "b", "YOUTUBE_REFRESH_TOKEN": "c", "IVS_YT_PRIVACY": "private"}
    c2 = ci.apply_overrides({}, full)
    assert c2["publishing"]["platforms"]["youtube"]["enabled"] and c2["publishing"]["platforms"]["youtube"]["privacy"] == "private"
    assert ci.apply_overrides({}, {"IVS_MODE": "bogus"})["publishing"]["mode"] == "auto"

def test_drafts_are_not_loaded(tmp_path):
    from ivs.content import load_stories
    (tmp_path / "a.yaml").write_text(yaml.safe_dump({"id": "a"}))
    (tmp_path / "b.yaml").write_text(yaml.safe_dump({"id": "b", "draft": {"needs_human_review": True}}))
    assert [d["id"] for d in load_stories(tmp_path)] == ["a"]

def test_workflows_are_safe():
    root = Path(__file__).resolve().parent.parent
    for f in (root / ".github" / "workflows").glob("*.yml"):
        y = yaml.safe_load(f.read_text()); assert y.get("jobs")
        txt = f.read_text()
        assert "github.event.comment.body }}" not in txt.replace("COMMENT: ${{ github.event.comment.body }}", "")   # comment only via env
        if f.name in ("daily.yml", "approve.yml"):                     # these two write the state branch
            assert "secrets.GITHUB_TOKEN" in txt
    ap = (root / ".github/workflows/approve.yml").read_text()
    assert "repository_owner" in ap
    ci = (root / ".github/workflows/ci.yml").read_text()
    assert "contents: read" in ci and "secrets." not in ci            # CI must not need write access or secrets
    assert "YOUTUBE_" not in ci and "git push" not in ci              # CI tests only, never publishes

def test_queue_valid():
    q = yaml.safe_load((Path(__file__).resolve().parent.parent / "content" / "queue.yaml").read_text())
    assert q and all({"id", "ref", "title"} <= set(e) for e in q)

def test_sequence_pool_is_huge_unique_and_covers_quran():
    from ivs.config import load_config
    from ivs.quran import Quran
    from ivs import content as C
    q = Quran(load_config(None))
    ch = list(C.seq_chunks(q))
    keys = [(s, a1, a2) for s, a1, a2 in ch]
    assert len(set(keys)) == len(keys) > 1500
    assert sum(b - a + 1 for _, a, b in ch) == 6236
    c, rep = C.build_quran_seq(q, *ch[0]); assert c and c.script is None and not c.needs_review

def test_sequence_content_rebuilds_from_key_and_threshold():
    from ivs.config import load_config
    from ivs.quran import Quran
    from ivs import content as C, engagement
    q = Quran(load_config(None)); s, a, b = list(C.seq_chunks(q))[5]
    c, _ = C.build_quran_seq(q, s, a, b)
    assert c.key == f"quran:{s}:{a}-{b}" if a != b else f"quran:{s}:{a}"
    assert engagement.min_for(c) == 70 and engagement.min_for(C.build_quran(q, __import__("ivs.catalog", fromlist=["x"]).QURAN[0])[0]) == 80

def test_ten_per_day_capped_by_quota():
    s = ci.slots_for({})
    assert s["videos_per_day"] == 6 and len(set(s["times"])) == 6            # default free quota = 6 uploads
    s = ci.slots_for({"IVS_YT_QUOTA": "20000"})
    assert s["videos_per_day"] == 10 and s["times"][0] == "06:00" and len(set(s["times"])) == 10 and all(t < "24:00" for t in s["times"])
    assert ci.slots_for({"IVS_VIDEOS_PER_DAY": "3"})["videos_per_day"] == 3
