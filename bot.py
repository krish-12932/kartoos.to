#!/usr/bin/env python3
"""Telegram bot - 2 commands only. No extra deps (Bot HTTP API + polling)."""
import os, re, time, json, queue, shutil, threading, pathlib
import urllib.parse, urllib.request
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=pathlib.Path(__file__).resolve().parent / ".env")
except Exception:
    pass
from app import run_pipeline
from modules.series import detect_season
BASE = pathlib.Path(__file__).resolve().parent
TOKEN = os.getenv("BOT_TOKEN", "").strip()
API = os.getenv("BOT_API_URL", "https://api.telegram.org").strip().rstrip("/") or "https://api.telegram.org"
ALLOW = {c.strip() for c in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if c.strip()}
DEL = os.getenv("DELETE_AFTER_SEND", "1").strip() not in ("0", "no", "off", "")
Q = queue.Queue()
PEND = []
LOCK = threading.Lock()
CUR = {"job": None}
CANCEL = threading.Event()
START_TS = time.time()
def health_server():
    """Render free plan ko zinda rakhne ke liye /health endpoint (stdlib only)."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    port = int(os.getenv("PORT", "10000") or "10000")
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"ok": True, "service": "kartoos-bot",
                               "uptime_sec": int(time.time() - START_TS),
                               "bot_token": bool(TOKEN),
                               "queue": Q.qsize(),
                               "paused": False}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a): pass
    try:
        HTTPServer(("0.0.0.0", port), H).serve_forever()
    except Exception as e:
        print("[health] server fail:", e)
def api(m, p=None, files=None, timeout=60):
    url = "%s/bot%s/%s" % (API, TOKEN, m)
    if files:
        b = "----b%d" % int(time.time() * 1000)
        body = b""
        for k, v in (p or {}).items():
            body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, k, v)).encode()
        for f, (fn, fb, mt) in files.items():
            body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n" % (b, f, fn, mt)).encode() + fb + b"\r\n"
        body += ("--%s--\r\n" % b).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "multipart/form-data; boundary=%s" % b})
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(p or {}).encode())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))
def send(c, t):
    try:
        return (api("sendMessage", {"chat_id": c, "text": t}).get("result") or {}).get("message_id")
    except Exception as e:
        print("[bot] send fail:", e)
        return None
def edit(c, i, t):
    try: api("editMessageText", {"chat_id": c, "message_id": i, "text": t})
    except Exception: pass
def dele(c, i):
    try: api("deleteMessage", {"chat_id": c, "message_id": i})
    except Exception: pass
def sendvid(c, vp, cap):
    try:
        d = pathlib.Path(vp).read_bytes()
        return api("sendVideo", {"chat_id": c, "caption": cap[:1024], "supports_streaming": "true"}, files={"video": (pathlib.Path(vp).name, d, "video/mp4")}, timeout=600).get("ok", False)
    except Exception as e:
        print("[bot] video fail:", e)
        return False
SE = re.compile(r"\bs(\d{1,2})\s*e(\d{1,4})\b", re.I)
NM = re.compile(r"\b(\d{1,2})\s+(\d{1,4})\b")
def parse(t):
    t = (t or "").strip()
    if not t or t.startswith("/"): return None
    if "," in t and not SE.search(t) and not NM.search(t):
        ts = [x.strip() for x in t.split(",") if x.strip()]
        return {"kind": "multi", "titles": ts, "label": ", ".join(ts)} if ts else None
    m = SE.search(t)
    if m:
        ti = (t[:m.start()] + " " + t[m.end():]).strip(" ,-")
        return {"kind": "single", "title": ti or t, "season": m.group(1), "ep": m.group(2), "label": "%s S%sE%s" % (ti, m.group(1), m.group(2))}
    m = NM.search(t)
    if m:
        ti = (t[:m.start()] + " " + t[m.end():]).strip(" ,-")
        return {"kind": "single", "title": ti or t, "season": m.group(1), "ep": m.group(2), "label": "%s S%sE%s" % (ti, m.group(1), m.group(2))}
    m = re.search(r"\b(\d{1,4})\s*$", t)
    if m and t[:m.start()].strip(" ,-"):
        ti = t[:m.start()].strip(" ,-")
        return {"kind": "auto", "title": ti, "ep": m.group(1), "label": "%s ep %s" % (ti, m.group(1))}
    return {"kind": "full", "title": t, "label": "FULL: %s" % t}
HELP = ("Commands:\n naruto -> pura series\n naruto, bleach -> multiple\n naruto 100 -> ep (season auto)\n bleach s1 e16 / naruto 1 16 -> specific\n/queue /skip <n> /cancel")
def enq(job, cid):
    job = dict(job); job["chat_id"] = cid
    with LOCK: PEND.append(job)
    Q.put(job)
    send(cid, "➕ Queue me daala: %s (position %d)" % (job["label"], Q.qsize()))
def expand(job):
    from modules.series import scan_series, build_plan
    out = []
    if job["kind"] == "multi":
        return [dict(kind="full", title=t, label="FULL: %s" % t, chat_id=job["chat_id"]) for t in job["titles"]]
    if job["kind"] == "full":
        b = scan_series(job["title"])
        if not b: return [dict(kind="dead", label=job["label"], error="series scan fail", chat_id=job["chat_id"])]
        for (s, n) in build_plan(b):
            out.append(dict(kind="single", title=job["title"], season=str(s), ep=str(n), label="%s S%sE%s" % (job["title"], s, n), chat_id=job["chat_id"]))
        return out
    if job["kind"] == "auto":
        b = scan_series(job["title"])
        if not b: return [dict(kind="dead", label=job["label"], error="series scan fail", chat_id=job["chat_id"])]
        s = detect_season(b, job["ep"])
        if s is None: return [dict(kind="dead", label=job["label"], error="ep %s season me nahi mila %s" % (job["ep"], b), chat_id=job["chat_id"])]
        return [dict(kind="single", title=job["title"], season=str(s), ep=job["ep"], label="%s S%sE%s" % (job["title"], s, job["ep"]), chat_id=job["chat_id"])]
    return [job]
def worker():
    print("[bot] worker live.")
    while True:
        job = Q.get()
        with LOCK:
            if job in PEND: PEND.remove(job)
            CUR["job"] = job
        CANCEL.clear()
        try:
            for sj in expand(job):
                if CANCEL.is_set(): send(job["chat_id"], "🛑 Cancel: %s" % job["label"]); break
                if sj.get("kind") == "dead": send(job["chat_id"], "❌ %s - %s" % (sj["label"], sj.get("error"))); continue
                runone(sj)
        except Exception as e:
            send(job["chat_id"], "❌ Job crash: %s - %s" % (job.get("label"), e))
        finally:
            with LOCK: CUR["job"] = None
            Q.task_done()
def runone(job):
    cid = job["chat_id"]
    sid = send(cid, "🎬 %s - shuru..." % job["label"])
    ICO = {"login": "🔓", "search": "🔍", "episode": "🎬", "capture": "📥", "download": "📦"}
    def prog(st, ms):
        if sid and ms: edit(cid, sid, "%s %s\n%s" % (ICO.get(st, "⏳"), job["label"], ms[-400:]))
    r = run_pipeline(job["title"], job["season"], job["ep"], progress=prog)
    if CANCEL.is_set(): send(cid, "🛑 Cancel: %s" % job["label"]); return
    if not r.get("ok"): send(cid, "❌ %s fail: %s" % (job["label"], r.get("error"))); return
    vp = pathlib.Path(r["video"])
    try: mb = vp.stat().st_size / 1048576
    except Exception: mb = 0.0
    ok = sendvid(cid, vp, "🎬 %s - S%sE%s\n📦 %.0f MB" % (job["title"], job["season"], job["ep"], mb))
    send(cid, "✅ %s bhej diya." % job["label"] if ok else "⚠️ %s download hua, bhejne me fail (Bot API 50MB limit?). File: %s" % (job["label"], vp))
    if sid: dele(cid, sid)
    if DEL and ok:
        try:
            fo = pathlib.Path(r.get("folder") or vp.parent)
            (shutil.rmtree(fo, ignore_errors=True) if (fo.exists() and fo.is_relative_to(BASE)) else vp.unlink(missing_ok=True))
        except Exception as e: print("[bot] cleanup fail:", e)
def handle(cid, t):
    lo = t.strip().lower()
    if lo in ("/start", "/help", "help"): send(cid, "🤖 Kartoons bot live.\n" + HELP); return
    if lo == "/queue":
        with LOCK:
            ls = ["%d. %s" % (i + 1, j["label"]) for i, j in enumerate(PEND)]
            cu = CUR["job"]["label"] if CUR["job"] else "kuch nahi"
        send(cid, "📋 Chal raha: %s\n%s" % (cu, "\n".join(ls) if ls else "Queue khaali.")); return
    if lo == "/cancel":
        CANCEL.set()
        with LOCK: n = len(PEND); PEND.clear()
        while not Q.empty():
            try: Q.get_nowait(); Q.task_done()
            except Exception: break
        send(cid, "🛑 Cancel (%d pending hate)." % n); return
    if lo.startswith("/skip"):
        try: n = int(lo.split()[1]) - 1
        except Exception: send(cid, "Use: /skip 2"); return
        with LOCK:
            if 0 <= n < len(PEND):
                g = PEND.pop(n)
                try: Q.get_nowait(); Q.task_done()
                except Exception: pass
                send(cid, "⏭️ Hataya: %s" % g["label"])
            else: send(cid, "Queue me %d job." % len(PEND))
        return
    j = parse(t.strip())
    if not j: send(cid, "Samajh nahi aaya.\n" + HELP); return
    enq(j, cid)
def main():
    if not TOKEN: print("[bot] BOT_TOKEN nahi - .env me daalo."); return
    print("[bot] start | allowed=%s | del=%s" % (sorted(ALLOW) if ALLOW else ["(sab)"], DEL))
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    try: api("getUpdates", {"offset": 0, "timeout": 1})
    except Exception: pass
    off = 0
    while True:
        try:
            r = api("getUpdates", {"offset": off, "timeout": 50}, timeout=65)
            for u in r.get("result", []):
                off = u.get("update_id", off) + 1
                mg = u.get("message") or u.get("edited_message") or {}
                ch = mg.get("chat") or {}
                cid = str(ch.get("id", "")); tx = (mg.get("text") or "").strip()
                if not cid or not tx: continue
                if ALLOW and cid not in ALLOW: print("[bot] BLOCKED", cid); continue
                print("[bot] msg", cid, tx[:80])
                handle(cid, tx)
        except KeyboardInterrupt: print("\n[bot] band."); break
        except Exception as e: print("[bot] poll error:", e); time.sleep(5)
if __name__ == "__main__": main()

