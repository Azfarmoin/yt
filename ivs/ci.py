"""GitHub Actions glue: CI overrides, chat-ops command parsing (owner-only /approve N, /skip N), run report/summary.
Nothing here talks to the network; publishing still goes through publish_youtube (official API, local quota guard)."""
from __future__ import annotations
import json, os, re
from pathlib import Path

CMD = re.compile(r"^\s*/(approve|skip)\s+(\d{1,6})\s*$")

def parse_command(comment: str) -> tuple[str, int] | None:
    """Only the FIRST line of a comment is considered and it must be exactly `/approve N` or `/skip N` (no shell, no extra text)."""
    first = (comment or "").splitlines()[0] if (comment or "").strip() else ""
    m = CMD.match(first)
    return (m.group(1), int(m.group(2))) if m else None

PER_UPLOAD = 1650      # videos.insert 1600 + thumbnails.set 50 units

def slots_for(env) -> dict:
    """N videos/day (IVS_VIDEOS_PER_DAY, default 10) spread over 06:00-23:00 Karachi time, but never more than the YouTube quota can upload
    (IVS_YT_QUOTA, default 10000 = 6/day): making videos that can't be uploaded would only pile up a backlog."""
    want = max(1, min(24, int(env.get("IVS_VIDEOS_PER_DAY") or 10)))
    cap = max(1, int(env.get("IVS_YT_QUOTA") or 10000) // PER_UPLOAD)
    n = min(want, cap)
    times = [f"{int(6 + i * 17 / n) % 24:02d}:{int((6 + i * 17 / n) % 1 * 60):02d}" for i in range(n)]
    return {"times": times, "videos_per_day": n}

def apply_overrides(cfg: dict, env=None) -> dict:
    """CI defaults: 2.5D only (3D is too slow for runners), auto-publish ONLY content that is fully verified with no review flags
    (Quran ayah), everything else waits for `/approve`. YouTube is enabled only when all three secrets exist; privacy defaults to private."""
    env = os.environ if env is None else env
    cfg.setdefault("three_d", {})["enabled"] = False
    cfg.setdefault("schedule", {}).update(slots_for(env))
    pub = cfg.setdefault("publishing", {}); pub["mode"] = env.get("IVS_MODE", "auto") if env.get("IVS_MODE") in ("auto", "approval", "draft") else "auto"
    yt = pub.setdefault("platforms", {}).setdefault("youtube", {})
    have = all(env.get(k) for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"))
    yt["enabled"] = bool(have)
    if env.get("IVS_YT_PRIVACY") in ("private", "unlisted", "public"): yt["privacy"] = env["IVS_YT_PRIVACY"]
    return cfg

def build_report(pipe, res: dict) -> dict:
    items = []
    for iid in res.get("generated", []):
        it = pipe.db.get_item(iid)
        items.append({"id": iid, "key": it["content_key"] if "content_key" in it.keys() else "", "title": it["title"], "status": it["status"], "review_reason": it["review_reason"] or "",
                      "religious_verification": it["religious_verification"], "content_quality": it["content_quality"], "error": it["error"] or ""})
    review = [i for i in items if i["status"] in ("needs_review", "rendered")]
    return {"generated": items, "needs_review": review, "published": res.get("published", []), "errors": res.get("errors", []),
            "skipped_slots": res.get("skipped_slots", []), "recovered": res.get("recovered", [])}

def markdown(rep: dict) -> str:
    L = ["## Islamic video engine run", ""]
    for i in rep["generated"]: L.append(f"- item **{i['id']}** `{i['status']}` {i['title'] or ''} {('(' + i['review_reason'] + ')') if i['review_reason'] else ''} {i['error']}")
    if not rep["generated"]: L.append("- nothing generated this run (slot already done, or no unique verified content)")
    for u in rep["published"]: L.append(f"- published: {u}")
    for e in rep["errors"]: L.append(f"- ERROR: {e}")
    if rep["needs_review"]: L += ["", "Needs your review. Reply `/approve <id>` or `/skip <id>` on the issue the workflow opened."]
    return "\n".join(L) + "\n"

def write_outputs(rep: dict, out: Path = Path("output")) -> None:
    out.mkdir(exist_ok=True); (out / "ci_report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    s = os.environ.get("GITHUB_STEP_SUMMARY")
    if s:
        with open(s, "a", encoding="utf-8") as f: f.write(markdown(rep))
