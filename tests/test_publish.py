import json
from pathlib import Path
import pytest
from ivs.publish_youtube import YouTubePublisher, PublishError, AuthExpired, QuotaExceeded, DAILY_QUOTA
from ivs.pipeline import Pipeline
from ivs.db import DB

class Resp:
    def __init__(self, code=200, js=None, headers=None, text=""):
        self.status_code, self._js, self.headers, self.text = code, js or {}, headers or {}, text
    def json(self): return self._js

class FakeHTTP:
    def __init__(self): self.calls = []
    def post(self, url, **kw):
        self.calls.append(("POST", url))
        if "oauth2" in url: return Resp(200, {"access_token": "tok"})
        if "uploadType=resumable" in url: return Resp(200, headers={"Location": "https://up.example/session"})
        return Resp(200)
    def put(self, url, **kw):
        self.calls.append(("PUT", url)); return Resp(200, {"id": "VID123"})

@pytest.fixture
def ready(cfg, monkeypatch):
    cfg["audio"]["recitation"]["enabled"] = False
    cfg["publishing"]["platforms"]["youtube"]["enabled"] = True
    for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"): monkeypatch.setenv(k, "x")
    p = Pipeline(cfg, DB(":memory:")); i = p.make_next(); p.approve(i)
    return p, i

def test_publish_once_then_blocks_duplicate(ready):
    p, i = ready; http = FakeHTTP(); y = YouTubePublisher(p.cfg, p.db, http)
    r = y.publish(i)
    assert r["id"] == "VID123" and p.db.get_item(i)["status"] == "published"
    with pytest.raises(PublishError): y.publish(i)                      # duplicate-upload guard
    assert sum(1 for c in http.calls if "resumable" in c[1]) == 1

def test_never_publishes_unapproved_or_review_items(cfg, monkeypatch):
    cfg["audio"]["recitation"]["enabled"] = False; cfg["schedule"]["categories"] = ["hadith"]
    for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"): monkeypatch.setenv(k, "x")
    p = Pipeline(cfg, DB(":memory:")); i = p.make_next()
    http = FakeHTTP()
    with pytest.raises(PublishError, match="needs_review"): YouTubePublisher(cfg, p.db, http).publish(i)
    assert http.calls == []

def test_quota_guard_blocks_before_any_network_call(ready):
    p, i = ready; http = FakeHTTP(); y = YouTubePublisher(p.cfg, p.db, http)
    y._spend(DAILY_QUOTA - 100, "preload")
    with pytest.raises(QuotaExceeded): y.publish(i)
    assert not any("resumable" in c[1] for c in http.calls)

def test_missing_credentials_reported(ready, monkeypatch):
    p, i = ready; monkeypatch.delenv("YOUTUBE_REFRESH_TOKEN")
    monkeypatch.setattr("ivs.publish_youtube.load_env", lambda path: None)   # a developer's local .env must not refill the token
    with pytest.raises(AuthExpired, match="missing credentials"): YouTubePublisher(p.cfg, p.db, FakeHTTP()).publish(i)

def test_scheduler_tick_generates_publishes_and_survives_errors(ready, monkeypatch):
    import datetime as dt
    from ivs.scheduler import tick
    p, i = ready
    p.cfg["publishing"]["mode"] = "auto"
    http = FakeHTTP(); y = YouTubePublisher(p.cfg, p.db, http)
    res = tick(p, y, now=dt.datetime(2026, 10, 29, 14, 0, tzinfo=dt.timezone.utc))
    assert res["published"], res        # the pre-approved item goes out; new slot item stays rendered or approved per mode
