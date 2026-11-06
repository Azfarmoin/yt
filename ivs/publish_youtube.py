"""YouTube Data API v3 publisher (official API, OAuth refresh token, resumable upload).

STATUS: implemented against Google's documented endpoints but NOT exercised against a live account in the build
environment (no network route to Google, no credentials). Test with privacy=private first. See docs/YOUTUBE_SETUP.md.
"""
from __future__ import annotations
import json, os, http.server, urllib.parse, webbrowser, secrets, hashlib, base64, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
THUMB_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube"
import os
UNITS_INSERT, UNITS_THUMB = 1600, 50
DAILY_QUOTA = int(os.environ.get('IVS_YT_QUOTA') or 10000)     # default free quota is 10,000 units/day (check Cloud Console)

class PublishError(Exception): pass
class AuthExpired(PublishError): pass
class QuotaExceeded(PublishError): pass

def load_env(path: Path) -> None:
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())

def _quota_day() -> str:
    return dt.datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()   # YouTube quota resets at midnight Pacific

class YouTubePublisher:
    def __init__(self, cfg: dict, db, http=None):
        self.cfg, self.db, self.http = cfg, db, http or requests
        load_env(Path(cfg["_root"]) / ".env")
        self.yt = cfg["publishing"]["platforms"]["youtube"]

    # ---- quota
    def quota_used_today(self) -> int:
        day = _quota_day()
        r = self.db.conn.execute("SELECT COALESCE(SUM(units),0) FROM quota_log WHERE platform='youtube' AND ts LIKE ?", (day + "%",)).fetchone()
        return int(r[0])

    def _spend(self, units: int, note: str):
        if self.quota_used_today() + units > DAILY_QUOTA:
            raise QuotaExceeded(f"local quota guard: {self.quota_used_today()}+{units} > {DAILY_QUOTA}")
        self.db.conn.execute("INSERT INTO quota_log(platform,ts,units,note) VALUES('youtube',?,?,?)", (_quota_day() + "T" + dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S"), units, note))
        self.db.conn.commit()

    # ---- auth
    def access_token(self) -> str:
        need = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
        missing = [k for k in need if not os.environ.get(k)]
        if missing:
            raise AuthExpired("missing credentials: " + ", ".join(missing) + " (run `python -m ivs auth-youtube`)")
        r = self.http.post(TOKEN_URL, data={"client_id": os.environ["YOUTUBE_CLIENT_ID"], "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
                                             "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=30)
        if r.status_code != 200:
            raise AuthExpired(f"token refresh failed ({r.status_code}): {r.text[:200]} — re-run auth. "
                              "Note: OAuth apps left in 'Testing' mode have refresh tokens that expire after 7 days.")
        return r.json()["access_token"]

    # ---- publish
    def eligible(self, item) -> tuple[bool, str]:
        if item["status"] != "approved": return False, f"status is '{item['status']}', not 'approved'"
        if item["religious_verification"] != "VERIFIED" or item["content_quality"] != "APPROVED":
            return False, f"gate: religious_verification={item['religious_verification']}, content_quality={item['content_quality']}"
        if item["platform_id"]: return False, "already has a platform id (duplicate-upload guard)"
        done = self.db.conn.execute("SELECT 1 FROM publish_log WHERE item_id=? AND platform='youtube' AND ok=1", (item["id"],)).fetchone()
        if done: return False, "publish_log already records a successful upload"
        if not item["video_path"] or not Path(item["video_path"]).exists(): return False, "video file missing"
        return True, "ok"

    def publish(self, item_id: int, publish_at: str | None = None) -> dict:
        item = self.db.get_item(item_id)
        ok, why = self.eligible(item)
        if not ok:
            raise PublishError(why)
        tok = self.access_token()
        meta = json.loads(Path(item["video_path"]).parent.joinpath("metadata.json").read_text(encoding="utf-8"))
        status = {"privacyStatus": self.yt.get("privacy", "private"), "selfDeclaredMadeForKids": False}
        if publish_at:
            status.update(privacyStatus="private", publishAt=publish_at)
        body = {"snippet": {"title": meta["title"], "description": meta["description"], "tags": [t.lstrip("#") for t in meta["tags"]],
                            "categoryId": self.yt.get("category_id", "27"), "defaultLanguage": meta["default_language"],
                            "defaultAudioLanguage": meta["audio_language"]}, "status": status}
        self._spend(UNITS_INSERT, f"videos.insert item {item_id}")
        path = Path(item["video_path"]); size = path.stat().st_size
        H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
             "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"}
        resume_key = f"yt_upload_url:{item_id}"
        url = self.db.setting(resume_key)
        if not url:
            r = self.http.post(f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status", headers=H, data=json.dumps(body), timeout=60)
            self._raise(r)
            url = r.headers["Location"]; self.db.put_setting(resume_key, url)
        with open(path, "rb") as f:
            r = self.http.put(url, data=f.read(), headers={"Content-Type": "video/mp4"}, timeout=600)
        if r.status_code == 308:                                   # incomplete: keep URL so the next run resumes
            raise PublishError("upload incomplete; session saved for resume")
        self._raise(r)
        vid = r.json()["id"]; link = f"https://www.youtube.com/shorts/{vid}"
        self.db.conn.execute("INSERT INTO publish_log(item_id,platform,ts,ok,platform_id,url,detail) VALUES(?,?,?,?,?,?,?)",
                             (item_id, "youtube", dt.datetime.now(dt.timezone.utc).isoformat(), 1, vid, link, status["privacyStatus"]))
        self.db.set_status(item_id, "published", platform_id=vid, platform_url=link, published_at=dt.datetime.now(dt.timezone.utc).isoformat())
        self.db.conn.execute("DELETE FROM settings WHERE key=?", (resume_key,)); self.db.conn.commit()
        if item["thumbnail_path"] and Path(item["thumbnail_path"]).exists():
            try:
                self._spend(UNITS_THUMB, f"thumbnails.set {vid}")
                self.http.post(f"{THUMB_URL}?videoId={vid}", headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"},
                               data=Path(item["thumbnail_path"]).read_bytes(), timeout=60)      # needs a verified channel; failure is non-fatal
            except Exception as e:
                self.db.log("warn", f"thumbnail not set: {e}", item_id)
        return {"id": vid, "url": link}

    def _raise(self, r):
        if r.status_code in (200, 201): return
        if r.status_code == 401: raise AuthExpired("401 from YouTube; refresh token revoked/expired")
        if r.status_code == 403 and "quota" in r.text.lower(): raise QuotaExceeded(r.text[:200])
        self.db.conn.execute("INSERT INTO publish_log(item_id,platform,ts,ok,detail) VALUES(0,'youtube',?,0,?)", (dt.datetime.now(dt.timezone.utc).isoformat(), f"{r.status_code} {r.text[:300]}"))
        self.db.conn.commit()
        raise PublishError(f"YouTube API {r.status_code}: {r.text[:300]}")

def auth_flow(client_id: str, client_secret: str, port: int = 8765) -> str:
    """Installed-app OAuth (loopback + PKCE). Returns the refresh token; you paste it into .env."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    redirect = f"http://127.0.0.1:{port}"
    q = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPES,
                                "access_type": "offline", "prompt": "consent", "code_challenge": challenge, "code_challenge_method": "S256"})
    got = {}
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            got.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
            self.send_response(200); self.end_headers(); self.wfile.write(b"Authorized. You can close this tab.")
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    print("Open this URL if the browser does not start:\n", f"{AUTH_URL}?{q}")
    webbrowser.open(f"{AUTH_URL}?{q}")
    srv.handle_request()
    if "code" not in got: raise AuthExpired(f"authorization failed: {got}")
    r = requests.post(TOKEN_URL, data={"client_id": client_id, "client_secret": client_secret, "code": got["code"][0], "code_verifier": verifier,
                                       "grant_type": "authorization_code", "redirect_uri": redirect}, timeout=30)
    if r.status_code != 200 or "refresh_token" not in r.json():
        raise AuthExpired(f"token exchange failed: {r.text[:300]}")
    return r.json()["refresh_token"]
