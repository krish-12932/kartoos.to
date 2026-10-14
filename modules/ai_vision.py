#!/usr/bin/env python3
"""AI vision fallback (Gemini): selector fail ho tabhi chalega.

Rule (user ne bola): AI sirf SEARCH ke baad kaam karega —
  1. search results me sahi title card dhoondna (neeche ho to bhi),
  2. show page par sahi season + episode dhoondna aur play karna.
Login / Cloudflare par AI NAHI chalega (waha manual + .env login hi hai).

Model output: {"x": 0-1000, "y": 0-1000} (normalized), usko viewport
pixels me badal ke mouse.click karte hain.
"""
import re
import json

from modules.config import GEMINI_API_KEY, AI_VISION_ON


def enabled() -> bool:
    return bool(AI_VISION_ON and GEMINI_API_KEY)


def _locate_xy(shot: bytes, query: str):
    """Screenshot bytes + query -> (x, y) 0-1000 me, ya None."""
    if not enabled():
        return None
    try:
        import google.generativeai as genai
        from PIL import Image
        import io as _io
    except Exception as e:
        print("    [ai] lib missing: %s" % str(e)[:100])
        return None
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-flash-latest")
        img = Image.open(_io.BytesIO(shot)).convert("RGB")
        prompt = (
            "You are a UI locator. Look at this browser screenshot. "
            "Find ONE element: %s. "
            "Return ONLY valid JSON like {\"x\": 500, \"y\": 300} "
            "with x,y as integers 0-1000 (relative to image). "
            "If not visible, return {\"x\": -1, \"y\": -1}." % query
        )
        resp = model.generate_content([prompt, img])
        txt = (getattr(resp, "text", "") or "").strip()
        m = re.search(r"\{[^}]*\}", txt)
        if not m:
            print("    [ai] samajh nahi aaya: %s" % txt[:80])
            return None
        d = json.loads(m.group(0))
        x, y = int(d.get("x", -1)), int(d.get("y", -1))
        if x < 0 or y < 0:
            print("    [ai] element dikha nahi: %s" % query[:60])
            return None
        return (x, y)
    except Exception as e:
        print("    [ai] error: %s" % str(e)[:120])
        return None


def ai_click(page, query: str, label: str = "") -> bool:
    """Screenshot lo -> AI se x,y lao -> click karo. Hua to True."""
    if not enabled():
        return False
    print("    [ai] vision: %s ..." % (label or query[:60]))
    try:
        shot = page.screenshot()
    except Exception as e:
        print("    [ai] screenshot fail: %s" % str(e)[:80])
        return False
    xy = _locate_xy(shot, query)
    if not xy:
        return False
    try:
        vp = page.viewport_size or {"width": 1280, "height": 800}
        px = xy[0] / 1000.0 * vp["width"]
        py = xy[1] / 1000.0 * vp["height"]
        page.mouse.click(px, py)
        page.wait_for_timeout(3500)
        print("    [ai] click kiya (%d,%d) -> %s" % (xy[0], xy[1], (label or "ok")))
        return True
    except Exception as e:
        print("    [ai] click fail: %s" % str(e)[:80])
        return False
