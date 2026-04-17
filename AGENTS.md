# ytb — YouTube Transcript Downloader

Fetches transcripts (captions) directly from YouTube — no video download, no speech-to-text.
Works with Claude Code, OpenCode, Cursor, Windsurf, Aider, and any agent that reads AGENTS.md.

---

## Setup

```bash
bash setup.sh          # creates .venv, installs deps, makes ytb.py executable
source .venv/bin/activate
```

---

## Tool: `ytb.py`

**Binary:** `python ytb.py` (or `python3 ytb.py`)  
**Requires:** `.venv` activated (run `setup.sh` once)

### Arguments

| Flag | Description |
|------|-------------|
| `--channel URL` | YouTube channel — `@handle`, `/c/name`, or `/channel/ID` |
| `--urls URL…` | One or more specific video URLs |
| `--limit N` | Max videos from channel (default: 20) |
| `--from YYYY-MM-DD` | Only videos uploaded on or after this date |
| `--to YYYY-MM-DD` | Only videos uploaded on or before this date |
| `--lang CODE` | Preferred language (default: `en`). Auto-falls-back if unavailable |
| `--output DIR` | Output directory (default: `./transcripts`) |
| `--meta` | Also write a `.json` sidecar with video metadata |

### Output

One `.txt` file per video, named `YYYYMMDD_Title_videoID.txt`, saved to `--output` dir.  
File structure:
```
Title:        <video title>
URL:          https://www.youtube.com/watch?v=...
Upload date:  YYYYMMDD
Language:     en (manual) | en (auto-generated) | ...
================================================================================

<full transcript text, one caption segment per line>
```

---

## Usage examples (for agents / prompt-driven workflows)

### Last 20 videos from a channel
```bash
source .venv/bin/activate && python ytb.py --channel https://www.youtube.com/@mkbhd
```

### Last N videos
```bash
source .venv/bin/activate && python ytb.py --channel https://www.youtube.com/@mkbhd --limit 5
```

### Videos between two dates
```bash
source .venv/bin/activate && python ytb.py \
  --channel https://www.youtube.com/@mkbhd \
  --from 2024-01-01 --to 2024-06-30
```

### Specific video URLs
```bash
source .venv/bin/activate && python ytb.py \
  --urls https://youtu.be/abc123 https://youtu.be/xyz456
```

### Non-English channel
```bash
source .venv/bin/activate && python ytb.py \
  --channel https://www.youtube.com/@channel --lang hi
```

### Save transcripts + metadata JSON
```bash
source .venv/bin/activate && python ytb.py \
  --channel https://www.youtube.com/@channel --meta --output ./out
```

---

## Makefile shortcuts

```bash
make setup          # run setup.sh
make transcripts CHANNEL=https://www.youtube.com/@mkbhd
make transcripts CHANNEL=https://www.youtube.com/@mkbhd LIMIT=5
make transcripts CHANNEL=https://www.youtube.com/@mkbhd FROM=2024-01-01 TO=2024-06-30
make video URL=https://youtu.be/abc123
```

---

## How it works

1. **Channel listing** — `yt-dlp` (no YouTube API key required) fetches the channel's video list as flat metadata (no download).
2. **Transcript fetch** — `youtube-transcript-api` retrieves the caption data YouTube already hosts (`.srv3` / `.vtt` format internally), returned as structured text. Preference order: manual captions → auto-generated → any available language.
3. **Nothing is downloaded** — no audio, no video, no conversion.

---

## Limitations

- Videos with captions disabled are skipped (a message is printed).
- Age-restricted or private videos may fail depending on your IP/cookies.
- Auto-generated captions may have formatting artefacts (`[♪♪♪]`, `[Music]`, etc.).
