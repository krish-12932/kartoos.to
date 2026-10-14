#!/usr/bin/env python3
"""Shared config: .env, paths, constants, database helpers.

Yahi single jagah hai jahan .env load hota hai aur database
path banta hai: C:/Users/hp/database/anime/<Title>/Episode_<N>/
"""
import os
import re
import json
import time
import pathlib

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=pathlib.Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass  # python-dotenv na ho to env vars se kaam chalega

KARTOONS_EMAIL = os.getenv("KARTOONS_EMAIL", "").strip()
KARTOONS_PASSWORD = os.getenv("KARTOONS_PASSWORD", "").strip()

# AI vision (Gemini) — sirf fallback: search-result select + season/episode select.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
AI_VISION_ON = os.getenv("AI_VISION", "1").strip() not in ("0", "no", "off", "")

# UNATTENDED MODE: 1 karo to script kabhi input() par nahi atkegi.
# Chhod ke chale jao to galat input par wahin rukne ke bajaye
# html_dumps/ me HTML + screenshot chhod ke clean exit karegi.
UNATTENDED = os.getenv("UNATTENDED", "0").strip() not in ("0", "no", "off", "")
# Har page ke baad HTML save karna hai? (html_dumps/ folder me)
HTML_DUMP_ON = os.getenv("HTML_DUMP", "1").strip() not in ("0", "no", "off", "")
# Manual wait kitne sec baad auto-fail ho (unattended me): default 5 min
MANUAL_WAIT_SECS = int(os.getenv("MANUAL_WAIT_SECS", "300") or "300")

# AUTO_FIND=1: (Season, Ep) site par na mile to episode number ko OVERALL
# number maan ke sahi Season/Episode khud dhoondta hai (jaise EP100 S2 me).
# 0 karo to sirf bataega, khud aage nahi badhega.
AUTO_FIND = os.getenv("AUTO_FIND", "1").strip() not in ("0", "no", "off", "")

HOME_URL = "https://kartoons.to/home"
LOGIN_URL_CANDIDATES = ["https://kartoons.to/login"]

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "profile"

def _find_chrome():
    """Windows + Linux (Render) dono ke liye Chrome dhoondho.
    Pehle CHROME_PATH env var, phir common install paths."""
    env = os.getenv("CHROME_PATH", "").strip()
    if env and pathlib.Path(env).exists():
        return env
    for c in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/opt/google/chrome/chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ):
        if pathlib.Path(c).exists():
            return c
    return ""


CHROME_PATH = _find_chrome()
CDP_URL = "http://localhost:9222"

# Database root — Windows pe purana fixed path, Linux (Render) pe project ke
# andar (send ke baad delete hota hai isliye ephemeral disk kaafi hai).
# Zaroorat ho to DB_ROOT env var se override karo.
_db_env = os.getenv("DB_ROOT", "").strip()
if _db_env:
    DB_ROOT = pathlib.Path(_db_env)
elif os.name == "nt":
    DB_ROOT = pathlib.Path(r"C:\Users\hp\database\anime")
else:
    DB_ROOT = BASE_DIR / "database"

SPEED = 4.0
QUIET_SECONDS = 60


def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    name, dom = email.split("@", 1)
    return (name[:2] + "***@" + dom) if len(name) > 2 else ("***@" + dom)


def safe_name(text: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", text).strip().replace(" ", "_")


def make_db_paths(title: str, ep: str):
    folder = DB_ROOT / safe_name(title) / ("Episode_%s" % safe_name(str(ep)))
    folder.mkdir(parents=True, exist_ok=True)
    video = folder / ("Episode_%s.mp4" % safe_name(str(ep)))
    return folder, video


def save_info_json(folder, video, title, ep, nseg):
    info = {
        "title": title,
        "episode": str(ep),
        "segments": nseg,
        "file": str(video),
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(folder / ("Episode_%s.json" % safe_name(str(ep))), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
