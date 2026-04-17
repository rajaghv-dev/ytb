# ytb — YouTube Transcript & Video Archiver

Two tools, shared human-pacing layer. No video-to-text conversion.
Works with Claude Code, OpenCode, Cursor, Windsurf, Aider, and any agent that reads AGENTS.md.

---

## Setup

```bash
bash setup.sh          # creates .venv, installs deps, makes scripts executable
source .venv/bin/activate
```

---

## Tool 1: `ytb.py` — Transcript downloader

Fetches YouTube's own hosted captions. No video download, no speech-to-text.

### Arguments

| Flag | Description |
|------|-------------|
| `--channel URL` | Channel URL — `@handle`, `/c/name`, or `/channel/ID` |
| `--urls URL…` | One or more specific video URLs |
| `--limit N` | Max videos from channel (default: 20) |
| `--from YYYY-MM-DD` | Only videos uploaded on or after this date |
| `--to YYYY-MM-DD` | Only videos uploaded on or before this date |
| `--lang CODE` | Preferred language code (default: `en`) |
| `--output DIR` | Output directory (default: `./transcripts`) |
| `--meta` | Also write a `.json` sidecar with metadata |
| `--no-delay` | Skip human-pacing delays |

### Output

`transcripts/YYYYMMDD_Title_videoID.txt` — header block followed by caption text.

### Examples

```bash
# Last 20 transcripts from a channel
source .venv/bin/activate && python ytb.py --channel https://www.youtube.com/@mkbhd

# Last 5
source .venv/bin/activate && python ytb.py --channel https://www.youtube.com/@mkbhd --limit 5

# Date range
source .venv/bin/activate && python ytb.py --channel https://www.youtube.com/@mkbhd \
  --from 2024-01-01 --to 2024-06-30

# Specific videos
source .venv/bin/activate && python ytb.py --urls https://youtu.be/abc123 https://youtu.be/xyz456
```

---

## Tool 2: `ytb_dl.py` — Video/audio downloader

Downloads videos for personal archiving or offline educational viewing.
Uses yt-dlp with human-paced delays and bandwidth throttling.

### Arguments

| Flag | Description |
|------|-------------|
| `--channel URL` | Channel URL — `@handle`, `/c/name`, or `/channel/ID` |
| `--urls URL…` | One or more specific video URLs |
| `--limit N` | Max videos from channel (default: 20) |
| `--from YYYY-MM-DD` | Only videos uploaded on or after this date |
| `--to YYYY-MM-DD` | Only videos uploaded on or before this date |
| `--quality PRESET` | `best`, `1080p`, `720p` *(default)*, `480p`, `360p`, `audio` |
| `--audio-only` | Extract audio only as `.m4a` (overrides `--quality`) |
| `--subs` | Embed English subtitles/captions into the file |
| `--thumbnail` | Embed video thumbnail as cover art |
| `--throttle RATE` | Bandwidth cap, e.g. `800K` or `2M` — mimics streaming |
| `--output DIR` | Output directory (default: `./videos`) |
| `--no-archive` | Disable archive log (re-download already-saved videos) |
| `--no-delay` | Skip human-pacing delays |

### Output

`videos/YYYYMMDD_Title_videoID.mp4` (or `.m4a` for audio-only).  
An archive log at `videos/.ytb_archive.txt` prevents re-downloading on re-runs.

### Examples

```bash
# Last 20 videos at 720p
source .venv/bin/activate && python ytb_dl.py --channel https://www.youtube.com/@mkbhd

# Best quality
source .venv/bin/activate && python ytb_dl.py --channel https://www.youtube.com/@mkbhd --quality best

# 1080p with subtitles and thumbnail embedded
source .venv/bin/activate && python ytb_dl.py --channel https://www.youtube.com/@mkbhd \
  --quality 1080p --subs --thumbnail

# Throttled to 800 KB/s (looks like streaming)
source .venv/bin/activate && python ytb_dl.py --channel https://www.youtube.com/@mkbhd \
  --throttle 800K

# Audio only — great for lectures and podcasts
source .venv/bin/activate && python ytb_dl.py --channel https://www.youtube.com/@3blue1brown \
  --audio-only

# Date range
source .venv/bin/activate && python ytb_dl.py --channel https://www.youtube.com/@mkbhd \
  --from 2024-01-01 --to 2024-06-30

# Specific video
source .venv/bin/activate && python ytb_dl.py --urls https://youtu.be/abc123
```

---

## Makefile shortcuts

```bash
make setup

# Transcripts
make transcripts CHANNEL=https://www.youtube.com/@mkbhd
make transcripts CHANNEL=https://www.youtube.com/@mkbhd LIMIT=5
make transcripts CHANNEL=https://www.youtube.com/@mkbhd FROM=2024-01-01 TO=2024-06-30
make transcript  URL=https://youtu.be/abc123

# Video downloads
make download CHANNEL=https://www.youtube.com/@mkbhd
make download CHANNEL=https://www.youtube.com/@mkbhd QUALITY=1080p
make download CHANNEL=https://www.youtube.com/@mkbhd THROTTLE=800K
make video    URL=https://youtu.be/abc123

# Audio only
make audio URL=https://youtu.be/abc123
make audio CHANNEL=https://www.youtube.com/@3blue1brown LIMIT=10
```

---

## Human-pacing layer (`_human.py`)

Both tools share the same behaviour model:

| Behaviour | Mechanism |
|-----------|-----------|
| Inter-request delays | Log-normal distribution (mean 3–7 s) — matches observed human click timing |
| Distraction breaks | 8% chance of 25–75 s pause between videos |
| Pre-download pause | 1.5–12 s before each download starts (simulates clicking play) |
| Reading pause | 0.4–6 s per video (skimming the title) |
| Post-listing pause | 1–10 s after channel page loads (scrolling) |
| UA rotation | 14 real Chrome/Firefox/Safari/Edge UAs (2024–2025) |
| Header variation | Accept-Language, Referer, DNT, Accept vary per session |
| Session persistence | One `requests.Session` per run (same-tab behaviour) |
| yt-dlp internals | `sleep_interval` and `sleep_interval_requests` randomised |
| Bandwidth throttle | `--throttle` cap mimics streaming speed |

---

## How it works

1. **Channel listing** — `yt-dlp` fetches video metadata (no download, no API key needed).
2. **Transcript fetch** — `youtube-transcript-api` retrieves caption data YouTube hosts (`.srv3` / `.vtt` internally). Manual captions preferred → auto-generated → any language.
3. **Video download** — `yt-dlp` downloads and muxes the selected quality. Archive log prevents re-runs.
4. **Nothing is decoded** — no video-to-text conversion, no local speech model.
