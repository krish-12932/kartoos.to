#!/usr/bin/env python3
"""Cloudflare detection + wait. Code kartoons_auto.py wala AS-IS hai.

NOTE: is file me kuch change mat karna jab tak cloudflare fix
test na ho jaye — ye tested working code hai.
"""
import time


def challenge_visible(page) -> bool:
    try:
        body = (page.content() or "")[:6000].lower()
        title = (page.title() or "").lower()
    except Exception:
        return True
    return ("are you a human" in body or "verify you are human" in body
            or "verification widget failed" in body or "just a moment" in title)


def cf_checkbox_manual_wait(page, timeout=120) -> bool:
    """Login form ke andar wala Turnstile checkbox: auto-tick, warna manual wait."""
    try:
        for frame in page.frames:
            try:
                url = (frame.url or "").lower()
            except Exception:
                continue
            if "challenges.cloudflare.com" not in url and "turnstile" not in url:
                continue
            try:
                box = frame.locator("input[type='checkbox'], iframe").first
                box.click(timeout=5000, force=True)
                print("[login] checkbox par auto-click kiya.")
                page.wait_for_timeout(4000)
            except Exception:
                pass
    except Exception:
        pass
    try:
        _checked = cf_checked
    except Exception:
        _checked = None
    if _checked and _checked(page):
        print("[login] checkbox tick ho gaya.")
        return True
    print("[login] checkbox khud TICK karo (max %ds), main auto-detect karunga..." % timeout)
    waited = 0
    while waited < timeout:
        try:
            if _checked and _checked(page):
                print("[login] tick detect hua.")
                return True
        except Exception:
            pass
        page.wait_for_timeout(3000)
        waited += 3
    print("[login] checkbox tick nahi hua, waise hi try kar raha hun...")
    return False


def home_ready(page) -> bool:
    """Home page aa gaya? (search icon + Trending/Login me se kuch)."""
    try:
        html = (page.content() or "").lower()
    except Exception:
        return False
    if "are you a human" in html or "verify you are human" in html:
        return False
    try:
        if page.locator("a[href*='search'], button:has-text('Search'), input[type='search']").first.is_visible(timeout=1500):
            return True
    except Exception:
        pass
    return ("trending now" in html or "kartoons app" in html or "watch now" in html)


def cf_checked(page) -> bool:
    """Cloudflare Turnstile checkbox tick ho gaya? (iframe ke andar check)."""
    try:
        for frame in page.frames:
            try:
                url = (frame.url or "").lower()
            except Exception:
                continue
            if "challenges.cloudflare.com" not in url and "turnstile" not in url:
                continue
            for sel in ["input[type='checkbox']:checked", "[aria-checked='true']",
                        ".cb-lb-checked", "[data-state='checked']"]:
                try:
                    if frame.locator(sel).first.is_visible(timeout=800):
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


def wait_cloudflare(page, timeout=30) -> None:
    """Challenge page aaye to auto-tick, warna manual tick ka wait. Search box mile to return."""
    if challenge_visible(page):
        print("[*] Cloudflare check (max %ds)..." % timeout)
        try:
            for frame in page.frames:
                try:
                    url = (frame.url or "").lower()
                except Exception:
                    continue
                if "challenges.cloudflare.com" not in url and "turnstile" not in url:
                    continue
                try:
                    frame.locator("input[type='checkbox'], iframe").first.click(timeout=4000, force=True)
                    print("[*] checkbox par auto-click kiya.")
                except Exception:
                    pass
        except Exception:
            pass
        waited = 0
        while waited < timeout:
            try:
                if cf_checked(page) and not challenge_visible(page):
                    print("[*] tick ho gaya, aage badh raha hun...")
                    return
            except Exception:
                pass
            try:
                if not challenge_visible(page):
                    print("[*] challenge clear.")
                    return
            except Exception:
                pass
            page.wait_for_timeout(3000)
            waited += 3
        print("[*] auto-tick nahi hua.")
        try:
            page.screenshot(path=str(__import__("pathlib").Path(__file__).resolve().parent.parent / "debug_search.png"))
        except Exception:
            pass
        print("    Browser me checkbox TICK karo. Tick karte hi main KHUD aage badhunga.")
        waited = 0
        while True:
            try:
                if cf_checked(page):
                    print("    tick detect hua, aage badh raha hun...")
                    page.wait_for_timeout(4000)
                    return
            except Exception:
                pass
            try:
                if not challenge_visible(page):
                    print("    challenge clear, aage badh raha hun...")
                    return
            except Exception:
                pass
            try:
                if page.locator("input[type='search'], input[name*='search' i], input[placeholder*='earch' i]").first.is_visible(timeout=1500):
                    print("    search box mil gaya, aage badh raha hun...")
                    return
            except Exception:
                pass
            page.wait_for_timeout(3000)
            waited += 3
            if waited % 30 == 0:
                print("    ... abhi bhi tick ka wait (%ds)" % waited)
