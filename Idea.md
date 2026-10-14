# Idea for automatic verfying the data which ep available in hindi or not
> > basically jo script hogi vo raat ko run krgi, and uska teen kam hoga 
> > 1. ki vo kartoons ki ep fetch kragi command and ep dena pur.
> > 2. vo database me ja kr dekhagi ki konsa ep uploaded ha aur konsa nhi.
> > 3. vo online search kragi ki ya ep hindi ha ya nhi and kya ya anime hindi ha ya nhi
> > 4. raat ko chale, morning me list de ki kaunsa ep bacha hai (anime name, season, etc.)

---

# v2 — IMPROVED PLAN (final)

## Pillar 1: Catalog Sync (point 1 ka upgrade)
- Kartoons se har anime ka **poora episode manifest** scrape: `naruto → S1(1-52), S2(53-104)...`
- Site ka total count + naya season aaya to detect
- Cache: har raat nahi, sirf 1x/week ya pehli baar (server bandwidth bacha)

## Pillar 2: DB Quality Audit (point 2 ka upgrade)
Sirf "file hai/nahi" nahi — **file sahi hai bhi ya nahi**:
- MP4 + JSON dono exist?
- Duration expected ke paas? (4 min ki file = adhoori ❌)
- Gaps 0 hain? (timeline check)
- Verdict: ✅ Uploaded / ⚠️ Re-download needed / ❌ Missing

## Pillar 3: Hindi/Dub Check — 3 reliable sources (order se)
1. **Site ka apna tag** (dual-audio/language) — sabse pakka
2. **AniList API** — `dualAudio` tag, free public API
3. **Manual list** — tumhari JSON me jo likha wo final
- Har result ke saath **source + confidence**: `✅ high (site) / ⚠️ medium (anilist) / ❓ none`

## Pillar 4: Priority Queue (naya)
- Report me sirf list nahi — **"pehle ye download karo" ka top-10**
- Score: missing + Hindi confirmed + sequence continuity (jo ep aage missing hai wo pehle)

## Pillar 5: Morning Telegram Report (naya — kal wale bot se connect)
```
📊 Subah report — 6 Oct
🎯 naruto: 15/220  ❌ missing: S1E16-52  🗣️ Hindi ✅
   💡 Pehle: S1E16, E17, E18
⚠️ Re-download: doraemon S1E9 (adhoori, 4 min)
[Buttons: ⬇️ Next 10 download] [🔁 Retry failed] [📊 Weekly stats]
```
- Reply ya button dabao → seedha download start (wahi Phase 1 bot)

---

## Round-2 NEW IMPROVEMENTS (v2 me naye)

### 6. Delta report — sirf change dikhao
Har roz pura report bhejne ki zaroorat nahi. Sirf **kal se aaj kya badla**:
"➕ 2 naye download, ❌ 1 adhoori mili, 🆕 site par naya season aaya"
Pura status sirf tum poochho ya Sunday ko.

### 7. Auto-repair (flag nahi, khud fix)
⚠️ wali file mili to sirf batana nahi — **khud redownload queue me daalo**
(subah report me: "1 adhoori mili → dobara download queue me hai")

### 8. Hole detection (sequence gap)
Beech ki missing episode alag highlight:
"naruto me E16-E18 missing hain aur tum E19+ pe ho → continuity toot gayi"
(Sequence wali download ko priority upar)

### 9. Failure evidence
Koi episode baar-baar fail ho → report me **screenshot attach** (html_dumps se)
"naruto S1E20 fail (3 baar) — reason: Cloudflare" → tumhe pata chale kya hua.

### 10. Commands (manual override)
- `/skip naruto S1E16` — ye chhodo, warna roz report me aayega
- `/done naruto S1E16` — maine khud download ki, maan lo
- `/check naruto` — turant audit (raat ka wait mat karo)
- `/hindi bleach yes` — manual Hindi list me add

### 11. Weekly digest (Sunday)
"Is hafte: 12 episode, 4.1 GB, 98% success, 2 fail (reason)"

### 12. Disk & safety guard (Render ke liye zaroori)
- Disk space check before download (Render disk chhota hai) — low ho to report
- Auto-cleanup: purane `_parts`, html_dumps >7 din, failed temp
- Rate limits: AniList politeness, Gemini budget cap, Telegram FloodWait auto

### 13. Schedule
- **Roz 2:30 AM** quick scan (catalog delta + DB audit)
- **Sunday 3:00 AM** deep scan (full catalog + Hindi re-check + weekly digest)

---

## Pipeline (raat ko)
```
[1] Catalog sync (cache se) → [2] DB quality audit → [3] Hindi check (3 source)
→ [4] Priority queue + holes → [5] Auto-repair queue chalao
→ [6] Report → Telegram (delta + buttons)
```

## Pending confirm (3 chhote sawal)
1. Hindi source: site ka HTML tag hai? (show page screenshot de do → main check)
2. Auto-download on/off? (raat me top-N khud download kare ya sirf report)
3. Report message chahiye ya .txt file? (buttons ke saath message = recommended)

---

# ⚙️ EXECUTION PLAN (v3) — review karo

## LOCKED DECISIONS (jo already confirm hai)
| # | Decision |
|---|---|
| 1 | **Local Bot API Server** (Option 1) — 2GB files, asli bot wala feel |
| 2 | **Render** hosting (paid plan $7-25/mo chahiye; free = sirf spike test) |
| 3 | **2 modes**: `ask` (permission wala) aur `auto` (full auto) — `.env` se toggle |
| 4 | Upload destination = **OPEN** (niche Open Decisions) |

---

## PHASE 0 — Spike Test (pehle, ~2 ghante, GO/NO-GO)
Kartoons + Cloudflare Render IP par chalega ya nahi — ye decide karega.
1. Minimal Dockerfile → Render free instance → `kartoons.to` kholo
2. Login cookie test + screenshot check
3. **Pass** → saare phases Render par | **Fail** → Hybrid: bot Render pe, capture tumhare PC pe (tunnel)

**Deliverable:** GO/NO-GO + screenshot

---

## PHASE 1 — Local Bot Foundation (kal)
1. `app.py` refactor → `run_pipeline(title, season, ep, progress_cb)` (input() bahar, CLI alag)
2. Local Bot API Server setup (binary + config + bot token)
3. `bot.py`: message parse (`naruto 1 16`), **single-job queue** (Chrome 1 hi chal sakta), `ALLOWED_USER_IDS` security
4. **Progress notifications** (status edit hote jaye):
   ```
   🔍 Search → 🎬 Episode mila (S2 remap) → 📥 Video capture (40/238)
   → 🧹 Duplicate remove → ✂️ Gaps fix / exact time (5-10 min)
   → 📤 Upload → ✅ Done (status delete)
   ```
5. **Cleanup (tumhari demand #2/#3):** send ke baad = status sab delete + temp folder + mp4 delete. Chat me sirf video bachegi.
6. Test: local se `naruto 1 1` → video aaye → folder khaali

**Deliverable:** Local bot working, video Telegram pe, post-send cleanup

---

## PHASE 2 — Nightly Auditor (raat wala script)
1. **Catalog sync** — poora episode manifest (cache 1x/week)
2. **DB quality audit** — exists + duration + gaps → ✅/⚠️/❌
3. **Hindi check** — site tag → AniList API → manual JSON (confidence ke saath)
4. **Priority queue + holes + delta report**
5. **Scheduler** — local: Windows Task Scheduler test → Render: Cron Jobs
6. Report → Telegram (delta + buttons: Next 10 / Retry / Stats)

**Deliverable:** Subah automated report aaye

---

## PHASE 3 — Auto-Pipeline (tumhara naya workflow) 🎯
Raat ko full chain, 2 mode:

```
[1] DB scan → missing episodes
[2] Site check → Hindi dub? (haan → aage, nahi → report me flag)
[3] Fetch → capture → dedupe → combine (EXISTING pipeline, naya kuch nahi)
[4] Mode:
    NIGHTLY_MODE=ask   → report me button: "naruto S1E16 ready — Upload? [Haan][Nahi]"
                         Haan → upload → cleanup | Nahi → skip (file DB me rehti)
    NIGHTLY_MODE=auto  → bina poochhe upload → subah summary: "➡️ 5 auto-uploaded"
    NIGHTLY_MODE=off   → sirf report (koi download nahi)
```

**Safety guards:** disk space check, max 3 retries/fail → screenshot evidence, failure items alag list

**Deliverable:** Raat ko chain chale, subah result aaye

---

## PHASE 4 — Render Deploy
1. Final `Dockerfile` (playwright chromium + ffmpeg + fonts) + `render.yaml`
2. Secrets (dashboard me, repo me nahi): kartoons login, bot token, Local API token, Gemini key, `ALLOWED_USER_IDS`
3. Cron jobs (daily 2:30 AM + Sunday deep scan)
4. Disk/persistent volume strategy (Render disk chhota hai)

**Deliverable:** Production pe live

---

## PHASE 5 — E2E + Hardening
Phone se pura flow → edge cases (FloodWait, disk full, site layout change) → monitoring/health ping

---

## Module structure (kya banega)
```
kartoons-auto/
├── app.py              (existing — refactor: run_pipeline())
├── bot.py              (NEW — Telegram commands + job queue)
├── nightly.py          (NEW — auditor + auto-pipeline)
├── modules/            (existing — as-is reuse)
├── Dockerfile, render.yaml  (NEW — Phase 4)
└── .env (secrets), .env.example
```

## `.env` flags
```
NIGHTLY_MODE=ask|auto|off        # auto-pipeline mode
NIGHTLY_TIME=02:30               # schedule
BOT_MODE=local_api               # Local Bot API Server
ALLOWED_USER_IDS=...             # security
UPLOAD_TARGET=telegram           # Open Decision 1 (niche)
```

## Risks → fallback
| Risk | Fallback |
|---|---|
| Cloudflare blocks Render IP | Hybrid (Phase 0 detect) |
| Render free kaafi nahi | Paid plan hi chahiye (confirm) |
| Local Bot API heavy file tune | Config me upload limit 2GB set |
| Site HTML change | HTML dumps + AI fallback (existing) |

## ✅ RESOLVED DECISIONS (v3.1 — FINAL)
1. **Upload = Telegram chat me video send** — bot delivery boy hai; **database me tum manually move karoge** (Render pe local DB hoti nahi, tumhari DB tumhare PC pe hai). Send ke baad bot temp+mp4 delete.
2. **Hindi check = SITE-FIRST** (kyunki site par **fan-dub** bhi hain; AniList sirf official dual-audio janta hai):
   - Order: **site tag (show + episode page)** → AniList API → manual list
   - **Episode-level check** zaroori (ek anime me alag-alag ep ka dub alag) — fan-dub yahi pakdega
   - Check **fetch se pehle** karo (waste 20-min capture na ho)
3. **Mode:** dono — `ask` + `auto`, `.env` se toggle
4. **Report = chat me message:** kya sent hua + kya nahi (har skip ka reason)

## FINAL NIGHTLY FLOW (tumhara step-by-step)
```
[1] DB scan → kaunsi episode upload/missing hai
[2] Anime-level Hindi check (SITE pehle → AniList → manual) — fan-dub included
    → Hindi nahi? → SKIP + report "Hindi nahi mili"
[3] Episode kartoons par hai? → nahi? → SKIP + report "site par nahi"
[4] Episode-page par EPISODE-level Hindi verify (fan-dub!) — FETCH SE PEHLE
    → Hindi nahi? → SKIP + report
[5] Fetch → capture → dedupe → combine (EXISTING pipeline)
[6] Mode:
    NIGHTLY_MODE=ask  → chat me: "naruto S1E16 ready — bhejun? [Haan][Nahi]"
                        Haan → video send → cleanup | Nahi → skip
    NIGHTLY_MODE=auto → seedha video send → summary "➡️ N auto-uploaded"
[7] Report (chat me): ✅ sent list + ❌ skipped list (har ek ka reason)
[8] Tum video chat se utha ke DATABASE me manually move (tumhara kaam)
```

---

# v3.2 — COMMANDS & SERIES MODE (naye update)

## Commands (bot kya samjhega) — 🔍 2 SEARCH TYPES (tumhari shart)

**Type 1 — Naam-based (single ya multi anime → FULL SERIES):**
| Command | Matlab |
|---|---|
| `naruto` | **FULL SERIES** — saare seasons, saare missing episodes ek-ek karke (S1E1 → S1E52 → S2E53...) |
| `naruto, doraemon, shinchan` | **Multi-anime queue** — pehle naruto FULL, uske baad doraemon full, phir shinchan (sequential — kyunki Chrome 1 hi) |

**Type 2 — Specific episode (ek hi episode chahiye):**
| Command | Matlab |
|---|---|
| `naruto s1 e1` | Season 1 Episode 1 (tumhara naya format) |
| `naruto 1 16` | Same cheez purane format me — **dono format accept** (case-insensitive) |

**Control commands:**
| Command | Matlab |
|---|---|
| `/queue` | Abhi queue me kya hai + progress |
| `/pause` / `/resume` | Ruko / aage badho (beech episode ke baad rukega) |
| `/skip naruto S1E20` | Ye hamesha chhod do |

## Video format (tumhari demand)
- **MP4 hi jayega** (Telegram me seedha playable)
- **Caption (video ke neeche) — NOTE: Hindi/fan-dub line NAHI (v3.3):**
  ```
  🎬 Naruto — Season 1, Episode 16 (S1E16)
  ⏱️ 23:37 | 📦 219 MB
  ```
- **Filename bhi wahi:** `Naruto_S1E16.mp4` — chat me dikh jayega
- Caption me season+ep DONO honge (jaise tumne bola)

## ⚠️ DB ACCESS problem (Render) + Solution
**Problem:** Tumhari database `C:\Users\hp\database` tumhare PC pe hai — **Render server usko access hi nahi kar sakta.**

**Solution — Bot ka APNA ledger (sent_log.json, Render persistent disk pe):**
```
pending = site ka catalog − (ledger me jo bheja) − (tumne /done jo kiya)

• Jab bot video bheje → ledger me ✅ add (auto)
• Tum manually DB me dalo → bot ko bolo: /done naruto S1E16
• Nightly scan = ledger + /done vs site catalog → missing list
• Report me dikhega: "naruto: 142 sent, 10 /done (tumhare), 68 pending"
```
Optional later: PC ki `manifest_sync.py` — tumhare PC se ek click me DB ki file-list bot ko bhej de (tab /done manual nahi chahiye). **Phase 2 ke baad.**

## ⏱️ Reality check — Full Series ka TIME
| Series | Episodes | Time (25 min/ep, nonstop) |
|---|---|---|
| naruto | 220 | **~4 din** |
| doraemon | ~25 | ~10 ghante |
| Shinchan | ~500 | ~8 din 😅 |

- Episodes **ek-ek karke turant aate jayenge** (pehli wali 25 min me, pura series nahi)
- Queue system: `/pause` se rok sakte ho, Render ka paisa bacha sakte ho
- Nightly window (sirf raat) vs 24/7 — decide karna: **full series fast chahiye to job aane par din me bhi chale**

## Multi-anime queue example
```
tum: naruto, doraemon

[1/2] 🎬 Naruto (220 eps) — S1E1 send... S1E2 send... (progress: 47/220)
      /pause → ruk gaya
      /resume → aage
[2/2] 🎬 Doraemon (25 eps) — S1E1 send...
subah report: naruto 12 sent / doraemon 8 sent / 3 skipped (Hindi nahi)
```

---

# ✅ v3.3 — FINAL LOCK (last updates)

## 1. Database = SUPABASE (upar wala "DB ACCESS problem" SOLVED ✅)
- Tumhari database **Supabase (cloud)** hai → **Render se direct padh sakta hai**, koi ledger/manfiest ki zarurat nahi!
- **Bot = READ-ONLY** (tumhari shart): sirf `SELECT`. Koi INSERT/UPDATE/DELETE **kabhi nahi**.
  - **Script me manual ep upload / write role = BILKUL nahi** (tumhari shart) — upload 100% tumhara kaam
  - Key: anon/read-only key `.env` me; RLS policy me sirf SELECT allow
- Nightly scan = Supabase query: `kaunsi episode row exist karti hai` → pending list
- Phase 2 me mujhe **table ka naam + columns** chahiye hoga (anime? season? episode? status?)

## 2. Scheduling Rule (tumhari shart)
```
pending = 50 se ZYADA  →  24/7 chalo (din-raat, jaldi khatam)
pending = 50 ya KAM    →  sirf raat ka window (2:30 AM se subah tak)
```

## 3. Caption me Hindi/fan-dub NAHI ✅ (upar format me fix kiya)
Caption = sirf `🎬 Title — S x E y` + `⏱️ duration | 📦 size`

## 4. SAB KUCH `kartoons-auto` KE ANDAR — koi extra folder NAHI (v3.4 shart) 🔒
- ~~Alag anime-bot folder~~ — **CANCEL**: sab kuch `kartoons-auto\` ke andar hi:
```
kartoons-auto\
├── app.py               (existing — run_pipeline refactor)
├── bot.py               (NEW — Telegram commands + queue)
├── nightly.py           (NEW — auditor + auto-pipeline)
├── modules/             (existing — engine, minimal change)
├── Dockerfile, render.yaml  (NEW — Phase 4)
├── .env, .env.example
```
- Existing working engine (modules/) me **bilkul minimal change** — sirf `run_pipeline()` jaisa naya function

## 5. FILE LIFECYCLE on RENDER DISK (tumhari shart)
```
Fetch → file RENDER DISK me save → combine (dedupe + concat + exact fix)
→ Telegram me SEND → Render disk se DELETE (temp + mp4 dono)
```
- Render disk = sirf **transient workspace** (job ke beech me), job ke baad khaali

## 6. Final flow (2 search types ke saath)
```
Type 1: "naruto" ya "naruto, doraemon" → full series queue (missing episodes)
Type 2: "naruto s1 e1" / "naruto 1 16" → specific episode (dono format)

Har episode:
  Supabase READ (row hai?) → site check (Hindi/fan-dub, site-first)
  → fetch → RENDER DISK save → combine → SEND (caption: S x E y + time + size)
  → RENDER DISK delete → next
```

## FINAL STATUS: ✅ Plan 100% LOCKED (v3.4)
Pehla kaam (Phase 1): `bot.py` + `run_pipeline()` + Local Bot API + queue (kartoons-auto ke andar hi)

