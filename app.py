#!/usr/bin/env python3
"""MAIN FILE — app.py: anime naam + episode likho, download database me payo.

Flow:
  [0] login    -> modules/login.py      (.env se auto-login, cookie yaad)
  [1] search   -> modules/search.py     (anime dhoondo, pehla result kholo)
  [2] episode  -> modules/episode.py    (episode kholo + mute/4x play)
  [3] capture  -> modules/capture.py    (segment URLs pakdo, scraper system)
  [4] download -> modules/download.py   (parts -> ffmpeg join -> .mp4)

Output: C:/Users/hp/database/anime/<Title>/Episode_<N>/Episode_<N>.mp4

Usage:
  python app.py
"""
from playwright.sync_api import sync_playwright

from modules.config import (
    KARTOONS_EMAIL, KARTOONS_PASSWORD, mask_email,
    GEMINI_API_KEY, AI_VISION_ON,
    UNATTENDED, HTML_DUMP_ON, AUTO_FIND,
    make_db_paths, save_info_json,
)
from modules.browser import launch_real_chrome, connect_cdp, close_all
from modules.login import logged_in, try_auto_login
from modules.search import search_and_open
from modules.episode import open_episode, start_player
from modules.capture import init_capture, watch_and_collect
from modules.download import download_segments

try:
    from modules.html_dump import save_html as _save_html
except Exception:
    def _save_html(page, name):
        return ""

try:
    from modules.unattended import input_with_timeout
except Exception:
    def input_with_timeout(prompt, timeout=None):
        try:
            return input(prompt)
        except Exception:
            return ""


def _dump(page, name: str):
    if not HTML_DUMP_ON:
        return ""
    try:
        return _save_html(page, name)
    except Exception:
        return ""


def run_pipeline(title, season, ep, progress=None):
    """Programmatic pipeline — CLI aur Telegram bot dono isi ko use karenge.

    progress(stage, msg): optional callback — bot status edit ke liye.
    Stages: info | login | search | episode | capture | download | done | error
    Return: {"ok": bool, "video": str, "folder": str, "segs": int, "error": str|None}
    """
    def p(stage, msg=""):
        if msg:
            print(msg)
        if progress is not None:
            try:
                progress(stage, msg)
            except Exception:
                pass  # bot callback fail ho to pipeline na ruke

    ep_full = "S%sE%s" % (season, ep)
    folder, video = make_db_paths(title, ep_full)
    p("info", "Target: Season %s Episode %s" % (season, ep))
    p("info", "Database folder: %s" % folder)
    p("info", "Output file: %s" % video)
    if KARTOONS_EMAIL and KARTOONS_PASSWORD:
        p("info", "Login: .env me mila (%s) — challenge aaya to auto-login hoga."
          % mask_email(KARTOONS_EMAIL))
    else:
        p("info", "Login: .env me nahi mila — sirf manual tick hoga. (.env.example dekho)")
    if AI_VISION_ON and GEMINI_API_KEY:
        p("info", "AI vision: ON (Gemini fallback — search-result + season/episode select).")
    elif AI_VISION_ON:
        p("info", "AI vision: key nahi mili (.env me GEMINI_API_KEY dalo) — sirf HTML chalega.")
    else:
        p("info", "AI vision: OFF — sirf HTML chalega.")
    if UNATTENDED:
        p("info", "UNATTENDED=1: input() par nahi atkegi. Galat S/E hua to")
        p("info", "  html_dumps/ + screenshot chhod ke clean exit (galat download NAHI).")
    if AUTO_FIND:
        p("info", "AUTO_FIND=1: (Season, Ep) site par na mile to overall EP number maan ke")
        p("info", "  sahi Season/Episode khud dhoondhunga (jaise EP100 = S2 ka episode).")
    if HTML_DUMP_ON:
        p("info", "HTML dump: ON (har page ke baad html_dumps/ me save hoga).")

    result = {"ok": False, "video": str(video), "folder": str(folder),
              "segs": 0, "error": None}

    proc = launch_real_chrome()
    if proc is None:
        p("error", "[!] Chrome launch fail.")
        result["error"] = "Chrome launch fail"
        return result
    with sync_playwright() as pw:
        browser, context, page = connect_cdp(pw)
        if page is None:
            close_all(None, proc)
            p("error", "[!] CDP connect fail.")
            result["error"] = "CDP connect fail"
            return result
        try:
            # [0] LOGIN — pehle HOME kholo, phir EK BAAR check (double message nahi)
            from modules.config import HOME_URL
            p("login", "[*] home khol raha hun...")
            try:
                page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
            p("login", "[*] login check kar raha hun...")
            ok = logged_in(page)
            if ok:
                p("login", "[*] pehle se logged in ho — login step skip.")
            else:
                p("login", "[*] logged in nahi ho, .env se login kar raha hun (ek baar)...")
                try_auto_login(page)
            # [1] SEARCH
            try:
                search_and_open(page, title)
            except RuntimeError as _se:
                # Logged-out header me search box gayab — seedha /search URL try
                from modules.search import search_direct_fallback
                if "Search box nahi mila" in str(_se) and search_direct_fallback(page, title):
                    p("login", "[*] direct /search fallback se result khul gaya (search box gayab tha).")
                else:
                    raise
            # [2] EPISODE + PLAYER (False = episode nahi khula -> exit, galat download nahi)
            # Segment listeners episode kholne se PEHLE attach (pehla segment safe)
            segs, hdrs, cstate = init_capture(page, context)
            pg = open_episode(page, ep_full)
            if not pg:
                _dump(page, "episode_abort")
                p("error", "[!] Episode step fail — exit. Galat download NAHI hui.")
                p("error", "    html_dumps/ + debug screenshots dekho, sahi Season/Episode likh ke dobara chalao.")
                result["error"] = "Episode step fail"
                return result
            page = pg
            _dump(page, "player_page")
            if not start_player(page):
                p("episode", "[!] Player khol nahi paya — 4 min tak segment ka wait karunga.")
            _dump(page, "player_started")
            # [3] CAPTURE (scraper system) — modules khud progress print karte hain
            p("capture", "")
            segs, hdrs = watch_and_collect(page, context, segs, hdrs, cstate)
            if len(segs) < 3:
                p("error", "[!] Segments nahi mile. debug screenshots dekho.")
                _dump(page, "no_segments")
                result["error"] = "Segments nahi mile"
                return result
            # [3.5] Capture ho gayi — ab browser ki zaroorat nahi (download,
            #      dedupe, concat, timeline fix sab offline chalte hain).
            #      Chrome abhi band = ~10 min resources free. finally idempotent hai.
            try:
                close_all(context, proc)
                p("capture", "[*] capture complete — Chrome band (background free).")
            except Exception:
                pass
            # [4] DOWNLOAD -> database (dedupe + concat + timeline fix andar hi)
            p("download", "")
            download_segments(segs, hdrs, folder, video)
            save_info_json(folder, video, title, ep_full, len(segs))
            p("done", "Ho gaya! Database file: %s" % video)
            result.update(ok=True, segs=len(segs), error=None)
            return result
        except KeyboardInterrupt:
            result["error"] = "Interrupted (user)"
            raise
        finally:
            try:
                close_all(context, proc)
            except Exception:
                pass


def main():
    """CLI wrapper.

    - Sirf anime naam  -> PURA series download (saare seasons, saari episodes).
    - Naam + ep number  -> khud dekhe wo ep kis season me hai, phir ussi ko download.
    """
    from modules.series import scan_series, detect_season, build_plan

    title = input("Anime name likho (jaise naruto): ").strip() or "naruto"
    ep_in = input("Episode number (khaali chhodo = poora series): ").strip()

    if not ep_in:
        # ---------- FULL SERIES ----------
        print("\n[*] Pura series scan kar raha hun: %s ..." % title)
        bounds = scan_series(title)
        if not bounds:
            print("[!] Series scan fail — show page khul nahi paya. debug screenshots dekho.")
            return
        plan = build_plan(bounds)
        total = len(plan)
        print("[*] %d episodes mile (%d seasons). Download shuru...\n"
              % (total, len(bounds)))
        done = 0
        for (s, n) in plan:
            ep_full = "S%sE%s" % (s, n)
            folder, video = make_db_paths(title, ep_full)
            if video.exists() and video.stat().st_size > 0:
                print("[skip] %s pehle se downloaded hai." % ep_full)
                continue
            done += 1
            print("\n===== [%d/%d] %s — %s =====\n" % (done, total, title, ep_full))
            r = run_pipeline(title, str(s), str(n))
            if not r.get("ok"):
                print("[!] %s fail: %s — aage badh raha hun." % (ep_full, r.get("error")))
        print("\n[done] Pura series complete: %s (%d episodes)." % (title, total))
    else:
        # ---------- SINGLE EPISODE (season auto-detect) ----------
        print("\n[*] Season detect kar raha hun (ep %s)..." % ep_in)
        bounds = scan_series(title)
        if not bounds:
            print("[!] Series scan fail — show page khul nahi paya.")
            return
        s = detect_season(bounds, ep_in)
        if s is None:
            print("[!] Ep %s kis season me hai ye nahi mila." % ep_in)
            print("    Available bounds: %s" % bounds)
            print("    Sahi episode number likho (ya season manually).")
            return
        lo, hi = bounds[s]
        print("[*] Ep %s -> Season %d me hai (cards %d..%d). Download shuru...\n"
              % (ep_in, s, lo, hi))
        run_pipeline(title, str(s), ep_in)


if __name__ == "__main__":
    main()
