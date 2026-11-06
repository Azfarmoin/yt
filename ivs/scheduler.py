"""Local scheduler. Honest by design: it only runs while this process (or the OS scheduler entry that launches it) runs;
missed slots are caught up on next start. It does NOT promise 24/7 operation."""
from __future__ import annotations
import time, datetime as dt
from zoneinfo import ZoneInfo

def due_slots(cfg: dict, now: dt.datetime, db) -> list[str]:
    """Slots (HH:MM, local tz) whose time has passed today and which have no item scheduled yet."""
    tz = ZoneInfo(cfg["timezone"]); now = now.astimezone(tz); today = now.date().isoformat()
    out = []
    for hhmm in cfg["schedule"]["times"][: cfg["schedule"]["videos_per_day"]]:
        h, m = map(int, hhmm.split(":"))
        if now >= now.replace(hour=h, minute=m, second=0, microsecond=0):
            tag = f"{today}T{hhmm}"
            if not db.conn.execute("SELECT 1 FROM content_items WHERE scheduled_for=?", (tag,)).fetchone():
                out.append(tag)
    return out

def tick(pipe, publisher=None, now: dt.datetime | None = None) -> dict:
    """One scheduler iteration: recover, generate due slots, publish approved items if mode allows."""
    cfg, db = pipe.cfg, pipe.db
    now = now or dt.datetime.now(dt.timezone.utc)
    res = {"recovered": pipe.resume_incomplete(), "generated": [], "skipped_slots": [], "published": [], "errors": []}
    if db.setting("paused") == "1":
        return res
    for tag in due_slots(cfg, now, db):
        iid = pipe.make_next(scheduled_for=tag)
        if iid is None:
            res["skipped_slots"].append(tag)
            db.conn.execute("INSERT INTO event_log(ts,level,msg) VALUES(datetime('now'),'warn',?)", (f"slot {tag} skipped: no unique verified content",)); db.conn.commit()
        else:
            res["generated"].append(iid)
    mode = cfg["publishing"]["mode"]
    yt = cfg["publishing"]["platforms"].get("youtube", {})
    if publisher and mode in ("auto", "approval") and yt.get("enabled"):
        for it in db.items("approved"):
            try:
                res["published"].append(publisher.publish(it["id"])["url"])
            except Exception as e:                       # one failure must not stop the loop; item stays 'approved' for retry
                res["errors"].append(f"item {it['id']}: {e}"); db.log("error", f"publish failed: {e}", it["id"])
    return res

def daemon(pipe, publisher=None, interval=60):
    print("scheduler running (Ctrl+C to stop). Timezone:", pipe.cfg["timezone"])
    while True:
        r = tick(pipe, publisher)
        if any(r.values()): print(r)
        time.sleep(interval)
