#!/usr/bin/env python3
"""Login module: .env credentials se Kartoons.to login + session check.

Flow:
  1. logged_in()? -> True to kuch mat karo (cookie/profile yaad hai)
  2. Warna /login kholo, Username + Password bharo, checkbox tick, Sign In
  3. SUCCESS to home_ready() True
"""
import pathlib

from modules.config import (
    KARTOONS_EMAIL, KARTOONS_PASSWORD, HOME_URL, LOGIN_URL_CANDIDATES,
)
from modules.cloudflare import (
    challenge_visible, home_ready, cf_checked, cf_checkbox_manual_wait,
)


def logged_in(page) -> bool:
    # Avatar render hone me time lagta hai — 2 baar check karo (total ~8s).
    for _ in range(2):
        page.wait_for_timeout(4000)  # avatar render hone do
        try:
            html = (page.content() or "").lower()
        except Exception:
            continue
        for sel in ["button:has-text('Logout')", "button:has-text('Log out')",
                    "a:has-text('Logout')", "a:has-text('Log out')",
                    "button:has-text('My List')", "a:has-text('My List')",
                    "img[alt*='avatar' i]", "[class*='avatar' i]",
                    "img[src*='avatar']"]:
            try:
                if page.locator(sel).first.is_visible(timeout=2000):
                    return True
            except Exception:
                continue
    return False


def _attempt_login(page, cb_timeout=120) -> bool:
    """Ek baar login try karo (page already kisi URL pe hai). Success -> True."""
    login_url = None
    if not challenge_visible(page):
        try:
            body = (page.content() or "").lower()
            if "sign in" in body or "log in" in body:
                for sel in ["a[href*='login' i]", "a[href*='signin' i]",
                            "button:has-text('Sign In')", "button:has-text('Log in')"]:
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=3000):
                            href = el.get_attribute("href") or ""
                            if href.startswith("/"):
                                login_url = "https://kartoons.to" + href
                            elif href.startswith("http"):
                                login_url = href
                            if login_url:
                                break
                    except Exception:
                        continue
        except Exception:
            pass
    if not login_url:
        login_url = LOGIN_URL_CANDIDATES[0]
    print("[login] login page khol raha hun: %s" % login_url)
    try:
        page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
    except Exception:
        pass
    page.wait_for_timeout(4000)
    try:
        page.screenshot(path=str(pathlib.Path(__file__).resolve().parent.parent / "debug_login.png"))
    except Exception:
        pass

    email_sel = ("input[name*='user' i], input[name*='email' i], input[name*='login' i], "
                 "input[type='email'], input[placeholder*='mail' i], "
                 "input[placeholder*='sername' i], input[type='text']")
    pass_sel = "input[type='password']"
    try:
        page.locator(email_sel).first.wait_for(state="visible", timeout=15000)
        page.locator(pass_sel).first.wait_for(state="visible", timeout=15000)
    except Exception:
        print("[login] form fields nahi mile. debug_login.png dekho.")
        return False
    try:
        email_box = page.locator(email_sel).first
        email_box.click(timeout=5000)
        email_box.fill("", timeout=5000)
        page.wait_for_timeout(500)
        email_box.fill(KARTOONS_EMAIL, timeout=10000)
        page.wait_for_timeout(500)
        pass_box = page.locator(pass_sel).first
        pass_box.click(timeout=5000)
        pass_box.fill(KARTOONS_PASSWORD, timeout=10000)
        page.wait_for_timeout(800)
        filled = (email_box.input_value() or "")
        if KARTOONS_EMAIL not in filled:
            print("[login] email fill verify fail (mila: '%s')." % filled[:40])
            return False
        print("[login] email+password bhara. checkbox check kar raha hun...")
    except Exception as e:
        print("[login] fill error:", str(e)[:150])
        return False

    cf_checkbox_manual_wait(page, timeout=cb_timeout)
    try:
        btn = page.locator(
            "button:has-text('Sign In'), button:has-text('Log in'), "
            "button[type='submit'], input[type='submit']").first
        btn.click(timeout=8000)
        print("[login] Sign In dabya, result ka wait...")
    except Exception as e:
        print("[login] submit error:", str(e)[:150])
        return False
    page.wait_for_timeout(6000)
    if logged_in(page):
        print("[login] SUCCESS — logged in, challenge skip ho gaya.")
        return True
    try:
        if not challenge_visible(page) and home_ready(page):
            print("[login] form submit ho gaya, challenge nahi dikha.")
            return True
    except Exception:
        pass
    print("[login] login confirm nahi hua. debug_login.png dekho.")
    return False


def try_auto_login(page) -> bool:
    """.env credentials se login. Success -> True.

    Cloudflare Turnstile headless server pe aksar PEHLI baar fail hota hai,
    DOOSRI baar pass. Isliye 2 attempt karte hain (har attempt naye login
    page + fresh challenge ke saath)."""
    if not KARTOONS_EMAIL or not KARTOONS_PASSWORD:
        return False
    # NOTE: HOME app.py khol chuka hai — yahan dobara goto nahi (double login msg fix).
    page.wait_for_timeout(2000)
    if logged_in(page):
        print("[login] pehle se logged in ho.")
        return True
    from modules.config import UNATTENDED
    cb_timeout = 30 if UNATTENDED else 120   # server pe koi human tick nahi karega
    for attempt in (1, 2):
        print("[login] attempt %d/2 (stealth mode)..." % attempt)
        if _attempt_login(page, cb_timeout):
            return True
        if attempt == 1:
            print("[login] attempt 1 fail — dobara try kar raha hun (Turnstile 2nd baar aksar pass)...")
            page.wait_for_timeout(3000)
    return False
