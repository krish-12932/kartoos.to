#!/usr/bin/env python3
"""CI queue runner — GitHub Actions cron ke liye NON-INTERACTIVE wrapper.

app.py me KUCH change nahi karta, sirf uske existing functions reuse karta hai:
  - app._load_queue()  -> queue.txt parse
  - app.run_pipeline() -> single episode download
  - modules.series.scan_series/build_plan/detect_season

Kyun alag file? Kyunki app.py Mode 2 me input() maangta hai
("Shuru karu? y/n") jo cron me atak jayega. Ye file bina input ke chalti hai.

Env (workflow se aate hain, Secrets me daalo):
  KARTOONS_EMAIL, KARTOONS_PASSWORD, GEMINI_API_KEY (optional)
  UNATTENDED=1 (must — warna input par atkegi)
  QUEUE_MAX_EPS=4        (ek run me max kitne episodes — 6h limit se bachne ke liye)
  QUEUE_TIMEOUT_MIN=300  (itne min baad naya episode start nahi hoga)

Exit code: 0 = kam se kam 1 ok/skip, 1 = sab fail / koi kaam nahi.
"""
import os
import sys
import time
import pathlib

BASE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

# UNATTENDED force — cron me input() matlab hang = 6h waste.
os.environ.setdefault("UNATTENDED", "1")

from app import _load_queue, run_pipeline  # noqa: E402
from modules.series import scan_series, detect_season, build_plan  # noqa: E402
from modules.config import make_db_paths  # noqa: E402


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return default


def main():
    max_eps = _env_int("QUEUE_MAX_EPS", 4)
    timeout_min = _env_int("QUEUE_TIMEOUT_MIN", 300)
    deadline = time.time() + timeout_min * 60

    jobs, qpath = _load_queue("queue.txt")
    if not jobs:
        print("[ci-queue] queue.txt me koi kaam nahi. File me naam likho.")
        print("Format: 'naruto' (full) | 'naruto 100' (single) | 'bleach 1 16' (specific)")
        return 1

    print("[ci-queue] %d kaam mile (%s). max_eps=%d timeout=%dmin" % (len(jobs), qpath, max_eps, timeout_min))
    ok = fail = skip = 0
    done_eps = 0

    for ji, job in enumerate(jobs, 1):
        if done_eps >= max_eps:
            print("[ci-queue] max_eps limit (%d) — baaki agle run me." % max_eps)
            break
        if time.time() >= deadline:
            print("[ci-queue] timeout (%dmin) — baaki agle run me." % timeout_min)
            break
        print("\n===== [ci-queue %d/%d] %s =====" % (ji, len(jobs), job))

        try:
            if job["kind"] == "full":
                title = job["title"]
                bounds = scan_series(title)
                if not bounds:
                    print("[ci-queue] scan fail: %s" % title)
                    fail += 1
                    continue
                plan = build_plan(bounds)
                for (s, n) in plan:
                    if done_eps >= max_eps:
                        break
                    if time.time() >= deadline:
                        break
                    ep_full = "S%sE%s" % (s, n)
                    _, video = make_db_paths(title, ep_full)
                    if video.exists() and video.stat().st_size > 0:
                        print("[skip] %s %s pehle se hai." % (title, ep_full))
                        skip += 1
                        continue
                    print("\n----- %s — %s -----" % (title, ep_full))
                    r = run_pipeline(title, str(s), str(n))
                    done_eps += 1
                    if r.get("ok"):
                        ok += 1
                    else:
                        fail += 1
                        print("[!] %s fail: %s — aage." % (ep_full, r.get("error")))
            elif job["kind"] == "single":
                title, ep_in = job["title"], job["ep"]
                bounds = scan_series(title)
                if not bounds:
                    print("[ci-queue] scan fail: %s" % title)
                    fail += 1
                    continue
                s = detect_season(bounds, ep_in)
                if s is None:
                    print("[!] Ep %s season me nahi mila. bounds=%s" % (ep_in, bounds))
                    fail += 1
                    continue
                print("[*] Ep %s -> Season %d. Download..." % (ep_in, s))
                r = run_pipeline(title, str(s), str(ep_in))
                done_eps += 1
                if r.get("ok"):
                    ok += 1
                else:
                    fail += 1
            else:
                title, s, n = job["title"], job["season"], job["ep"]
                ep_full = "S%sE%s" % (s, n)
                _, video = make_db_paths(title, ep_full)
                if video.exists() and video.stat().st_size > 0:
                    print("[skip] %s %s pehle se hai." % (title, ep_full))
                    skip += 1
                    continue
                r = run_pipeline(title, str(s), str(n))
                done_eps += 1
                if r.get("ok"):
                    ok += 1
                else:
                    fail += 1
        except KeyboardInterrupt:
            print("\n[ci-queue] interrupted.")
            break
        except Exception as e:
            print("[ci-queue] job crash: %s" % str(e)[:200])
            fail += 1

    print("\n[ci-queue done] ok=%d fail=%d skip=%d (is run me %d episodes try)" % (ok, fail, skip, done_eps))
    return 0 if (ok > 0 or skip > 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
