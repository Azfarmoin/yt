"""Pre-publication engagement score (0-100) using the weights from the spec. A TRANSPARENT HEURISTIC over measurable
properties of the finished video (structure, pacing, presence of lesson/ending); it cannot judge emotional impact.
Religious accuracy is scored here only as pass/fail evidence and is ALSO a separate mandatory gate: a high score can
never compensate for failed verification."""
from __future__ import annotations
MIN_SCORE = 80
MIN_SCORE_RECITATION = 70      # whole-Quran walk: recitation + verified translation only; no editorial takeaway by design (nothing unreviewed is added), so that part of the heuristic cannot score

def min_for(content) -> int:
    source = getattr(content, "source", None) or {}
    return MIN_SCORE_RECITATION if source.get("sequence") else MIN_SCORE

def score(content, render: dict, hook_score: dict | None, cta: str, verification_ok: bool) -> dict:
    tl = render.get("timeline", [])
    kinds = [t["kind"] for t in tl]
    has_narr = "narration" in kinds
    has_verse = "ayah" in kinds or bool(content.segments and any(s.ar for s in content.segments))
    has_ctx = bool(content.script and content.script.get("context")) or has_narr
    has_take = bool(content.script and content.script.get("takeaway"))
    body = [t for t in tl if t["kind"] not in ("outro",)]
    fast = sum(1 for t in body if t["dur"] <= 9.0) / max(len(body), 1)
    motion = bool(render.get("vfx"))
    voice = bool(render.get("voices"))
    hook_pts = round((hook_score["score"] if hook_score else 50) * 0.20)
    story_pts = (8 if has_ctx else 0) + (6 if has_verse else 0) + (6 if len(tl) >= 5 else 3 if len(tl) >= 4 else 0)
    retention_pts = round(9 * fast) + (6 if motion else 0)
    acc_pts = 20 if verification_ok else 0
    emo_pts = (4 if (hook_score and hook_score["criteria"]["emotion"] >= 1) else 1) + (3 if voice else 0) + (3 if has_take else 0)
    lesson_pts = 10 if has_take else (5 if has_ctx else 0)
    end_pts = (3 if has_take else 0) + (2 if cta else 0)
    parts = {"hook": hook_pts, "storytelling": story_pts, "retention": retention_pts, "religious_accuracy": acc_pts,
             "emotional": emo_pts, "lesson": lesson_pts, "ending": end_pts}
    return {"total": sum(parts.values()), "parts": parts, "min": min_for(content), "method": "rule-based heuristic"}
