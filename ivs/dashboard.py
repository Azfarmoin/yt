"""Optional local dashboard (Flask, 127.0.0.1 only). The CLI works without it."""
from __future__ import annotations
import html, shutil
from .audit import run_audit
from .publish_youtube import YouTubePublisher

PAGE = """<!doctype html><meta charset=utf-8><title>IVS dashboard</title>
<style>body{font:15px system-ui;margin:24px;max-width:1100px;background:#0f1b22;color:#e8e4da}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #2c4350;padding:6px 8px;text-align:left;vertical-align:top}
a,button{color:#d9b36a}button{background:none;border:1px solid #d9b36a;border-radius:4px;padding:2px 8px;cursor:pointer}
h2{margin-top:28px;color:#d9b36a}.pass{color:#7bd88f}.fail{color:#ff7b72}.warn{color:#e3b341}</style>"""

def create_app(pipe):
    from flask import Flask, redirect, request
    app = Flask(__name__)
    db = pipe.db

    def act(path, label, item_id):
        return f'<form method=post action="{path}/{item_id}" style="display:inline"><button>{label}</button></form>'

    @app.get("/")
    def index():
        c = db.conn
        paused = db.setting("paused") == "1"
        rows = db.items()
        h = [PAGE, f"<h1>Islamic Video Engine</h1><p>Automation: <b>{'PAUSED' if paused else 'running'}</b> "
             f"<form method=post action=/pause style=display:inline><button>{'Resume' if paused else 'Pause'}</button></form></p>"]
        h.append("<h2>Items</h2><table><tr><th>#</th><th>Key</th><th>Status</th><th>Title</th><th>Notes</th><th>Actions</th></tr>")
        for r in rows:
            btn = ""
            if r["status"] in ("rendered", "needs_review"): btn += act("/approve", "Approve", r["id"])
            if r["status"] not in ("published", "skipped"): btn += act("/skip", "Skip", r["id"])
            if r["status"] in ("failed", "generating"): btn += act("/rerender", "Re-render", r["id"])
            link = f' <a href="{html.escape(r["platform_url"])}">video</a>' if r["platform_url"] else ""
            h.append(f"<tr><td>{r['id']}</td><td>{html.escape(r['key'])}</td><td>{r['status']}{link}</td><td>{html.escape(r['title'] or '')}</td>"
                     f"<td>{html.escape((r['review_reason'] or r['error'] or ''))[:200]}</td><td>{btn}</td></tr>")
        h.append("</table>")
        rej = c.execute("SELECT ts,key,reason FROM rejections ORDER BY id DESC LIMIT 15").fetchall()
        h.append(f"<h2>Rejected candidates ({c.execute('select count(*) from rejections').fetchone()[0]})</h2><table>")
        h += [f"<tr><td>{r['ts']}</td><td>{html.escape(r['key'] or '')}</td><td>{html.escape(r['reason'])}</td></tr>" for r in rej]
        h.append("</table><h2>Quota & storage</h2>")
        used = YouTubePublisher(pipe.cfg, db).quota_used_today()
        du = shutil.disk_usage(pipe.out_root)
        h.append(f"<p>YouTube quota used today (local count): {used}/10000 units. Output dir free space: {du.free // 2**30} GiB.</p>")
        h.append("<h2>Zero-cost / environment audit</h2><table>")
        h += [f"<tr><td class={x['status']}>{x['status']}</td><td>{x['name']}</td><td>{html.escape(x['detail'])}</td></tr>" for x in run_audit(pipe.cfg)["checks"]]
        h.append("</table><h2>Recent log</h2><table>")
        h += [f"<tr><td>{r['ts']}</td><td>{r['level']}</td><td>{html.escape(r['msg'][:300])}</td></tr>" for r in c.execute("SELECT * FROM event_log ORDER BY id DESC LIMIT 20")]
        h.append("</table>")
        return "".join(h)

    @app.post("/approve/<int:i>")
    def approve(i): pipe.approve(i); return redirect("/")
    @app.post("/skip/<int:i>")
    def skip(i): pipe.skip(i); return redirect("/")
    @app.post("/rerender/<int:i>")
    def rerender(i): pipe.render_item(i); return redirect("/")
    @app.post("/pause")
    def pause(): db.put_setting("paused", "0" if db.setting("paused") == "1" else "1"); return redirect("/")
    return app
