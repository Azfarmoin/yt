"""Resumable job pipeline: queued -> verified -> generating -> rendered -> needs_review|approved -> published."""
from __future__ import annotations
import json, shutil, traceback, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
from .config import resolve
from .db import DB
from .topics import TopicSelector
from .render import render_video
from .content import load_stories as C_load_stories
from .qc import run_qc
from .textutil import fingerprint
from . import hooks, engagement

PALETTES = ["default", "emerald", "midnight"]

def make_metadata(content, render: dict) -> dict:
    first = content.segments[0]
    en_preview = "\n".join(f"{s.label}: {s.en}" if s.label else s.en for s in content.segments)
    tag = {"quran_ayah": "#Quran", "hadith": "#Hadith", "story": "#IslamicStories"}[content.category]
    first = content.segments[0] if content.segments else None
    tags = [tag, "#Islam", "#Shorts", "#" + content.theme.title().replace(" ", "").replace("'", "")]
    title = (f"{content.source['title']} | {content.theme.title()}" if content.category == "story"
             else f"{content.theme.title()} | {content.reference_line}")
    title = (title[:92] + " #Shorts") if "#Shorts" not in title else title
    title = title[:100]
    lines = [content.hook, ""]
    if content.script and content.script.get("context"):
        lines += [content.script["context"]["en"], ""]
    lines += [en_preview if len(en_preview) < 900 else en_preview[:880] + "…", ""]
    if content.script and content.script.get("takeaway"):
        lines += [f"Takeaway: {content.script['takeaway']['en']}", "(Context and takeaway lines are editorial reflections, not tafsir.)", ""]
    lines += [f"Source: {content.reference_line}"]
    if content.source.get("translations"):
        tr = content.source["translations"]
        lines += [f"Arabic text: Quran Complex Uthmani Hafs (checksum-pinned). Urdu translation: {tr['ur'].split(':')[-1].strip()}. English translation: {tr['en'].split(':')[-1].strip()}."]
        lines += ["Video is text-only (no recitation audio)." if render["text_only"] else "Recitation: recorded audio from a verified source (see engine docs)."]
    if render.get("voices"):
        lines += ["Narration is synthetic (free local text-to-speech), not a scholar's or reciter's voice."]
    if content.category == "hadith":
        lines += [f"Grading: {content.source.get('grading', '')}", f"Text source: {content.source.get('text_source', '')}",
                  f"Verified on: {content.source.get('verified_on', '')}"]
    lines += ["", " ".join(tags)]
    return {"title": title, "description": "\n".join(lines), "tags": tags, "default_language": "en", "audio_language": "ar" if content.category != "story" else "en"}

class Pipeline:
    def __init__(self, cfg: dict, db: DB | None = None, selector: TopicSelector | None = None):
        self.cfg = cfg
        self.out_root = resolve(cfg, cfg["paths"]["output"]); self.out_root.mkdir(parents=True, exist_ok=True)
        self.cache = resolve(cfg, cfg["paths"]["cache"])
        self.db = db or DB(resolve(cfg, cfg["paths"]["db"]))
        self.sel = selector or TopicSelector(cfg, self.db)
        self.tz = ZoneInfo(cfg.get("timezone", "Asia/Karachi"))

    # ---- creation -------------------------------------------------
    def make_next(self, scheduled_for: str | None = None, only: str | None = None) -> int | None:
        """Pick verified unique content and run it to a terminal-for-now state. Returns item id, or None (skip day)."""
        if self.db.setting("paused") == "1":
            self.db.log("info", "automation paused; nothing generated"); return None
        content = self.sel.next_content(only)
        if content is None:
            self.db.log("warn", "no sufficiently unique verified content available; skipping (nothing fabricated)")
            return None
        chosen, scored = hooks.select_hook(content, self.db)
        if chosen is None:
            self.db.reject(content.key, content.category, "no acceptable hook: every candidate was forbidden, off-topic or repeated")
            self.db.log("warn", f"{content.key}: no acceptable hook candidate; skipped"); return None
        content.hook = chosen
        tcands = hooks.title_candidates(content, chosen); title = hooks.pick_title(tcands, self.db)
        cta = hooks.pick_cta(self.db, len(self.db.items()))
        c = self.db.conn
        cur = c.execute("""INSERT INTO content_items(category,key,topic,status,source_json,text_fingerprint,script_text,created_at,updated_at,scheduled_for,
                                                     hook_candidates,title_candidates)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (content.category, content.key, content.theme, "verified", json.dumps(content.source, ensure_ascii=False),
                         fingerprint(content.similarity_text()), content.similarity_text(), self._now(), self._now(), scheduled_for,
                         json.dumps({"chosen": chosen, "cta": cta, "candidates": scored}, ensure_ascii=False),
                         json.dumps({"chosen": title, "candidates": tcands}, ensure_ascii=False)))
        item_id = cur.lastrowid
        for s, a in content.ayat:
            c.execute("INSERT INTO used_ayat(surah,ayah,item_id) VALUES(?,?,?)", (s, a, item_id))
        c.commit()
        self.db.log("info", f"selected {content.key}", item_id)
        self.render_item(item_id, content)
        return item_id

    def _now(self): return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    def _rebuild_content(self, item):
        """Re-create Content from the DB row's key (resumable jobs don't keep objects in memory)."""
        from . import content as C
        from .catalog import QURAN, HADITH
        key = item["key"]
        if key.startswith("quran:"):
            _, s, rng = key.split(":"); a1, _, a2 = rng.partition("-"); a1 = int(a1); a2 = int(a2 or a1)
            e = next((e for e in QURAN if (e[0], e[1], e[2]) == (int(s), a1, a2)), None)
            return C.build_quran(self.sel.quran, e)[0] if e else C.build_quran_seq(self.sel.quran, int(s), a1, a2)[0]
        if key.startswith("hadith:"):
            _, col, num = key.split(":")
            e = next(e for e in HADITH if e["collection"] == col and e["number"] == int(num))
            return C.build_hadith(self.sel.hadith, e)[0]
        d = next(d for d in C.load_stories(self.sel.stories_dir) if f"story:{d['id']}" == key)
        return C.build_story(d, self.sel.quran)[0]

    def render_item(self, item_id: int, content=None) -> dict:
        item = self.db.get_item(item_id)
        content = content or self._rebuild_content(item)
        if content is None:
            self.db.set_status(item_id, "failed", error="content could not be rebuilt/verified"); return {}
        hc = json.loads(item["hook_candidates"] or "{}"); tc = json.loads(item["title_candidates"] or "{}")
        if hc.get("chosen"): content.hook = hc["chosen"]
        content.cta = hc.get("cta", "")
        self.db.set_status(item_id, "generating", error=None)
        work = self.out_root / f"{item_id:04d}_{content.key.replace(':', '_')}"
        try:
            palette = PALETTES[item_id % len(PALETTES)]
            from . import blender_shot, director as DIR
            if content.category == "story":
                sd = next(d for d in C_load_stories(self.sel.stories_dir) if f"story:{d['id']}" == content.key)
                content.treatment = DIR.treat(content, sd, self.db); DIR.save(self.db, content.treatment)
                (work).mkdir(parents=True, exist_ok=True); (work / "treatment.json").write_text(json.dumps(content.treatment, indent=2, ensure_ascii=False))
            shots = blender_shot.provider(content, self.db, self.cfg, self.cache, getattr(self, "render_3d", False)) if content.category == "story" else None
            r = render_video(self.cfg, content, work, self.cache, palette, shots)
            qc = run_qc(self.cfg, content, r, self.db, item_id)
            (work / "qc_report.json").write_text(json.dumps(qc, indent=2, ensure_ascii=False))
            meta = make_metadata(content, r)
            if tc.get("chosen"): meta["title"] = (tc["chosen"] + " #Shorts")[:100]
            meta["title_candidates"] = tc.get("candidates", []); meta["hook_candidates"] = hc.get("candidates", [])
            ver_ok = not content.source.get("verification", {}).get("problems")
            hs = next((x for x in hc.get("candidates", []) if x["hook"] == content.hook), None)
            eng = engagement.score(content, r, hs, content.cta, ver_ok)
            meta["engagement"] = eng
            reviewed_script = (not content.script) or content.script.get("reviewed") or not self.cfg.get("script", {}).get("require_review", True)
            if not ver_ok: rel = "REJECTED"
            elif content.needs_review or not reviewed_script: rel = "NEEDS_HUMAN_REVIEW"
            else: rel = "VERIFIED"
            qual = "REJECTED" if not qc["passed"] else ("APPROVED" if eng["total"] >= engagement.min_for(content) else "NEEDS_REVISION")
            meta["religious_verification"], meta["content_quality"] = rel, qual
            self._record_claims(item_id, content, r, rel)
            hooks.log_style(self.db, item_id, content.hook, meta["title"], content.script["takeaway"]["en"] if content.script and content.script.get("takeaway") else "", content.cta)
            if content.script:
                (work / "script.json").write_text(json.dumps({"hook": content.hook, **content.script, "source": content.reference_line}, indent=2, ensure_ascii=False))
            (work / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
            for a in r["assets"]:
                self.db.conn.execute("INSERT INTO assets_used(item_id,name,kind,source_url,license,attribution) VALUES(?,?,?,?,?,?)",
                                     (item_id, a["name"], a["kind"], a["source_url"], a["license"], a["attribution"]))
            self.db.conn.commit()
            fields = dict(religious_verification=rel, content_quality=qual, engagement_score=eng["total"], video_path=r["video"], video_sha256=r["sha256"], thumbnail_path=r["thumbnail"], title=meta["title"],
                          description=meta["description"], tags=json.dumps(meta["tags"]))
            if not qc["passed"]:
                self.db.set_status(item_id, "failed", error="QC failed: " + ", ".join(qc["failed"]), **fields)
            elif rel != "VERIFIED" or qual != "APPROVED":
                reasons = [x for x in (content.review_reason if content.needs_review else "",
                                       "Editorial script lines (context/takeaway) have not been reviewed by a qualified person."
                                       if self._script_needs_review(content) else "",
                                       f"Engagement score {eng['total']}/100 is below {engagement.min_for(content)}." if qual == "NEEDS_REVISION" else "") if x]
                self.db.set_status(item_id, "needs_review", review_reason=" ".join(reasons), **fields)
            else:
                self.db.set_status(item_id, "rendered", **fields)
                self._auto_approve(item_id)
            return qc
        except Exception as e:
            self.db.set_status(item_id, "failed", error=f"{type(e).__name__}: {e}")
            self.db.log("error", traceback.format_exc()[-1500:], item_id)
            return {}

    def _record_claims(self, item_id: int, content, r: dict, rel: str) -> None:
        """Permanent audit trail: one row per displayed religious claim / editorial line."""
        c = self.db.conn; c.execute("DELETE FROM claims WHERE item_id=?", (item_id,))
        ver = content.source.get("verification", {}) or {}
        tr = content.source.get("translations", {}) or {}
        status = "automated_only" if rel == "VERIFIED" else ("rejected" if rel == "REJECTED" else "awaiting_human_review")
        today = ver.get("verified_on") or content.source.get("verified_on") or ""
        n = 0
        def add(kind, ar, trans, translator, title, ref, grade, method, url, lic, rev):
            nonlocal n; n += 1
            c.execute("INSERT INTO claims(claim_id,item_id,kind,arabic,translation,translator,source_title,reference,grade,method,source_url,license,verified_on,reviewer_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (f"{item_id}-{n}", item_id, kind, ar, trans, translator, title, ref, grade, method, url, lic, today, rev))
        for sg in content.segments:
            if sg.kind == "verse" or content.category in ("quran_ayah", "hadith"):
                if content.category == "hadith":
                    add("hadith", sg.ar, sg.en, content.source.get("translations", {}).get("en", ""), content.source.get("collection", ""), content.reference_line,
                        content.source.get("grading", ""), "number + book-ref + keyword match against data source; matn markers",
                        content.source.get("text_source", ""), "open data mirror", status)
                else:
                    add("quran_ayah", sg.ar, sg.en, tr.get("en", ""), "Quran (Uthmani Hafs, King Fahd Complex)", sg.label, "n/a",
                        "SHA-256 pinned data + independent 2nd-edition cross-check + range check", "https://github.com/fawazahmed0/quran-api", "Tanzil / KFQC terms", status)
            else:
                add("story_narration", "", f"{sg.en} | {sg.ur}", "story author", content.source.get("title", ""), "; ".join(content.source.get("sources", [])),
                    "n/a", "author-written; must follow cited sources (literal reading of the verses)", "", "original", "awaiting_human_review")
        if content.script:
            for k in ("context", "takeaway"):
                if content.script.get(k):
                    add("script_" + k, "", json.dumps(content.script[k], ensure_ascii=False), content.script.get("author", ""), content.reference_line, content.reference_line,
                        "n/a", "editorial reflection, not tafsir", "", "original", "reviewed" if content.script.get("reviewed") else "awaiting_human_review")
        c.commit()

    def _script_needs_review(self, content) -> bool:
        return bool(content.script and self.cfg.get("script", {}).get("require_review", True) and not content.script.get("reviewed"))

    def _auto_approve(self, item_id: int) -> None:
        """Approval policy: mode=approval -> stays 'rendered' until a human approves; auto/draft -> approved."""
        mode = self.cfg["publishing"]["mode"]
        it = self.db.get_item(item_id)
        if mode == "auto" and it["religious_verification"] == "VERIFIED" and it["content_quality"] == "APPROVED":
            self.db.set_status(item_id, "approved")

    # ---- review actions -------------------------------------------
    def approve(self, item_id: int) -> None:
        it = self.db.get_item(item_id)
        if it["status"] not in ("rendered", "needs_review"):
            raise ValueError(f"item {item_id} is '{it['status']}', cannot approve")
        self.db.set_status(item_id, "approved", religious_verification="VERIFIED", content_quality="APPROVED")
        self.db.conn.execute("UPDATE claims SET reviewer_status='human_approved' WHERE item_id=? AND reviewer_status IN ('awaiting_human_review','automated_only')", (item_id,))
        self.db.conn.commit()

    def skip(self, item_id: int) -> None:
        self.db.set_status(item_id, "skipped")

    def resume_incomplete(self) -> list[int]:
        """Crash recovery: re-render items stuck in 'generating' (never touches published items)."""
        done = []
        for it in self.db.items("generating"):
            self.render_item(it["id"]); done.append(it["id"])
        return done
