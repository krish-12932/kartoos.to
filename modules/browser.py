#!/usr/bin/env python3
"""Real Chrome launch + CDP connect + cleanup.

Cloudflare bot-detection se bachne ke liye Playwright ka
chromium nahi, tumhara ASLI installed Chrome use hota hai.

Render free plan = 512 MB RAM (0.1 CPU) — Chrome ko LEAN rakhna
padta hai, warna OOM (memory limit exceeded) mail aata hai:
- launch se PEHLE purana bachi hua Chrome maaro (memory leak fix)
- --no-zygote + memory-saving flags (renderers kam)
- close par poora process tree hard-kill
"""
import time
import os
import re
import shutil
import subprocess
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

from modules.config import CHROME_PATH, CDP_URL, PROFILE_DIR


def kill_stale_chrome():
    """Crash/wipe se bachi hui Chrome processes maaro (Linux container).

    Bina iske har failed job ke baad Chrome zinda reh jaata hai ->
    agle job me 2 Chrome = 512MB plan OOM.
    """
    if os.name == "nt":
        return
    try:
        subprocess.run(
            ["pkill", "-9", "-f", "user-data-dir=%s" % str(PROFILE_DIR)],
            timeout=10, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except Exception:
        pass


def _chrome_ua():
    """Installed Chrome ka ASLI User-Agent (version match).
    Headless UA ('HeadlessChrome/...') ek dead-giveaway hai — Cloudflare
    Turnstile turant bot pehchaan kar fail kar deta hai. Isliye installed
    Chrome ki version nikaal kar normal 'Chrome/XXX' UA banate hain."""
    try:
        out = subprocess.run([CHROME_PATH, "--version"], capture_output=True,
                             text=True, timeout=10).stdout or ""
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)", out)
        if m:
            return ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/%s Safari/537.36" % m.group(1))
    except Exception:
        pass
    return None


def launch_real_chrome():
    kill_stale_chrome()                    # puraana Chrome ho to pehle maaro
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    if not CHROME_PATH:
        print("[!] Chrome nahi mila — CHROME_PATH env me path do (ya install karo).")
        return None
    args = ["--remote-debugging-port=9222",
            "--user-data-dir=%s" % str(PROFILE_DIR)]
    xvfb_prefix = []
    if os.name != "nt":                      # Render / Linux container
        # lean flags — OOM aur zygote-spam se bachav
        args += ["--no-sandbox", "--no-zygote", "--disable-dev-shm-usage",
                 "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                 "--disable-extensions", "--disable-background-networking",
                 "--disable-component-update", "--disable-sync",
                 "--disable-translate", "--disable-default-apps",
                 "--metrics-recording-only", "--mute-audio",
                 "--renderer-process-limit=2",
                 "--js-flags=--max-old-space-size=128",
                 # --- anti bot-detection (Cloudflare Turnstile bachav) ---
                 "--disable-blink-features=AutomationControlled"]
        ua = _chrome_ua()
        if ua:
            args.append("--user-agent=%s" % ua)
        if os.environ.get("DISPLAY"):
            pass                            # display already hai -> headed chalao
        elif shutil.which("xvfb-run"):
            # HEADED-in-xvfb: Cloudflare headless se zyada shak karta hai.
            # xvfb virtual display -> Chrome "asli insaan" jaisa dikhta hai.
            xvfb_prefix = ["xvfb-run", "-a",
                           "--server-args=-screen 0 1920x1080x24"]
        else:
            args.append("--headless=new")   # fallback: headless + stealth
    try:
        # start_new_session=True -> Chrome apna process group banaye,
        # taaki kill se poora tree (renderers/gpu-process) saaf ho.
        proc = subprocess.Popen(xvfb_prefix + [CHROME_PATH] + args,
                                start_new_session=True)
        print("[*] Chrome launch: %s" % CHROME_PATH)
        if xvfb_prefix:
            print("[*] xvfb headed mode (stealth) — Cloudflare bypass best shot.")
        print("[*] Asli Chrome launch kiya... (CDP mode for Cloudflare Bypass)")
        # Blind sleep(3) ki jagah CDP up hone tak wait (max 30s)
        for _ in range(30):
            try:
                urlopen(CDP_URL + "/json/version", timeout=2).read(256)
                print("[*] CDP ready: %s" % CDP_URL)
                break
            except Exception:
                time.sleep(1)
        return proc
    except Exception as e:
        print("[!] Chrome launch error:", e)
        return None


def connect_cdp(pw):
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        # Stealth: automation markers chhupao (Cloudflare bot-detect bachav).
        # navigator.webdriver/plugins/languages jaisi cheezein asli browser
        # jaisi dikhao — warna Turnstile "ye bot hai" bol kar fail kar deta hai.
        try:
            context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                "Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});"
                "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
                "window.chrome={runtime:{}};"
                "Object.defineProperty(navigator,'permissions',"
                "{get:()=>({query:()=>Promise.resolve({state:'granted'})})});"
            )
        except Exception:
            pass
        page = context.pages[0] if context.pages else context.new_page()
        return browser, context, page
    except Exception as e:
        print("[!] CDP Connect error:", e)
        print("Pehle se khule hue saare Chrome band karke dobara try karein.")
        return None, None, None


def close_all(context, proc):
    try:
        if context is not None:
            context.close()
    except Exception:
        pass
    try:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except Exception:
                pass
    except Exception:
        pass
    # Bacha hua renderer/gpu-process bhi maaro — warna RAM leak -> OOM mail
    kill_stale_chrome()
    if os.name == "nt" and proc is not None:
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           timeout=10, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
