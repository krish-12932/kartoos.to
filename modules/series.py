#!/usr/bin/env python3
"""Series module: pura anime scan + episode -> season auto-detect.

Do kaam:
  1. scan_series(title)  -> show page kholo, saare seasons + unke OVERALL
     episode labels padho -> {season(int): (lo, hi)}.  ({ } = fail)
  2. detect_season(bounds, ep) -> diye gaye episode number kis season me hai.
  3. build_plan(bounds)  -> full-series ke liye [(season, ep), ...] list.

Site ki episode numbering OVERALL hai (naruto: S1=1..52, S2=53..104),
isliye episode number seedha us range wale season me map hota hai.
"""
from playwright.sync_api import sync_playwright

from modules.config import HOME_URL
from modules.browser import launch_real_chrome, connect_cdp, close_all
from modules.login import logged_in, try_auto_login
from modules.search import search_and_open, search_direct_fallback
from modules.episode import season_bounds


def _open_show_page(page, title):
    """login + search -> show page khula hua page return karo."""
    from modules.cloudflare import wait_cloudflare
    from modules.episode import list_seasons
    try:
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
    except Exception:
        pass
    page.wait_for_timeout(3000)
    if not logged_in(page):
        print("[series] logged in nahi — auto-login...")
        try_auto_login(page)
    try:
        search_and_open(page, title)
    except RuntimeError as _se:
        if "Search box nahi mila" in str(_se) and search_direct_fallback(page, title):
            pass
        else:
            raise
    # Show page ka season dropdown JS se render hota hai — usko load hone
    # ka wait karo, warna season_bounds -> select_season "button nahi mila"
    # bol ke fail hota hai (yahi scan fail ho raha tha).
    wait_cloudflare(page, timeout=30)
    page.wait_for_timeout(3000)
    for _ in range(15):
        try:
            if list_seasons(page):
                break
        except Exception:
            pass
        page.wait_for_timeout(1000)
    return page


def scan_series(title):
    """Show page kholo, saare seasons + episode bounds padho.
    Return: {season(int): (lo, hi)} — overall card labels. {} = fail."""
    print("[series] scan: %s" % title)
    proc = launch_real_chrome()
    if proc is None:
        return {}
    bounds = {}
    try:
        with sync_playwright() as pw:
            browser, context, page = connect_cdp(pw)
            if page is None:
                return {}
            try:
                _open_show_page(page, title)
                bounds = season_bounds(page)
            finally:
                close_all(context, proc)
    except Exception as e:
        print("[series] scan fail: %s" % str(e)[:150])
        try:
            close_all(None, proc)
        except Exception:
            pass
    if bounds:
        total = sum(hi - lo + 1 for lo, hi in bounds.values())
        print("[series] %d seasons, total %d episodes." % (len(bounds), total))
    else:
        print("[series] koi season/episode nahi mila.")
    return bounds


def detect_season(bounds, ep_num):
    """Episode number kis season me hai? (overall numbering).
    Return season(int) ya None."""
    try:
        n = int(str(ep_num).strip())
    except Exception:
        return None
    for s in sorted(bounds):
        lo, hi = bounds[s]
        if lo <= n <= hi:
            return s
    return None


def build_plan(bounds):
    """Full series -> [(season, ep), ...] overall order me."""
    plan = []
    for s in sorted(bounds):
        lo, hi = bounds[s]
        for n in range(lo, hi + 1):
            plan.append((s, n))
    return plan
