#!/usr/bin/env python3
"""Unattended helpers: input() par atakna band + galat season/ep par jaldi exit.

Problem (user ne bola): galat Season/Ep likh ke chala gaya to script
input("Enter dabao...") par GHANTO atak jayegi — wapas aake dekhega
to wahi ruki hogi, download bhi nahi hua, pata bhi nahi chala kyu.

Fix:
  1. input_with_timeout(): UNATTENDED=1 ho to input() puchta hi nahi,
     turant "" deta hai. Attended mode me bhi thread-timeout hai taaki
     bhool se chhod diya to MANUAL_WAIT_SECS baad auto-aage badhe.
  2. wait_episode_opened(): episode button na mile to input() ke bajaye
     page ko poll karo — user ne khud episode khol di (video tag aaya)
     to True, timeout par HTML+screenshot chhod ke False.
"""
import threading

from modules.config import UNATTENDED, MANUAL_WAIT_SECS


def is_unattended() -> bool:
    return bool(UNATTENDED)


def input_with_timeout(prompt: str, timeout: int = None) -> str:
    """UNATTENDED me input skip. Warna timeout (default MANUAL_WAIT_SECS)."""
    if is_unattended():
        print("    [unattended] input skip (UNATTENDED=1): %s" % prompt.strip()[:80])
        return ""
    secs = timeout or MANUAL_WAIT_SECS
    out = [""]

    def _ask():
        try:
            out[0] = input(prompt)
        except Exception:
            out[0] = ""

    t = threading.Thread(target=_ask, daemon=True)
    t.start()
    t.join(timeout=secs)
    if t.is_alive():
        print("    [unattended] %ds ho gaye, input nahi aaya — auto-aage." % secs)
        return ""
    return out[0]


def wait_episode_opened(page, timeout: int = None) -> bool:
    """User ne khud episode khol di? video tag / watch URL ka wait.

    Har 5 sec me check: <video> dikha ya URL me watch/episode aaya
    to True. Timeout par False (caller HTML+screenshot save karke exit).
    """
    secs = timeout or MANUAL_WAIT_SECS
    print("    [unattended] khud episode kholo — max %ds wait karunga..." % secs)
    waited = 0
    while waited < secs:
        try:
            st = page.evaluate(
                "() => { const v = document.querySelector('video'); "
                "return v ? true : false; }")
            if st:
                print("    [unattended] video tag mila — episode khul gaya!")
                return True
        except Exception:
            pass
        try:
            url = (page.url or "").lower()
            if "/watch" in url or "/episode" in url or "/player" in url:
                print("    [unattended] URL badla (%s) — episode khul gaya!" % url[:80])
                return True
        except Exception:
            pass
        try:
            page.wait_for_timeout(5000)
        except Exception:
            import time as _t
            _t.sleep(5)
        waited += 5
        if waited % 30 == 0:
            print("    ... episode ka wait (%ds/%ds)" % (waited, secs))
    print("    [unattended] timeout — episode nahi khula.")
    return False
