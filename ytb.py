#!/usr/bin/env python3
"""
ytb.py — Download YouTube transcripts without converting video to text.
Fetches captions/subtitles that YouTube already hosts (auto-generated or manual).

Usage examples:
  # Last 20 videos from a channel
  python ytb.py --channel https://www.youtube.com/@mkbhd

  # Last N videos
  python ytb.py --channel https://www.youtube.com/@mkbhd --limit 5

  # Videos uploaded between two dates
  python ytb.py --channel https://www.youtube.com/@mkbhd --from 2024-01-01 --to 2024-03-31

  # Specific video URLs
  python ytb.py --urls https://youtu.be/abc123 https://youtu.be/xyz456

  # Choose transcript language (default: en, falls back to auto-generated)
  python ytb.py --channel https://www.youtube.com/@mkbhd --lang en

  # Custom output directory
  python ytb.py --channel https://www.youtube.com/@mkbhd --output ./my-transcripts

  # Skip all delays (faster, less human-like)
  python ytb.py --channel https://www.youtube.com/@mkbhd --no-delay
"""

import argparse
import json
import math
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    import yt_dlp
except ImportError:
    print("ERROR: yt-dlp not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled
except ImportError:
    print("ERROR: youtube-transcript-api not installed. Run: pip install -r requirements.txt")
    sys.exit(1)


# ── realistic browser fingerprints ────────────────────────────────────────────

# Real Chrome/Firefox/Safari UAs from 2024-2025 across common OS combos
_USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

# Referers that a human visiting YouTube would realistically come from
_REFERERS = [
    "https://www.youtube.com/",
    "https://www.youtube.com/feed/subscriptions",
    "https://www.youtube.com/results?search_query=",
    "https://www.google.com/",
    "https://www.google.com/search?q=youtube",
    "https://www.reddit.com/",
    "https://t.co/",
    "",  # direct navigation (no referer)
]

# Browser accept-language combos — weighted toward English variants
_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en-US,en;q=0.9,es;q=0.8",
    "en-US,en;q=0.8",
    "en-CA,en;q=0.9,fr-CA;q=0.8,fr;q=0.7,en-US;q=0.6",
    "en-AU,en;q=0.9",
    "en-US,en;q=0.9,de;q=0.7",
]


def random_ua() -> str:
    return random.choice(_USER_AGENTS)


def random_headers(referer: str | None = None, include_encoding: bool = False) -> dict:
    """
    Build a plausible browser request header set.

    include_encoding=False: omit Accept-Encoding so that requests/urllib3 manages
    transparent decompression itself — setting it manually in session headers causes
    response bodies to arrive still compressed and breaks parsers downstream.
    """
    ua = random_ua()
    is_firefox = "Firefox" in ua

    headers = {
        "User-Agent": ua,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Connection": "keep-alive",
        "DNT": random.choice(["1", "0", "1", "1"]),  # most privacy-conscious users have DNT on
        "Upgrade-Insecure-Requests": "1",
    }

    if include_encoding:
        headers["Accept-Encoding"] = "gzip, deflate, br"

    if is_firefox:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    else:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"

    ref = referer if referer is not None else random.choice(_REFERERS)
    if ref:
        headers["Referer"] = ref

    return headers


# ── human timing ──────────────────────────────────────────────────────────────

def _lognormal_sleep(mean_s: float, sigma: float = 0.5, min_s: float = 0.3, max_s: float = 120.0) -> float:
    """
    Draw a sleep duration from a log-normal distribution.
    Log-normal matches observed human inter-action timing better than uniform:
    most clicks happen quickly but there's a long right tail for distraction.
    """
    mu = math.log(mean_s) - (sigma ** 2) / 2
    return max(min_s, min(max_s, random.lognormvariate(mu, sigma)))


def pause_between_videos(no_delay: bool = False) -> None:
    """
    Simulate the gap between a human finishing one video page and starting
    the next: 3–12 s on average, occasionally much longer.
    """
    if no_delay:
        return

    # 8% chance of a long "distraction" break (phone, bio, tab switching)
    if random.random() < 0.08:
        duration = random.uniform(25, 75)
        print(f"  [pause {duration:.0f}s]", flush=True)
        time.sleep(duration)
        return

    duration = _lognormal_sleep(mean_s=random.uniform(3.0, 7.0), sigma=0.6)
    print(f"  [pause {duration:.1f}s]", flush=True)
    time.sleep(duration)


def pause_reading(no_delay: bool = False) -> None:
    """
    Short pause as if skimming the video title / description before clicking.
    0.8–3 s, log-normal.
    """
    if no_delay:
        return
    time.sleep(_lognormal_sleep(mean_s=1.2, sigma=0.5, min_s=0.4, max_s=6.0))


def pause_after_listing(no_delay: bool = False) -> None:
    """
    Pause after the channel page loads — human scrolls through the list.
    Scales with how many videos were found.
    """
    if no_delay:
        return
    time.sleep(_lognormal_sleep(mean_s=2.5, sigma=0.7, min_s=1.0, max_s=10.0))


# ── yt-dlp with browser headers ───────────────────────────────────────────────

def _ydl_opts(extra: dict | None = None) -> dict:
    """Base yt-dlp options that look like a real browser session."""
    # yt-dlp handles raw HTTP bytes itself, so Accept-Encoding is safe here
    hdrs = random_headers(referer="https://www.youtube.com/", include_encoding=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "http_headers": hdrs,
        # Randomise the sleep_interval so yt-dlp's own fragment requests vary too
        "sleep_interval": round(random.uniform(0.5, 1.5), 2),
        "max_sleep_interval": round(random.uniform(2.0, 4.0), 2),
        "sleep_interval_requests": round(random.uniform(0.3, 1.0), 2),
    }
    if extra:
        opts.update(extra)
    return opts


# ── transcript API with browser session ───────────────────────────────────────

def _make_requests_session() -> requests.Session:
    """
    Build a requests.Session that looks like a real browser:
    consistent UA + headers for the lifetime of the session.
    """
    session = requests.Session()
    session.headers.update(random_headers(referer="https://www.youtube.com/"))
    return session


# ── core logic ────────────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:200]


def extract_video_id(url: str) -> str | None:
    for pat in [r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})"]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def get_channel_videos(
    channel_url: str,
    limit: int,
    from_date: datetime | None,
    to_date: datetime | None,
    no_delay: bool = False,
) -> list[dict]:
    """Use yt-dlp to list videos from a channel without downloading them."""
    opts = _ydl_opts({
        "extract_flat": True,
        "playlistend": limit * 3,
    })

    videos = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        if not info:
            print(f"ERROR: Could not retrieve info for {channel_url}")
            return []

        entries = info.get("entries", [])
        if entries and entries[0] and entries[0].get("_type") == "playlist":
            flat = []
            for sub in entries:
                flat.extend(sub.get("entries") or [])
            entries = flat

        for entry in entries:
            if not entry:
                continue
            vid_id = entry.get("id") or extract_video_id(entry.get("url", ""))
            if not vid_id:
                continue

            upload_str = entry.get("upload_date")
            upload_dt = None
            if upload_str:
                try:
                    upload_dt = datetime.strptime(upload_str, "%Y%m%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            if from_date and upload_dt and upload_dt < from_date:
                continue
            if to_date and upload_dt and upload_dt > to_date:
                continue

            videos.append({
                "id": vid_id,
                "title": entry.get("title", vid_id),
                "upload_date": upload_str or "unknown",
                "url": f"https://www.youtube.com/watch?v={vid_id}",
            })

            if len(videos) >= limit:
                break

    pause_after_listing(no_delay)
    return videos


def fetch_transcript(
    video_id: str,
    preferred_lang: str = "en",
    session: requests.Session | None = None,
) -> tuple[str, str]:
    """
    Fetch transcript text for a video.
    Returns (transcript_text, language_used).
    """
    api = YouTubeTranscriptApi(http_client=session) if session else YouTubeTranscriptApi()

    try:
        transcript_list = api.list(video_id)
    except TranscriptsDisabled:
        raise RuntimeError("Transcripts are disabled for this video.")
    except Exception as e:
        raise RuntimeError(f"Could not list transcripts: {e}")

    transcript = None
    lang_used = preferred_lang

    try:
        transcript = transcript_list.find_manually_created_transcript([preferred_lang])
        lang_used = preferred_lang + " (manual)"
    except NoTranscriptFound:
        pass

    if transcript is None:
        try:
            transcript = transcript_list.find_generated_transcript([preferred_lang])
            lang_used = preferred_lang + " (auto-generated)"
        except NoTranscriptFound:
            pass

    if transcript is None:
        available = list(transcript_list)
        if not available:
            raise RuntimeError("No transcripts available.")
        transcript = available[0]
        lang_used = transcript.language_code + (" (auto-generated)" if transcript.is_generated else " (manual)")

    raw = transcript.fetch()

    lines = []
    for segment in raw:
        text = segment.get("text", "") if isinstance(segment, dict) else segment.text
        text = text.strip()
        if text:
            lines.append(text)

    return "\n".join(lines), lang_used


def save_transcript(video: dict, transcript_text: str, lang_used: str, output_dir: Path) -> Path:
    safe_title = sanitize_filename(video["title"])
    filename = f"{video['upload_date']}_{safe_title}_{video['id']}.txt"
    out_path = output_dir / filename

    header = (
        f"Title:        {video['title']}\n"
        f"URL:          {video['url']}\n"
        f"Upload date:  {video['upload_date']}\n"
        f"Language:     {lang_used}\n"
        f"{'='*80}\n\n"
    )
    out_path.write_text(header + transcript_text, encoding="utf-8")
    return out_path


def parse_date(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{s}'. Use YYYY-MM-DD format.")


def main():
    parser = argparse.ArgumentParser(
        description="Download YouTube transcripts (no video conversion — uses YouTube's own captions).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--channel", metavar="URL", help="YouTube channel URL (@handle, /c/name, or /channel/ID)")
    source.add_argument("--urls", metavar="URL", nargs="+", help="One or more specific video URLs")

    parser.add_argument("--limit", type=int, default=20, metavar="N",
                        help="Max number of videos to process from a channel (default: 20)")
    parser.add_argument("--from", dest="from_date", type=parse_date, metavar="YYYY-MM-DD",
                        help="Only include videos uploaded on or after this date")
    parser.add_argument("--to", dest="to_date", type=parse_date, metavar="YYYY-MM-DD",
                        help="Only include videos uploaded on or before this date")
    parser.add_argument("--lang", default="en", metavar="LANG",
                        help="Preferred transcript language code (default: en)")
    parser.add_argument("--output", default="./transcripts", metavar="DIR",
                        help="Output directory for transcript files (default: ./transcripts)")
    parser.add_argument("--meta", action="store_true",
                        help="Also save a JSON file with metadata for each video")
    parser.add_argument("--no-delay", action="store_true",
                        help="Skip all human-pacing delays (faster, less human-like)")

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # One requests.Session for the whole run — mimics a persistent browser tab
    http_session = _make_requests_session()

    # Build video list
    if args.channel:
        print(f"Fetching video list from channel: {args.channel}")
        videos = get_channel_videos(
            channel_url=args.channel,
            limit=args.limit,
            from_date=args.from_date,
            to_date=args.to_date,
            no_delay=args.no_delay,
        )
        if not videos:
            print("No videos found matching the criteria.")
            sys.exit(0)
        print(f"Found {len(videos)} video(s) to process.\n")
    else:
        videos = []
        for url in args.urls:
            vid_id = extract_video_id(url)
            if not vid_id:
                print(f"WARNING: Could not parse video ID from {url!r}, skipping.")
                continue
            videos.append({"id": vid_id, "title": vid_id, "upload_date": "unknown", "url": url})

    success, failed = 0, 0
    for i, video in enumerate(videos, 1):
        # Pause before each video except the first (simulate clicking through a list)
        if i > 1:
            pause_between_videos(args.no_delay)

        print(f"[{i}/{len(videos)}] {video['title']} ({video['id']})")

        # Pause as if reading the title before clicking
        pause_reading(args.no_delay)

        # Fetch full metadata if we only have the ID (from --urls)
        if video["title"] == video["id"]:
            try:
                with yt_dlp.YoutubeDL(_ydl_opts()) as ydl:
                    info = ydl.extract_info(video["url"], download=False)
                    if info:
                        video["title"] = info.get("title", video["id"])
                        upload = info.get("upload_date")
                        if upload:
                            video["upload_date"] = upload
            except Exception:
                pass

        try:
            transcript_text, lang_used = fetch_transcript(
                video["id"],
                preferred_lang=args.lang,
                session=http_session,
            )
            out_path = save_transcript(video, transcript_text, lang_used, output_dir)
            print(f"  -> Saved: {out_path}  [{lang_used}]")

            if args.meta:
                meta_path = out_path.with_suffix(".json")
                meta_path.write_text(json.dumps(video, indent=2), encoding="utf-8")

            success += 1
        except RuntimeError as e:
            print(f"  -> SKIPPED: {e}")
            failed += 1
        except Exception as e:
            print(f"  -> ERROR: {e}")
            failed += 1

    print(f"\nDone. {success} transcript(s) saved to '{output_dir}/'", end="")
    if failed:
        print(f", {failed} skipped (no captions available).", end="")
    print()


if __name__ == "__main__":
    main()
