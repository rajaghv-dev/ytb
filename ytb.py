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
import re
import sys
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

from _human import (
    ydl_base_opts,
    make_requests_session,
    pause_between_items,
    pause_reading,
    pause_after_listing,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:200]


def extract_video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


# ── channel listing ───────────────────────────────────────────────────────────

def get_channel_videos(
    channel_url: str,
    limit: int,
    from_date: datetime | None,
    to_date: datetime | None,
    no_delay: bool = False,
) -> list[dict]:
    opts = ydl_base_opts({
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


# ── transcript fetch ──────────────────────────────────────────────────────────

def fetch_transcript(
    video_id: str,
    preferred_lang: str = "en",
    session: requests.Session | None = None,
) -> tuple[str, str]:
    """
    Returns (transcript_text, language_used).
    Preference: manual → auto-generated → any available language.
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
        lang_used = transcript.language_code + (
            " (auto-generated)" if transcript.is_generated else " (manual)"
        )

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


# ── CLI ───────────────────────────────────────────────────────────────────────

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
    source.add_argument("--channel", metavar="URL",
                        help="YouTube channel URL (@handle, /c/name, or /channel/ID)")
    source.add_argument("--urls", metavar="URL", nargs="+",
                        help="One or more specific video URLs")

    parser.add_argument("--limit", type=int, default=20, metavar="N",
                        help="Max videos from channel (default: 20)")
    parser.add_argument("--from", dest="from_date", type=parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--to",   dest="to_date",   type=parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--lang", default="en", metavar="LANG",
                        help="Preferred transcript language code (default: en)")
    parser.add_argument("--output", default="./transcripts", metavar="DIR",
                        help="Output directory (default: ./transcripts)")
    parser.add_argument("--meta", action="store_true",
                        help="Also save a .json sidecar with video metadata")
    parser.add_argument("--no-delay", action="store_true",
                        help="Skip all human-pacing delays")

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    http_session = make_requests_session()

    # Build video list
    if args.channel:
        print(f"Fetching video list from: {args.channel}")
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
        if i > 1:
            pause_between_items(args.no_delay, label="pause")

        print(f"[{i}/{len(videos)}] {video['title']} ({video['id']})")
        pause_reading(args.no_delay)

        # Resolve full metadata for bare IDs (from --urls)
        if video["title"] == video["id"]:
            try:
                with yt_dlp.YoutubeDL(ydl_base_opts()) as ydl:
                    info = ydl.extract_info(video["url"], download=False)
                    if info:
                        video["title"] = info.get("title", video["id"])
                        if info.get("upload_date"):
                            video["upload_date"] = info["upload_date"]
            except Exception:
                pass

        try:
            transcript_text, lang_used = fetch_transcript(
                video["id"], preferred_lang=args.lang, session=http_session,
            )
            out_path = save_transcript(video, transcript_text, lang_used, output_dir)
            print(f"  -> Saved: {out_path}  [{lang_used}]")

            if args.meta:
                out_path.with_suffix(".json").write_text(
                    json.dumps(video, indent=2), encoding="utf-8"
                )
            success += 1
        except RuntimeError as e:
            print(f"  -> SKIPPED: {e}")
            failed += 1
        except Exception as e:
            print(f"  -> ERROR: {e}")
            failed += 1

    print(f"\nDone. {success} transcript(s) saved to '{output_dir}/'", end="")
    if failed:
        print(f", {failed} skipped.", end="")
    print()


if __name__ == "__main__":
    main()
