#!/usr/bin/env python3
"""Har page ke baad HTML dump: debug ke liye full page source save karo.

User demand: script har page (home / search / show / player) ke baad
uska HTML content de, taaki baad me dekha ja sake selector kyu fail hua.

Use:
    from modules.html_dump import save_html
    save_html(page, "home")  # -> html_dumps/20240101_120000_home.html

NOTE: file size badi ho sakti hai (200-500KB), isliye sirf key stages
par call karo, har 5 sec par nahi.
"""
import time
import pathlib


def _dump_dir():
    d = pathlib.Path(__file__).resolve().parent.parent / "html_dumps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_html(page, name: str) -> str:
    """Current page ka full HTML save karo. Return file path (str)."""
    try:
        html = page.content() or ""
    except Exception as e:
        print("    [html-dump] %s: content nahi mila: %s" % (name, str(e)[:80]))
        return ""
    try:
        url = page.url if hasattr(page, "url") else ""
    except Exception:
        url = ""
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)[:40]
    fname = "%s_%s.html" % (ts, safe)
    path = _dump_dir() / fname
    try:
        header = "<!-- URL: %s | saved: %s | size: %d -->\n" % (
            url, time.strftime("%Y-%m-%d %H:%M:%S"), len(html))
        path.write_text(header + html, encoding="utf-8")
        # latest_ copy taaki hamesha ek fixed naam se khul sake
        try:
            latest = _dump_dir() / ("latest_%s.html" % safe)
            latest.write_text(header + html, encoding="utf-8")
        except Exception:
            pass
        print("    [html-dump] %s -> %s (%d KB, %s)" % (
            name, path.name, len(html) // 1024, (url or "")[:70]))
        return str(path)
    except Exception as e:
        print("    [html-dump] %s save fail: %s" % (name, str(e)[:100]))
        return ""
