"""Daily topic selection: rotation + verification + duplicate rejection. Returns None rather than fabricate."""
from __future__ import annotations
from pathlib import Path
from .config import resolve
from .dedupe import DuplicateCheck
from .quran import Quran
from .hadith import Hadith
from . import content as C
from .catalog import QURAN, HADITH

class TopicSelector:
    def __init__(self, cfg: dict, db, quran: Quran | None = None, hadith: Hadith | None = None):
        self.cfg, self.db = cfg, db
        self.quran = quran or Quran(cfg)
        self.hadith = hadith or Hadith(resolve(cfg, cfg["paths"]["cache"]))
        self.dups = DuplicateCheck(db, cfg.get("dedupe", {}).get("similarity_threshold", 0.82))
        self.stories_dir = Path(cfg["_root"]) / "content" / "stories"

    def _category_order(self) -> list[str]:
        """Least-recently-used category first (balanced rotation)."""
        cats = self.cfg["schedule"]["categories"]
        last = {}
        for r in self.db.conn.execute("SELECT category, MAX(id) m FROM content_items GROUP BY category"):
            last[r["category"]] = r["m"]
        return sorted(cats, key=lambda c: last.get(c, 0))

    def _candidates(self, cat: str):
        if cat == "quran_ayah":
            for e in QURAN:
                yield ("quran:%d:%s" % (e[0], str(e[1]) if e[1] == e[2] else f"{e[1]}-{e[2]}")), (lambda e=e: C.build_quran(self.quran, e))
            for (s, a1, a2) in C.seq_chunks(self.quran):          # then the whole Quran in order: never runs out (6236 ayat)
                yield f"quran:{s}:{a1 if a1 == a2 else f'{a1}-{a2}'}", (lambda s=s, a1=a1, a2=a2: C.build_quran_seq(self.quran, s, a1, a2))
        elif cat == "hadith":
            for e in HADITH:
                yield f"hadith:{e['collection']}:{e['number']}", (lambda e=e: C.build_hadith(self.hadith, e))
        elif cat == "story":
            for d in C.load_stories(self.stories_dir):
                yield f"story:{d.get('id')}", (lambda d=d: C.build_story(d, self.quran))

    def next_content(self, only: str | None = None):
        """Walk categories in rotation order; return the first verified, non-duplicate Content (or None)."""
        for cat in self._category_order():
            for key, build in self._candidates(cat):
                if only and key != only: continue
                if self.db.conn.execute("SELECT 1 FROM content_items WHERE key=?", (key,)).fetchone():
                    continue                                     # cheap skip, not logged as rejection
                content, rep = build()
                if content is None:
                    self.db.reject(key, cat, "verification failed: " + "; ".join(rep.get("problems", [])))
                    continue
                ok, why = self.dups.check(content.key, content.similarity_text(), content.ayat)
                if not ok:
                    self.db.reject(key, cat, "duplicate: " + why)
                    continue
                return content
        return None
