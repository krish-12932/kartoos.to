#!/usr/bin/env python3
"""Episode module: episode kholo + player start (mute + 4x).

PROVEN (html_dumps + episode page se, naruto-68186):
  - Card:  <div role="button" aria-label="View Season 1 Episode 25: Title!">
           (label me TITLE SUFFIX hota hai -> exact match isliye fail hota tha)
  - Play:  <button aria-label="Play Season 1 Episode 25">  (is label me suffix nahi)
  - Grid sirf ~30 cards render karta hai, lekin Season 1 me 52 episodes hain
    -> target ke liye NEECHE SCROLL karke load karna padta hai
  - Scroll ke baad purane cards DOM se GAYAB bhi ho sakte hain (windowing)
    -> isliye find: pehle mounted cards -> phir TOP se step-step scroll,
    jahan target mount ho wahan TURANT click (aur click fail ho to reason print)
  - Site ki EPISODE NUMBERING OVERALL hai: S1 cards "Episode 1..52",
    S2 cards "Episode 53..104" (S2 ka pehla card hi "Episode 53" likha hai!)
    -> isliye har season ke liye (min, max) bounds padhte hain, phir remap
  - Card click -> /show/.../episode/<id> detail page -> wahan "Continue"
    button (play icon) -> player chalu -> /segment/ URLs (capture.py pakadta hai)
  - Agar (Season, Ep) site par na ho to episode number ko OVERALL maan ke
    sahi season + us season ka sahi card label khud dhoondhte hain (AUTO_FIND).
"""
import re
import pathlib

from modules.cloudflare import wait_cloudflare
from modules.config import (
    SPEED, GEMINI_API_KEY, AI_VISION_ON, HTML_DUMP_ON,
    UNATTENDED, MANUAL_WAIT_SECS, AUTO_FIND,
)
from modules.ai_vision import ai_click

try:
    from modules.html_dump import save_html
except Exception:
    def save_html(page, name):
        return ""

try:
    from modules.unattended import input_with_timeout, wait_episode_opened
except Exception:
    def input_with_timeout(prompt, timeout=None):
        try:
            return input(prompt)
        except Exception:
            return ""

    def wait_episode_opened(page, timeout=None):
        return False


def _dump(page, name: str):
    if not HTML_DUMP_ON:
        return ""
    try:
        return save_html(page, name)
    except Exception:
        return ""


# JS: page ke saare "Season S Episode E" aria-labels se per-season MAX nikaalo.
_JS_SEASON_MAX = (
    "() => { const out = {};"
    " document.querySelectorAll('[aria-label]').forEach(function (e) {"
    "   const t = e.getAttribute('aria-label') || '';"
    "   const m = t.match(/Season\\s*(\\d+)\\s*Episode\\s*(\\d+)/i);"
    "   if (m) { const s = String(parseInt(m[1], 10)); const n = parseInt(m[2], 10);"
    "     if (!out[s] || n > out[s]) out[s] = n; }"
    " }); return out; }"
)


def _season_max(page, season) -> int:
    """DOM me abhi is season ke liye max episode number kitna render hai?"""
    try:
        data = page.evaluate(_JS_SEASON_MAX) or {}
        return int(data.get(str(season), 0))
    except Exception:
        return 0


def _video_exists(page) -> bool:
    """Is page ya context ke kisi bhi page par video tag hai?"""
    try:
        pages = list(page.context.pages)
    except Exception:
        pages = [page]
    for pg in pages:
        if _page_has_video(pg):
            return True
    return False


def load_all_episodes(page, season, rounds: int = 25) -> int:
    """Grid lazy render karta hai — neeche scroll karte raho jab tak
    'Season S Episode N' ke naye cards na aayen. Return: max N jo mila."""
    best, stable = 0, 0
    for _ in range(rounds):
        cur = _season_max(page, season)
        if cur > best:
            best, stable = cur, 0
        else:
            stable += 1
        if stable >= 3:
            break
        try:
            cards = page.locator(
                "div[aria-label^='View Season'], button[aria-label^='Play Season']")
            n = cards.count()
            if n:
                try:
                    cards.nth(n - 1).hover(timeout=1200)
                except Exception:
                    pass
                cards.nth(n - 1).scroll_into_view_if_needed(timeout=2500)
        except Exception:
            pass
        try:
            page.mouse.wheel(0, 2500)
        except Exception:
            pass
        try:
            page.evaluate(
                "() => { const ds = Array.from(document.querySelectorAll('div'));"
                " const c = ds.find(d => d.scrollHeight > d.clientHeight + 300 &&"
                " d.querySelector(\"div[aria-label^='View Season']\"));"
                " if (c) { c.scrollTop = c.scrollHeight; }"
                " window.scrollTo(0, document.body.scrollHeight); return 1; }")
        except Exception:
            pass
        page.wait_for_timeout(1100)
    return best


def list_seasons(page) -> list:
    """Show page par kaun-kaun se seasons hain -> ['1','2','3','4'].

    Site ab season ko <button> ke bajaye div-dropdown me rakhta hai
    (div.sc-fxgerm "Season 1..4"), isliye dono scan hote hain.
    """
    found = []
    try:
        for el in page.locator("button").all()[:60]:
            try:
                t = (el.inner_text() or "").strip()
            except Exception:
                continue
            m = re.match(r"(?i)^season\s*(\d+)$", t)
            if m:
                s = m.group(1).lstrip("0") or "0"
                if s not in found:
                    found.append(s)
    except Exception:
        pass
    try:
        for el in page.locator("div").all()[:400]:
            try:
                t = (el.inner_text() or "").strip()
            except Exception:
                continue
            if len(t) > 20:
                continue
            m = re.match(r"(?i)^season\s*(\d+)$", t)
            if m:
                s = m.group(1).lstrip("0") or "0"
                if s not in found:
                    found.append(s)
    except Exception:
        pass
    try:
        return sorted(found, key=int)
    except Exception:
        return found


def select_season(page, season) -> bool:
    """'Season N' select karo + grid load hone ka wait.

    Pehle purane <button> wale selectors, phir site ke naye div-dropdown
    (season-dropdown -> div "Season N"). Naye flow me pehle dropdown ka
    header (span/div "Season X") click karke list kholni padti hai.
    """
    s = str(season).lstrip("0") or "0"
    for sel in ["button:text-is('Season %s')" % s,
                "button:has-text('Season %s')" % s]:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible(timeout=3500):
                btn.scroll_into_view_if_needed(timeout=3500)
                page.wait_for_timeout(400)
                btn.click(timeout=5000)
                page.wait_for_timeout(2500)
                print("    [ep] Season %s select kiya." % s)
                return True
        except Exception:
            continue
    # Naya dropdown: option divs (site ab button nahi deta)
    for sel in ["div:text-is('Season %s')" % s,
                "span:text-is('Season %s')" % s,
                "div:has-text('Season %s')" % s]:
        try:
            opt = page.locator(sel).first
            if opt.count() > 0:
                try:
                    if opt.is_visible(timeout=2500):
                        opt.scroll_into_view_if_needed(timeout=2500)
                        page.wait_for_timeout(300)
                        opt.click(timeout=5000)
                        page.wait_for_timeout(2500)
                        print("    [ep] Season %s select kiya (dropdown)." % s)
                        return True
                except Exception:
                    pass
                # Option DOM me hai par list band hai -> pehle dropdown kholo
                try:
                    for hsel in ["div.season-dropdown", "div[class*='season-dropdown']"]:
                        hdr = page.locator(hsel).first
                        if hdr.count() > 0 and hdr.is_visible(timeout=2500):
                            hdr.scroll_into_view_if_needed(timeout=2500)
                            hdr.click(timeout=5000)
                            page.wait_for_timeout(1200)
                            break
                except Exception:
                    pass
                try:
                    if opt.is_visible(timeout=2500):
                        opt.click(timeout=5000)
                        page.wait_for_timeout(2500)
                        print("    [ep] Season %s select kiya (dropdown kholke)." % s)
                        return True
                except Exception:
                    pass
        except Exception:
            continue
    print("    [ep] ⚠️ Season %s ka button nahi mila (page par: %s)."
          % (s, list_seasons(page) or "?"))
    return False


def _iter_pages_frames(page):
    """Context ke saare pages + unke saare nested frames (recursive)."""
    out = []
    try:
        pages = list(page.context.pages)
    except Exception:
        pages = [page]
    for pg in pages:
        out.append(pg)
        try:
            stack = list(pg.frames)
            while stack:
                f = stack.pop()
                out.append(f)
                try:
                    stack.extend(f.child_frames)
                except Exception:
                    pass
        except Exception:
            pass
    return out


_ENFORCE_JS = (
    "(arg) => { const sp = arg[0], rw = arg[1];"
    " const vs = Array.from(document.querySelectorAll('video'));"
    " for (const v of vs) {"
    "   try {"
    "     if (rw && v.currentTime > 5) { try { v.currentTime = 0; } catch (e) {} }"
    "     v.muted = true; v.volume = 0; v.playbackRate = sp;"
    "     try {"
    "       Object.defineProperty(v, 'playbackRate', { get: () => sp,"
    "         set: () => {}, configurable: true });"
    "       Object.defineProperty(v, 'muted', { get: () => true,"
    "         set: () => {}, configurable: true });"
    "       Object.defineProperty(v, 'volume', { get: () => 0,"
    "         set: () => {}, configurable: true });"
    "     } catch (e) {}"
    "     const p = v.play(); if (p && p.catch) p.catch(function(){});"
    "   } catch (e) {}"
    " }"
    " if (!vs.length) return null;"
    " return {n: vs.length, rate: vs[0].playbackRate, muted: vs[0].muted,"
    "   paused: vs[0].paused, t: Math.floor(vs[0].currentTime)}; }"
)


def enforce_player(page, quiet=True, rewind=False) -> int:
    """Har page/frame ke SAARE video elements: muted + volume 0 + SPEEDx.
    Site ka player khud reset kar de to bhi ye dobara lagta hai (aur
    property lock lag jata hai taaki site 1x par wapas na kar sake).
    Return: kitne video elements mile."""
    found = 0
    samples = []
    for obj in _iter_pages_frames(page):
        try:
            st = obj.evaluate(_ENFORCE_JS, [SPEED, bool(rewind)])
        except Exception:
            continue
        if st:
            found += int(st.get("n") or 0)
            samples.append(st)
    if found and not quiet:
        print("    [player] enforce: %d video(s) %s" % (found, samples[:2]))
    return found


def _page_has_video(pg) -> bool:
    """Is page par (ya uske kisi frame me) video tag hai?"""
    try:
        if pg.evaluate("() => !!document.querySelector('video')"):
            return True
    except Exception:
        pass
    try:
        for f in pg.frames:
            try:
                if f.evaluate("() => !!document.querySelector('video')"):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _find_episode_page(page):
    """Context ke kis page par episode/player khula hai? -> page | None.
    (Site player ko NAYE TAB me kholti hai aur purana tab band kar deti hai,
    isliye sirf apne page par bharosa nahi — poore context me dhoondhte hain.)"""
    try:
        pages = list(page.context.pages)
    except Exception:
        pages = [page]
    for pg in pages:
        try:
            u = pg.url or ""
        except Exception:
            continue
        if ("/episode/" in u) or ("/watch" in u) or ("workers.dev" in u):
            return pg
    for pg in pages:
        if _page_has_video(pg):
            return pg
    return None


def _alive_page(page):
    """page zinda hai? nahi to context ka koi zinda page lo."""
    try:
        if page is not None and not page.is_closed():
            return page
    except Exception:
        pass
    try:
        for pg in page.context.pages:
            try:
                if not pg.is_closed():
                    return pg
            except Exception:
                continue
    except Exception:
        pass
    return None


def _wait_opened(page, secs: float = 5):
    """Episode/player khul gaya? -> us page ka handle | None.
    (Naya tab khul jaye ya purana tab band ho jaye — dono handle.)"""
    for _ in range(max(1, int(secs * 2))):
        pg = _find_episode_page(page)
        if pg:
            print("    [ep] ✅ Episode/player khul gaya (%s)."
                  % ((getattr(pg, "url", "") or "")[:70] or "video mila"))
            return pg
        try:
            page.wait_for_timeout(500)
        except Exception:
            page = _alive_page(page)
            if page is None:
                break
            try:
                page.wait_for_timeout(500)
            except Exception:
                break
    try:
        urls = [(getattr(p, "url", "") or "")[:60] for p in page.context.pages]
        print("    [ep] (wait: %ss tak kuch nahi khula — open tabs: %s)" % (secs, urls))
    except Exception:
        pass
    return None


def _js_click_lookup(page, season, epnum):
    """JS se DOM me target card dhoondo AUR usi waqt click karo — Playwright
    ke visibility/stability checks bypass (isliye koi timeout nahi hota).
    Return: clicked label | 'not-found' | 'error'."""
    js = (
        "([S, E]) => {"
        " const rx = new RegExp('^(play|view)\\\\s+season\\\\s*' + S +"
        "   '\\\\s*episode\\\\s*' + E + '\\\\s*(?:[:\\\\-\\\\u2014].*)?$', 'i');"
        " const vis = e => { const r = e.getBoundingClientRect();"
        "   return (r.width > 0 && r.height > 0) ? 0 : 1; };"
        " const hits = Array.from(document.querySelectorAll('[aria-label]'))"
        "   .filter(e => rx.test(e.getAttribute('aria-label') || ''));"
        " if (!hits.length) return 'not-found';"
        " hits.sort((a, b) => {"
        "   const pa = /^play/i.test(a.getAttribute('aria-label')) ? 0 : 1;"
        "   const pb = /^play/i.test(b.getAttribute('aria-label')) ? 0 : 1;"
        "   return vis(a) - vis(b) || pa - pb; });"
        " const el = hits[0];"
        " try { el.scrollIntoView({block: 'center'}); } catch (e) {}"
        " el.click();"
        " return el.getAttribute('aria-label') || 'clicked'; }"
    )
    try:
        return page.evaluate(js, [str(season), str(epnum)]) or "not-found"
    except Exception as e:
        print("    [ep] js-click error: %s" % str(e)[:90])
        return "error"


def _click_and_verify(page, el, tag: str = "") -> bool:
    """Element click karo (3 tarike: normal -> force -> JS dispatch),
    phir check karo episode/player khula ya nahi. Har fail ka REASON print
    hota hai — silent fail nahi (debugging ke liye)."""
    clicked_with, problems = None, []
    for mode in ("normal", "force", "dispatch"):
        try:
            if mode == "normal":
                el.scroll_into_view_if_needed(timeout=1500)
                page.wait_for_timeout(250)
                el.click(timeout=4000)
            elif mode == "force":
                el.click(timeout=4000, force=True)
            else:
                el.dispatch_event("click")
            clicked_with = mode
            break
        except Exception as e:
            problems.append("%s:%s" % (mode, str(e).splitlines()[0][:90]))
    if clicked_with is None:
        print("    [ep] ⚠️ click nahi hua%s — %s"
              % ((" (" + tag + ")") if tag else "", " | ".join(problems)))
        return False
    for _ in range(10):          # 5s tak poll (SPA nav / naya tab — dono)
        pg = _find_episode_page(page)
        if pg:
            print("    [ep] ✅ Episode khul gaya (%s, %s click)."
                  % ((getattr(pg, "url", "") or "")[:70], clicked_with))
            return True
        try:
            page.wait_for_timeout(500)
        except Exception:
            try:
                page = _alive_page(page) or page
            except Exception:
                pass
            try:
                page.wait_for_timeout(500)
            except Exception:
                pass
    print("    [ep] click hua (%s) par kuch khula nahi — agla tareeka..." % clicked_with)
    return False


def _find_target_els(page, season, epnum):
    """Abhi MOUNTED target card ke elements -> [(kind, locator), ...].
    kind: 'play' (chhota play button) ya 'view' (poora card). Play pehle."""
    out = []
    try:
        els = page.locator("[aria-label]").all()
    except Exception:
        els = []
    rx = re.compile(
        r"(?i)^\s*(play|view)\s+season\s*%s\s*episode\s*%s\s*(?:[:\-—].*)?$"
        % (season, epnum))
    for e in els:
        try:
            lb = e.get_attribute("aria-label") or ""
        except Exception:
            continue
        m = rx.match(lb)
        if m:
            out.append(("play" if m.group(1).lower() == "play" else "view", e))
    out.sort(key=lambda kv: 0 if kv[0] == "play" else 1)
    return out


def _grid_scroll_top(page):
    """Grid ko wapas TOP par le jao (pehle wale episodes dobara mount hote hain)."""
    try:
        page.evaluate(
            "() => { const ds = Array.from(document.querySelectorAll('div'));"
            " const c = ds.find(d => d.scrollHeight > d.clientHeight + 300 &&"
            " d.querySelector(\"div[aria-label^='View Season']\"));"
            " if (c) c.scrollTop = 0; window.scrollTo(0, 0); return 1; }")
    except Exception:
        pass
    page.wait_for_timeout(700)


def _grid_scroll_step(page, px=1500):
    """Grid ko thoda neeche scroll karo (naye cards mount hote hain)."""
    try:
        page.evaluate(
            "(px) => { const ds = Array.from(document.querySelectorAll('div'));"
            " const c = ds.find(d => d.scrollHeight > d.clientHeight + 300 &&"
            " d.querySelector(\"div[aria-label^='View Season']\"));"
            " if (c) c.scrollTop += px; window.scrollBy(0, px); return 1; }", px)
    except Exception:
        pass
    try:
        page.mouse.wheel(0, px)
    except Exception:
        pass
    page.wait_for_timeout(650)


def _try_click_found(page, season, epnum, tag):
    """Abhi jo target mounted hai use click karo: pehle JS click (fast,
    koi timeout nahi), phir Playwright fallback.
    Return: episode/player page handle | None."""
    lb = _js_click_lookup(page, season, epnum)
    if lb not in ("not-found", "all-skipped", "error"):
        print("    [ep] JS click >> %s" % lb[:70])
        pg = _wait_opened(page, 6)
        if pg:
            print("    [ep] (card: js — %s)" % tag)
            return pg
    try:
        cands = _find_target_els(page, season, epnum)
    except Exception:
        cands = []
    for kind, el in cands:
        try:
            if _click_and_verify(page, el, kind):
                print("    [ep] (card: %s — %s)" % (kind, tag))
                return _wait_opened(page, 3) or _alive_page(page)
        except Exception as e:
            print("    [ep] click try fail: %s" % str(e)[:90])
    return None


def find_and_click_episode(page, season, epnum, load: bool = True):
    """Target episode card dhoondo aur click karo.
    Return: episode/player PAGE handle (naya tab ho sakta hai!) | None."""
    # 0. Kya player pehle se khula hai (page switch / naya tab)?
    pg = _find_episode_page(page)
    if pg and (("/episode/" in (getattr(pg, "url", "") or ""))
               or _page_has_video(pg)):
        print("    [ep] (player page pehle se khula hua hai)")
        return pg
    # 1. Abhi jo mounted hai — chhote episodes (EP1..30) turant mil jate hain
    pg = _try_click_found(page, season, epnum, "mounted")
    if pg:
        return pg
    # 2. Poora grid max tak render karao (dead page kabhi crash na kare)
    if load:
        try:
            mx = load_all_episodes(page, season)
            print("    [ep] Season %s: max Episode %d tak cards load hue." % (season, mx))
        except Exception as e:
            print("    [ep] load skip (%s)" % str(e)[:60])
    # 3. TOP se step-by-step neeche — jahan target mile, click
    _grid_scroll_top(page)
    fails = 0
    for step in range(30):
        pg = _find_episode_page(page)
        if pg and _page_has_video(pg):
            print("    [ep] (player mil gaya — scroll step %d)" % step)
            return pg
        if _find_target_els(page, season, epnum):
            pg = _try_click_found(page, season, epnum, "scroll step %d" % step)
            if pg:
                return pg
            fails += 1
            if fails >= 2:
                print("    [ep] card mil gaya par click nahi chala — AI/manual par chhod raha hun.")
                return None
        _grid_scroll_step(page)
    print("    [ep] target card scroll karke bhi nahi mila (S%s E%s)."
          % (season, epnum))
    return None


def season_bounds(page, pick=None) -> dict:
    """Har season select karke scroll-load karo -> {s: (min_label, max_label)}.

    Naruto par site ki numbering OVERALL hai: S1 = "Episode 1..52",
    S2 = "Episode 53..104" — isliye min AUR max dono chahiye.

    pick=(season, epnum) do to EARLY-STOP: jis season me wo episode aa jaye,
    wahan tak hi scan hota hai (S3/S4 ka wait nahi — seedha target par jao).
    """
    js = (
        "() => { const out = {};"
        " document.querySelectorAll('[aria-label]').forEach(function (e) {"
        "   const t = e.getAttribute('aria-label') || '';"
        "   const m = t.match(/Season\\s*(\\d+)\\s*Episode\\s*(\\d+)/i);"
        "   if (m) { const s = String(parseInt(m[1], 10)); const n = parseInt(m[2], 10);"
        "     if (!out[s]) out[s] = { mn: n, mx: n };"
        "     else { if (n < out[s].mn) out[s].mn = n; if (n > out[s].mx) out[s].mx = n; } }"
        " }); return out; }"
    )
    bounds = {}
    seasons = list_seasons(page) or ["1"]
    try:
        seasons = sorted(seasons, key=lambda x: int(x))
    except Exception:
        pass
    ps = pe = None
    if pick:
        try:
            ps, pe = int(pick[0]), int(pick[1])
        except Exception:
            ps = pe = None
    cum, fixed = 0, None
    for s in seasons:
        select_season(page, s)
        load_all_episodes(page, s)
        try:
            data = page.evaluate(js) or {}
        except Exception:
            data = {}
        item = data.get(str(s))
        if item:
            lo, hi = int(item.get("mn", 0)), int(item.get("mx", 0))
            bounds[int(s)] = (lo, hi)
            if fixed is None and ps is not None and int(s) == ps:
                fixed = cum + pe          # picked (S,E) ka overall episode number
            cum += hi - lo + 1
            print("    [ep] Season %s: Episode %s..%s (%d cards)."
                  % (s, lo, hi, hi - lo + 1))
        else:
            print("    [ep] Season %s: koi episode card nahi mila." % s)
        if fixed is not None and cum >= fixed:
            print("    [ep] (✅ early-stop: target EP%s Season %s me hai — "
                  "aage scan nahi kiya)" % (fixed, s))
            break
    return bounds


def remap_overall(bounds, season, epnum):
    """(S,E) site par nahi mila -> E ko us season ka LOCAL number maano,
    overall ("kitva episode hai") nikaalo, phir sahi season + us season ka
    SAHI CARD LABEL return karo. Return (season, card_label, overall) ya None.

    bounds: {1: (1, 52), 2: (53, 104), ...} — site ke actual card labels se.
    Formula dono numbering schemes par chalta hai:
      overall = (season se pehle ke total cards) + e
      card    = season ke pehle card ka label + (us season me index - 1)
    """
    try:
        s, e = int(season), int(epnum)
    except Exception:
        return None
    if not bounds or e < 1 or s < 1:
        return None
    sizes = {k: (hi - lo + 1) for k, (lo, hi) in bounds.items() if hi >= lo}
    if not sizes:
        return None
    overall = sum(v for k, v in sizes.items() if k < s) + e
    if overall > sum(sizes.values()):
        return None
    acc = 0
    for k in sorted(sizes):
        if overall <= acc + sizes[k]:
            label = bounds[k][0] + (overall - acc) - 1
            return (k, label, overall)
        acc += sizes[k]
    return None


def open_episode(page, ep: str, auto_season: bool = True):
    """[2] Episode kholo. Return: episode/player PAGE (naya tab ho sakta
    hai) ya None (fail).

    Steps:
      1. Season select (page ke 'Season 1..4' buttons)
      2. Target card scroll karke load -> Play button / View card click
      3. Nahi mila -> AUTO_FIND: overall EP number maan ke sahi S/E dhoondo
      4. Phir bhi nahi -> AI vision (agar GEMINI_API_KEY hai)
      5. Sab fail -> manual/unattended wait
    """
    print("[2] Episode %s khol raha hun..." % ep)
    page = _alive_page(page)
    if page is None:
        print("    [ep] ❌ koi zinda page nahi mila.")
        return None
    page.wait_for_timeout(2000)
    epn = str(ep).strip()
    m = re.match(r"(?i)^(?:s(\d+))?e?(\d+)$", epn.replace(" ", ""))
    season = str(int(m.group(1))) if (m and m.group(1)) else "1"
    epnum = str(int(m.group(2))) if (m and m.group(2)) else epn
    print("    [ep] target: Season %s Episode %s" % (season, epnum))

    wait_cloudflare(page, timeout=30)
    _dump(page, "show_page")

    seasons = list_seasons(page)
    if seasons:
        print("    [ep] page par seasons: %s" % ", ".join("S%s" % s for s in seasons))
        select_season(page, season)

    # 1. Seedha target dhoondo (scroll se poora grid load karke)
    pg = find_and_click_episode(page, season, epnum)
    if pg:
        print("[2] ✅ Episode khul gaya (S%s E%s)." % (season, epnum))
        return pg

    # 2. AUTO_FIND: overall number maan ke remap
    if AUTO_FIND and auto_season:
        print("    [ep] S%s E%s direct nahi mila — har season ke cards gino..."
              % (season, epnum))
        bounds = season_bounds(page, (season, epnum))
        got = remap_overall(bounds, season, epnum)
        if got:
            s2, e2, overall = got
            print("    [ep] ℹ️ Overall EP%s = Season %s, site par card 'Episode %s'."
                  % (overall, s2, e2))
            select_season(page, str(s2))
            pg = find_and_click_episode(page, str(s2), str(e2))
            if pg:
                print("[2] ✅ Episode khul gaya (remap: S%s E%s)." % (s2, e2))
                return pg
        else:
            print("    [ep] ❌ EP%s kisi bhi season me nahi mila (bounds: %s)."
                  % (epnum, bounds))

    # 3. HTML fail -> AI vision (manual wait se PEHLE, taaki UNATTENDED me bhi try ho)
    if AI_VISION_ON and GEMINI_API_KEY:
        try:
            ok = ai_click(
                page,
                "the play button on the episode card for Season %s Episode %s "
                "(small round play triangle in the episode list)" % (season, epnum),
                label="S%s E%s play" % (season, epnum))
            if ok:
                page.wait_for_timeout(3500)
                pg = _wait_opened(page, 6) or _alive_page(page)
                print("[2] ✅ AI se episode khola (S%s E%s)." % (season, epnum))
                return pg
        except Exception as e:
            print("    [ai] fail: %s" % str(e)[:100])

    # 4. Manual / unattended (sabse aakhir)
    print("[2] Episode button auto nahi mila — browser me KHUD episode kholo,")
    if UNATTENDED:
        _dump(page, "episode_not_found")
        try:
            page.screenshot(path=str(pathlib.Path(__file__).resolve().parent.parent
                                     / "debug_episode.png"))
        except Exception:
            pass
        if wait_episode_opened(page, timeout=MANUAL_WAIT_SECS):
            return _wait_opened(page, 5) or _alive_page(page)
        print("[2] ❌ episode nahi khula (timeout %ds). Galat download NAHI hogi."
              % MANUAL_WAIT_SECS)
        print("    html_dumps/latest_show_page.html + debug_episode.png dekho.")
        return None
    print("    khul jaye to terminal me Enter dabao, main aage badhunga.")
    answered = input_with_timeout("    >>> Episode kholke Enter dabao: ",
                                  timeout=MANUAL_WAIT_SECS)
    if answered == "":
        # timeout — shayad user khud khol chuka ho, page poll karo
        if wait_episode_opened(page, timeout=60):
            return _wait_opened(page, 5) or _alive_page(page)
    return _wait_opened(page, 3) or _alive_page(page)


def _page_with_video(page):
    """Context ke kis page par video hai? -> page ya None."""
    try:
        pages = list(page.context.pages)
    except Exception:
        pages = [page]
    for pg in pages:
        if _page_has_video(pg):
            return pg
    return None


def start_player(page) -> bool:
    """[3] Episode detail page -> 'Continue' (play icon) dabao -> video aaye
    to mute + 4x karo. Return True = video mil gaya."""
    page = _alive_page(page)
    if page is None:
        print("[3] ❌ koi zinda page nahi mila.")
        return False
    print("[3] Player start (mute + %sx)..." % SPEED)
    wait_cloudflare(page, timeout=30)

    vp = _page_with_video(page)
    if vp is None:
        # Episode detail ka bada play button: <button><svg data-icon=play>Continue</button>
        for sel in ["button:has-text('Continue')",
                    "button:has-text('Play Now')",
                    "button:has-text('Watch Now')",
                    "button:has(svg[data-icon='play'])",
                    "button:has-text('Play')"]:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=3000):
                    el.scroll_into_view_if_needed(timeout=2500)
                    page.wait_for_timeout(300)
                    el.click(timeout=5000)
                    print("    [3] player button dabya: %s" % sel)
                    page.wait_for_timeout(2500)
                    break
            except Exception:
                continue

    # video ka wait (player naye tab me khula ho to wahan bhi check hoga)
    vp = None
    for i in range(30):
        vp = _page_with_video(page)
        if vp:
            break
        if i == 6:
            print("    [3] video ka wait... (player load ho raha hai)")
        page.wait_for_timeout(1500)
    if vp is None:
        print("    [3] ❌ video tag nahi mila — player nahi khula.")
        try:
            page.screenshot(path=str(pathlib.Path(__file__).resolve().parent.parent
                                     / "debug_player.png"))
        except Exception:
            pass
        return False

    # mute + 4x — SAARE videos par (har page + nested frames bhi), aur
    # thodi der tak lagatar (site khud reset kar deti hai to bhi lagta rahe)
    n = 0
    for i in range(8):
        n = enforce_player(page, quiet=(i > 0), rewind=True)
        if n:
            break
        page.wait_for_timeout(1500)
    if n:
        print("    [3] mute + %sx lagaya (%d video element par)." % (SPEED, n))
    else:
        print("    [3] ⚠️ video element nahi mila — capture phir bhi chalega.")
    # Browser-level audio mute (extra guarantee — page ke saare audio band)
    try:
        for pg in list(page.context.pages):
            try:
                cdp = page.context.new_cdp_session(pg)
                cdp.send("Page.setAudioMuted", {"muted": True})
            except Exception:
                continue
        print("    [3] browser-level audio mute ON.")
    except Exception:
        pass
    page.wait_for_timeout(1000)
    return True
