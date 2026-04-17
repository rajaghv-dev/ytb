#!/usr/bin/env python3
"""
ytb_dl.py — Archive YouTube videos for personal/educational use.
Uses yt-dlp with human-paced delays, browser fingerprint rotation,
bandwidth throttling, and an archive log so re-runs skip already-saved videos.

Usage examples:
  # Archive last 20 videos from a channel (720p mp4, default)
  python ytb_dl.py --channel https://www.youtube.com/@mkbhd

  # Best available quality
  python ytb_dl.py --channel https://www.youtube.com/@mkbhd --quality best

  # Specific resolution cap
  python ytb_dl.py --channel https://www.youtube.com/@mkbhd --quality 1080p

  # Audio only (lectures, podcasts)
  python ytb_dl.py --channel https://www.youtube.com/@3blue1brown --audio-only

  # Videos between two dates
  python ytb_dl.py --channel https://www.youtube.com/@mkbhd --from 2024-01-01 --to 2024-06-30

  # Specific video URLs
  python ytb_dl.py --urls https://youtu.be/abc123 https://youtu.be/xyz456

  # Embed subtitles + thumbnail into the file
  python ytb_dl.py --channel https://www.youtube.com/@mkbhd --subs --thumbnail

  # Throttle bandwidth to 800 KB/s (looks like streaming, not bulk download)
  python ytb_dl.py --channel https://www.youtube.com/@mkbhd --throttle 800K

  # Skip delays (use when you don't care about fingerprinting)
  python ytb_dl.py --channel https://www.youtube.com/@mkbhd --no-delay
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

from _human import (
    ydl_base_opts,
    pause_between_items,
    pause_reading,
    pause_after_listing,
    pause_pre_download,
)


# ── format / quality presets ──────────────────────────────────────────────────

# Each preset is a yt-dlp format string that prefers mp4+m4a so the result
# muxes cleanly without re-encoding.  Falls back gracefully if not available.
_QUALITY_FORMATS = {
    "best":  "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]",
    "720p":  "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
    "480p":  "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
    "360p":  "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]",
    "audio": "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio",
}

_DEFAULT_QUALITY = "720p"


# ── helpers ───────────────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:180]


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


# ── download ──────────────────────────────────────────────────────────────────

def build_ydl_download_opts(
    output_dir: Path,
    quality: str,
    audio_only: bool,
    subs: bool,
    thumbnail: bool,
    throttle: str | None,
    archive_file: Path | None,
    no_delay: bool,
) -> dict:
    """
    Assemble yt-dlp options for actual downloading.
    Output filename template: YYYYMMDD_Title_videoID.ext
    """
    fmt = "audio" if audio_only else quality
    format_str = _QUALITY_FORMATS.get(fmt, _QUALITY_FORMATS[_DEFAULT_QUALITY])

    # File naming: date_title_id.ext  (readable + dedup-safe)
    outtmpl = str(output_dir / "%(upload_date)s_%(title)s_%(id)s.%(ext)s")

    opts = ydl_base_opts({
        "format": format_str,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4" if not audio_only else None,
        "restrictfilenames": False,   # keep unicode titles
        "windowsfilenames": True,     # strip chars invalid on Windows too
        "nooverwrites": True,         # never clobber existing files
        "continuedl": True,           # resume partial downloads
        "retries": 5,
        "fragment_retries": 10,
        "quiet": False,               # show yt-dlp progress bar
        "no_warnings": False,
        "progress_hooks": [],
    })

    # Bandwidth throttle — looks like a human streaming rather than bulk pulling
    if throttle:
        opts["ratelimit"] = _parse_throttle(throttle)

    # Archive file — yt-dlp writes "youtube VIDEO_ID" lines; skips on re-run
    if archive_file:
        opts["download_archive"] = str(archive_file)

    # Subtitles
    if subs:
        opts.update({
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "en-US"],
            "embedsubtitles": True,
            "postprocessors": [{"key": "FFmpegEmbedSubtitle"}],
        })

    # Thumbnail embedded into the file
    if thumbnail:
        existing_pp = opts.get("postprocessors", [])
        existing_pp.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
        opts["writethumbnail"] = True
        opts["postprocessors"] = existing_pp

    # Audio-only post-processing: extract to m4a
    if audio_only:
        existing_pp = opts.get("postprocessors", [])
        existing_pp.insert(0, {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
            "preferredquality": "192",
        })
        opts["postprocessors"] = existing_pp
        opts["merge_output_format"] = None

    return opts


def _parse_throttle(s: str) -> int:
    """Convert '800K', '2M', '500k' → bytes per second."""
    s = s.strip().upper()
    if s.endswith("K"):
        return int(float(s[:-1]) * 1024)
    if s.endswith("M"):
        return int(float(s[:-1]) * 1024 * 1024)
    return int(s)  # assume raw bytes


def download_video(
    video: dict,
    ydl_opts: dict,
    no_delay: bool,
) -> bool:
    """
    Download a single video.  Returns True on success.
    Applies a pre-download pause to simulate a human clicking play first.
    """
    pause_pre_download(no_delay)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ret = ydl.download([video["url"]])
            return ret == 0
    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if "has already been recorded" in err or "already been downloaded" in err:
            print("  -> Already in archive, skipping.")
            return True   # not a failure — intentional skip
        raise


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_date(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{s}'. Use YYYY-MM-DD format.")


def main():
    parser = argparse.ArgumentParser(
        description="Archive YouTube videos for personal/educational use.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--channel", metavar="URL",
                        help="YouTube channel URL (@handle, /c/name, or /channel/ID)")
    source.add_argument("--urls", metavar="URL", nargs="+",
                        help="One or more specific video URLs")

    parser.add_argument("--limit", type=int, default=20, metavar="N",
                        help="Max videos to download from channel (default: 20)")
    parser.add_argument("--from", dest="from_date", type=parse_date, metavar="YYYY-MM-DD",
                        help="Only include videos uploaded on or after this date")
    parser.add_argument("--to",   dest="to_date",   type=parse_date, metavar="YYYY-MM-DD",
                        help="Only include videos uploaded on or before this date")

    parser.add_argument("--quality",
                        choices=list(_QUALITY_FORMATS.keys()),
                        default=_DEFAULT_QUALITY,
                        help=f"Video quality (default: {_DEFAULT_QUALITY})")
    parser.add_argument("--audio-only", action="store_true",
                        help="Download audio only — m4a (overrides --quality)")

    parser.add_argument("--subs", action="store_true",
                        help="Embed English subtitles/captions into the file")
    parser.add_argument("--thumbnail", action="store_true",
                        help="Embed video thumbnail as cover art")

    parser.add_argument("--throttle", metavar="RATE",
                        help="Bandwidth cap, e.g. 800K or 2M (bytes/s). "
                             "Mimics streaming speed instead of bulk download.")
    parser.add_argument("--no-archive", action="store_true",
                        help="Disable the archive log (re-download already-saved videos)")
    parser.add_argument("--output", default="./videos", metavar="DIR",
                        help="Output directory (default: ./videos)")
    parser.add_argument("--no-delay", action="store_true",
                        help="Skip all human-pacing delays")

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    archive_file = None if args.no_archive else (output_dir / ".ytb_archive.txt")

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
        print(f"Found {len(videos)} video(s) to download.\n")
    else:
        videos = []
        for url in args.urls:
            vid_id = extract_video_id(url)
            if not vid_id:
                print(f"WARNING: Could not parse video ID from {url!r}, skipping.")
                continue
            videos.append({"id": vid_id, "title": vid_id, "upload_date": "unknown", "url": url})

    # Build shared yt-dlp opts once (all videos in this run use same quality/flags)
    ydl_opts = build_ydl_download_opts(
        output_dir=output_dir,
        quality=args.quality,
        audio_only=args.audio_only,
        subs=args.subs,
        thumbnail=args.thumbnail,
        throttle=args.throttle,
        archive_file=archive_file,
        no_delay=args.no_delay,
    )

    # Print run summary
    mode = "audio-only (m4a)" if args.audio_only else args.quality
    print(f"Quality:  {mode}")
    print(f"Output:   {output_dir}/")
    if args.throttle:
        print(f"Throttle: {args.throttle}/s")
    if archive_file:
        print(f"Archive:  {archive_file}")
    print()

    success, failed = 0, 0
    for i, video in enumerate(videos, 1):
        if i > 1:
            pause_between_items(args.no_delay, label="next in")

        print(f"[{i}/{len(videos)}] {video['title']}  ({video['id']})")
        pause_reading(args.no_delay)

        try:
            ok = download_video(video, ydl_opts, no_delay=args.no_delay)
            if ok:
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  -> ERROR: {e}")
            failed += 1

    print(f"\nDone. {success} video(s) saved to '{output_dir}/'", end="")
    if failed:
        print(f", {failed} failed.", end="")
    print()
    if archive_file and archive_file.exists():
        count = sum(1 for _ in archive_file.read_text().splitlines() if _.strip())
        print(f"Archive log now contains {count} video(s): {archive_file}")


if __name__ == "__main__":
    main()
