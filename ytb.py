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
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

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


def sanitize_filename(name: str) -> str:
    """Remove characters that are invalid in filenames."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:200]  # cap length


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def get_channel_videos(channel_url: str, limit: int, from_date: datetime | None, to_date: datetime | None) -> list[dict]:
    """
    Use yt-dlp to list videos from a channel without downloading them.
    Returns list of dicts with keys: id, title, upload_date, url
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,       # list only, no download
        "playlistend": limit * 3,   # fetch more than needed so date filter has room
        "ignoreerrors": True,
    }

    videos = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        if not info:
            print(f"ERROR: Could not retrieve info for {channel_url}")
            return []

        entries = info.get("entries", [])
        # Flatten one level if it's a nested playlist (channels often return a playlist of playlists)
        if entries and entries[0] and entries[0].get("_type") == "playlist":
            flat_entries = []
            for sub in entries:
                flat_entries.extend(sub.get("entries") or [])
            entries = flat_entries

        for entry in entries:
            if not entry:
                continue
            vid_id = entry.get("id") or extract_video_id(entry.get("url", ""))
            if not vid_id:
                continue

            upload_str = entry.get("upload_date")  # "YYYYMMDD"
            upload_dt = None
            if upload_str:
                try:
                    upload_dt = datetime.strptime(upload_str, "%Y%m%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            # Date filtering
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

    return videos


def fetch_transcript(video_id: str, preferred_lang: str = "en") -> tuple[str, str]:
    """
    Fetch transcript text for a video.
    Returns (transcript_text, language_used).
    Prefers manual captions in preferred_lang, falls back to auto-generated,
    then any available language.
    """
    api = YouTubeTranscriptApi()

    try:
        transcript_list = api.list(video_id)
    except TranscriptsDisabled:
        raise RuntimeError("Transcripts are disabled for this video.")
    except Exception as e:
        raise RuntimeError(f"Could not list transcripts: {e}")

    transcript = None
    lang_used = preferred_lang

    # 1. Try manual transcript in preferred language
    try:
        transcript = transcript_list.find_manually_created_transcript([preferred_lang])
        lang_used = preferred_lang + " (manual)"
    except NoTranscriptFound:
        pass

    # 2. Try auto-generated in preferred language
    if transcript is None:
        try:
            transcript = transcript_list.find_generated_transcript([preferred_lang])
            lang_used = preferred_lang + " (auto-generated)"
        except NoTranscriptFound:
            pass

    # 3. Fall back to any available transcript
    if transcript is None:
        available = list(transcript_list)
        if not available:
            raise RuntimeError("No transcripts available.")
        transcript = available[0]
        lang_used = transcript.language_code + (" (auto-generated)" if transcript.is_generated else " (manual)")

    raw = transcript.fetch()

    # Concatenate segments into plain text, one line per segment
    lines = []
    for segment in raw:
        # FetchedTranscript segments are objects with a .text attribute in newer versions
        text = getattr(segment, "text", None) or segment.get("text", "") if isinstance(segment, dict) else segment.text
        text = text.strip()
        if text:
            lines.append(text)

    return "\n".join(lines), lang_used


def save_transcript(video: dict, transcript_text: str, lang_used: str, output_dir: Path) -> Path:
    """Write transcript to a .txt file and return the path."""
    date_prefix = video["upload_date"]  # YYYYMMDD or "unknown"
    safe_title = sanitize_filename(video["title"])
    filename = f"{date_prefix}_{safe_title}_{video['id']}.txt"
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

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build video list
    if args.channel:
        print(f"Fetching video list from channel: {args.channel}")
        videos = get_channel_videos(
            channel_url=args.channel,
            limit=args.limit,
            from_date=args.from_date,
            to_date=args.to_date,
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

    # Process each video
    success, failed = 0, 0
    for i, video in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] {video['title']} ({video['id']})")

        # Fetch full metadata if we only have the ID (from --urls)
        if video["title"] == video["id"]:
            try:
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                    info = ydl.extract_info(video["url"], download=False)
                    if info:
                        video["title"] = info.get("title", video["id"])
                        upload = info.get("upload_date")
                        if upload:
                            video["upload_date"] = upload
            except Exception:
                pass

        try:
            transcript_text, lang_used = fetch_transcript(video["id"], preferred_lang=args.lang)
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
