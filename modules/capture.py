#!/usr/bin/env python3
"""Capture: /segment/ URLs pakdo — player start hone se PEHLE attach.

init_capture() listeners turant lagata hai (video chalu hone se pehle)
taaki episode ka pehla segment bhi miss na ho. Phir watch_and_collect()
tab tak URLs jama karta hai jab tak 60s tak kuch naya na aaye (khatam).
"""
import re
import time

from modules.config import SPEED, QUIET_SECONDS


def is_ok_url(url: str) -> bool:
    if not url or len(url) < 60:
        return False
    if re.search(r"[\x00-\x1f\x7f-\x9f]", url):
        return False
    if not re.match(r"^[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+$", url):
        return False
    low = url.lower()
    if any(x in low for x in [".png", ".jpg", ".css", ".js", ".woff", ".ico", "sprite"]):
        return False
    return True


def init_capture(page, context):
    """Segment listeners abhi attach karo (video start hone se PEHLE).
    Returns (segments, headers, state) — state ko watch_and_collect ko do."""
    segments, headers, seen = [], {}, set()
    state = {"last_new": time.time(), "hook": None}

    def add_url(u, hdrs):
        if not u or "/segment/" not in u or not is_ok_url(u):
            return
        if u in seen:
            return
        seen.add(u)
        segments.append(u)
        if hdrs and not headers:
            headers.update({k: v for k, v in hdrs.items()
                            if k.lower() not in (":authority", ":method", ":path",
                                                 ":scheme", "content-length")})
        state["last_new"] = time.time()
        if len(segments) % 5 == 0 or len(segments) <= 3:
            print("[SEGMENTS] %d mile. Pehla: %s" % (len(segments), segments[0][:80]))

    def on_response(resp):
        try:
            add_url(resp.url, resp.request.headers if resp.request else {})
        except Exception:
            pass

    def on_request(req):
        try:
            add_url(req.url, req.headers)
        except Exception:
            pass

    def attach(pg):
        try:
            pg.on("response", on_response)
            pg.on("request", on_request)
        except Exception:
            pass

    def hook():
        try:
            pages = list(context.pages)
        except Exception:
            pages = [page]
        for pg in pages:
            attach(pg)

    attach(page)
    hook()
    state["hook"] = hook
    return segments, headers, state


def _find_video(page, context):
    """Video kis page par chal rahi hai? -> (page, state) ya (None, None)."""
    try:
        pages = list(context.pages)
    except Exception:
        pages = [page]
    for pg in pages:
        try:
            st = pg.evaluate(
                "() => { const v = document.querySelector('video'); "
                "return v ? ({paused: v.paused, rate: v.playbackRate, "
                "muted: v.muted, ended: v.ended, dur: Math.floor(v.duration || 0), "
                "t: Math.floor(v.currentTime)}) : null; }")
            if st:
                return pg, st
        except Exception:
            continue
    return None, None


def watch_and_collect(page, context, segments=None, headers=None, state=None):
    """Video ko chalne do aur /segment/ URLs jama karo.

    init_capture() pehle call kiya ho to uske (segments, headers, state)
    yahan pass kar do — wahi list aage badhegi (pehla segment safe rahega).
    Returns (segments, headers).
    """
    if segments is None or state is None:
        segments, headers, state = init_capture(page, context)
    print("[4] Live capture %sx (video mute par chal rahi hai)..." % SPEED)
    waited = 0
    last_t = -1
    while True:
        page.wait_for_timeout(5000)
        waited += 5
        try:
            state["hook"]()
        except Exception:
            pass
        # mute + 4x har tick dobara enforce (site reset kar de to bhi laga rahe)
        try:
            from modules.episode import enforce_player
            enforce_player(page, quiet=True)
        except Exception:
            pass
        vp, st = _find_video(page, context)
        cur_t = int((st or {}).get("t") or 0)
        # Video END / LOOP detect -> episode ka data poora mil chuka hai
        if st and len(segments) >= 20:
            if st.get("ended") or (last_t > 5 and cur_t + 5 < last_t):
                print("[4] Video end/loop detect (t %d -> %d, segs=%d) — capture complete."
                      % (last_t, cur_t, len(segments)))
                break
        if st:
            last_t = cur_t
        if waited % 15 == 0:
            print("[player %ds] %s | segs=%d" % (waited, st, len(segments)))
        if st and st.get("paused") and vp is not None:
            try:
                vp.evaluate(
                    "() => { const v = document.querySelector('video');"
                    " if (v) v.play().catch(function(){}); }")
            except Exception:
                pass
        if segments and (time.time() - state["last_new"]) > QUIET_SECONDS:
            print("[4] %ds se naya segment nahi — episode khatam." % QUIET_SECONDS)
            break
        if not segments and waited >= 240:
            print("[4] 4 min me koi segment nahi aaya — player start nahi hua. Stop.")
            break
        if waited >= 1800:
            print("[4] 30 min ho gaye, jo mila usi se download.")
            break
    print("[4] Total valid segments: %d" % len(segments))
    return segments, headers
