#!/usr/bin/env python3
"""Download: valid segments -> parts -> duplicate check -> ffmpeg concat -> single .mp4.

Site kabhi ek hi content do baar alag quality me serve karti hai
(pehla segment 480p, dobara 720p) — dono alag URL hote hain isliye
capture me filter nahi hota. Download ke baad content se check karke
duplicate part hatao, warna video me 7-8s ka repeat aa jayega.
"""
import json
import os
import pathlib
import shutil
import subprocess
import time
import urllib.request

from modules.capture import is_ok_url

_SIG_W = _SIG_H = 32          # duplicate check ke liye chhota frame size
_DUP_MAX_MAD = 3.0            # isse neeche = same content (0 = bilkul same)
_DUP_MIN_FRAMES = 5
_DUP_LEN_RATIO = 0.9          # frame count ka ratio (duration match)


def _gray_sig(path):
    """Part ka 32x32 gray signature: list of frame-byte-strings. Fail -> None."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-an",
           "-vf", "scale=%d:%d,format=gray" % (_SIG_W, _SIG_H),
           "-f", "rawvideo", "-"]
    try:
        raw = subprocess.run(cmd, capture_output=True).stdout
    except Exception:
        return None
    fsz = _SIG_W * _SIG_H
    n = len(raw) // fsz
    if n < _DUP_MIN_FRAMES:
        return None
    return [raw[i * fsz:(i + 1) * fsz] for i in range(n)]


def _is_dup(sig_a, sig_b):
    """Do signatures same content ke hain? (MAD early-abort ke saath)"""
    if not sig_a or not sig_b:
        return False
    la, lb = len(sig_a), len(sig_b)
    if min(la, lb) / float(max(la, lb)) < _DUP_LEN_RATIO:
        return False
    m = min(la, lb)
    fsz = len(sig_a[0])
    total = 0
    for k in range(m):
        for x, y in zip(sig_a[k], sig_b[k]):
            d = x - y
            total += d if d >= 0 else -d
        if k >= 9 and total / float((k + 1) * fsz) > _DUP_MAX_MAD:
            return False
    return total / float(m * fsz) <= _DUP_MAX_MAD


def _res_of(path):
    """Part ki resolution (width*height) — behtar wala duplicate rakho."""
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30).stdout
        s = json.loads(p)["streams"][0]
        return int(s.get("width", 0)) * int(s.get("height", 0))
    except Exception:
        return 0


def dedupe_parts(tmp, count):
    """Adjacent parts me content-duplicate dhundho; behtar resolution wala rakho.
    Returns kept part-index list (order me)."""
    kept = []
    prev_i, prev_sig = None, None
    for i in range(count):
        sig = _gray_sig(tmp / ("part%04d.ts" % i))
        if prev_sig is not None and sig is not None and _is_dup(prev_sig, sig):
            cur_r = _res_of(tmp / ("part%04d.ts" % i))
            if cur_r > _res_of(tmp / ("part%04d.ts" % prev_i)):
                dropped, kept_i = prev_i, i
                kept[-1] = i
                prev_i, prev_sig = i, sig
                print("    [dup] part%04d = part%04d repeat; behtar resolution wala rakha"
                      % (dropped, kept_i))
            else:
                print("    [dup] part%04d = part%04d ka repeat — drop kiya"
                      % (i, prev_i))
        else:
            kept.append(i)
            prev_i, prev_sig = i, sig
        if i and i % 50 == 0:
            print("    ... dup-check %d/%d" % (i, count))
    return kept


def _packet_pts(path, stream):
    """Stream ke saare packet PTS (sorted) — ffprobe se."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", stream,
             "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=300)
    except Exception:
        return []
    pts = []
    for tok in r.stdout.replace(",", " ").split():
        try:
            pts.append(float(tok))
        except ValueError:
            pass
    pts.sort()
    return pts


def _find_gaps(pts, thresh=0.05):
    """(last_pts, next_pts) pairs jahan bada gap hai — TS boundary dead-time."""
    out = []
    for i in range(1, len(pts)):
        d = pts[i] - pts[i - 1]
        if d > thresh:
            out.append((pts[i - 1], pts[i]))
    return out


def fix_timeline(video):
    """Har segment boundary par ~0.1s TS dead-time hatao (video+audio dono se).

    Cut points dono streams ke gap-intersection ke beech rakhe jaate hain
    (taaki koi frame/sample na kate), phir re-encode = exact content duration.
    Fail par original file safe rehti hai. Returns True if fixed.
    """
    video = pathlib.Path(video)
    vp = _packet_pts(video, "v:0")
    ap = _packet_pts(video, "a:0")
    vg = _find_gaps(vp)
    ag = _find_gaps(ap)
    if not vp or len(vg) == 0:
        print("[6.1] timeline: koi gap nahi — fix ki zarurat nahi.")
        return False
    print("[6.1] timeline: %d video gaps (%.1fs), %d audio gaps — fix shuru..."
          % (len(vg), sum(b - a for a, b in vg), len(ag)))

    n = min(len(vg), len(ag)) if ag else len(vg)
    cuts = []
    for k in range(n):
        if ag:
            lo, hi = max(vg[k][0], ag[k][0]), min(vg[k][1], ag[k][1])
        else:
            lo, hi = vg[k]
        cuts.append((lo + hi) / 2.0 if hi > lo + 0.004 else lo + 0.01)

    N = len(cuts) + 1
    starts = [0.0] + cuts
    ends = cuts + [max(vp[-1], ap[-1] if ap else vp[-1]) + 1.0]

    chains = [
        "[0:v]split=%d%s" % (N, "".join("[sv%d]" % i for i in range(N))),
        "[0:a]asplit=%d%s" % (N, "".join("[sa%d]" % i for i in range(N))),
    ]
    for i in range(N):
        chains.append("[sv%d]trim=start=%.4f:end=%.4f,setpts=PTS-STARTPTS[v%d]"
                      % (i, starts[i], ends[i], i))
        chains.append("[sa%d]atrim=start=%.4f:end=%.4f,asetpts=PTS-STARTPTS[a%d]"
                      % (i, starts[i], ends[i], i))
    chains.append("%sconcat=n=%d:v=1:a=0[vout]"
                  % ("".join("[v%d]" % i for i in range(N)), N))
    chains.append("%sconcat=n=%d:v=0:a=1[aout]"
                  % ("".join("[a%d]" % i for i in range(N)), N))

    gpath = video.parent / "_timeline_fix.txt"
    tmp_out = video.parent / ("_fixed_" + video.name)
    gpath.write_text(";\n".join(chains), encoding="ascii")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(video),
           "-filter_complex_script", str(gpath),
           "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           # 512MB plan: x264 buffers threads×frame se bante hain — cap karke
           # memory spike (OOM) roko. Quality par asar nahi (sirf speed).
           "-threads", "2",
           "-x264-params", "threads=2:lookahead-threads=1:rc-lookahead=20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", str(tmp_out)]
    print("[6.1] re-encode (exact timeline)... ~5-10 min — DHYAAN RAHE, Ctrl+C mat karna (warna fir se chalana padega)")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        ok = (r.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 0)
        if ok:
            d_new = _packet_pts(tmp_out, "v:0")
            if not d_new or len(d_new) < len(vp) * 0.99:
                ok = False
        if not ok:
            print("[6.1] timeline fix FAIL — original safe. %s"
                  % (r.stderr or "")[-300:])
            if tmp_out.exists():
                tmp_out.unlink()
            gpath.unlink(missing_ok=True)
            return False
        os.replace(str(tmp_out), str(video))
        gpath.unlink(missing_ok=True)
        return True
    except KeyboardInterrupt:
        # User ne Ctrl+C dabaya — partial temp hatao, original safe hai.
        try:
            if tmp_out.exists():
                tmp_out.unlink()
        except Exception:
            pass
        print("[6.1] interrupted — original file safe. Dobara fix_timeline chalao (re-capture nahi).")
        raise
    except Exception as e:
        print("[6.1] timeline fix error (original safe): %s" % str(e)[:120])
        if tmp_out.exists():
            tmp_out.unlink()
        return False


def concat_parts(tmp, kept, video):
    """kept parts ko list.txt se join karke final video banao."""
    with open(tmp / "list.txt", "w", encoding="utf-8") as lf:
        for i in kept:
            lf.write("file 'part%04d.ts'\n" % i)
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", str(tmp / "list.txt"), "-c", "copy", str(video)]
    print("[6] ffmpeg join...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(tmp))
    if r.returncode != 0:
        print(r.stderr[-2500:])
        raise RuntimeError("ffmpeg join fail")
    print("[SUCCESS] database me saved: %s" % video)


def download_segments(urls, headers, folder, video):
    clean = [u for u in urls if is_ok_url(u)]
    removed = len(urls) - len(clean)
    print("[5] download: %d valid parts (%d gande hataye)" % (len(clean), removed))
    print("[5] Output: %s" % video)
    if len(clean) < 3:
        raise RuntimeError("Valid segments bahut kam (%d). Video poori chali thi?" % len(clean))
    tmp = pathlib.Path(folder) / "_parts"
    tmp.mkdir(parents=True, exist_ok=True)
    base_h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
              "Referer": "https://kartoons.to/", "Origin": "https://kartoons.to"}
    base_h.update(headers or {})
    for i, u in enumerate(clean):
        out = tmp / ("part%04d.ts" % i)
        if out.exists() and out.stat().st_size > 0:
            continue
        for _ in range(3):
            try:
                req = urllib.request.Request(u, headers=base_h)
                with urllib.request.urlopen(req, timeout=60) as r, open(out, "wb") as f:
                    while True:
                        chunk = r.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                break
            except Exception as e:
                if i < 3:
                    print("    [fail] part %d: %s" % (i, str(e)[:120]))
                time.sleep(2)
        if i % 25 == 0:
            print("    ... %d/%d" % (i, len(clean)))
    print("[5.1] duplicate content check...")
    kept = dedupe_parts(tmp, len(clean))
    dropped = len(clean) - len(kept)
    if dropped:
        print("[5.1] %d duplicate part(hataye) — video me repeat nahi aayega." % dropped)
    else:
        print("[5.1] koi duplicate nahi mila.")
    concat_parts(tmp, kept, video)
    try:
        fix_timeline(video)
    except Exception as e:
        print("[6.1] timeline fix skip (original safe): %s" % str(e)[:120])
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        print("[6] _parts temp folder saaf (%d files)." % len(clean))
    except Exception as e:
        print("[6] _parts cleanup fail (safe hai): %s" % str(e)[:80])
