"""
_human.py — Shared human-pacing and browser-fingerprint helpers.
Imported by ytb.py (transcripts) and ytb_dl.py (video download).
"""

import math
import random
import time

try:
    import requests
except ImportError:
    requests = None  # callers that need it will fail loudly themselves


# ── realistic browser fingerprints ────────────────────────────────────────────

# Real Chrome/Firefox/Safari/Edge UAs from 2024-2025 across common OS combos
USER_AGENTS = [
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

# Referers a human visiting YouTube would realistically come from
REFERERS = [
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
ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en-US,en;q=0.9,es;q=0.8",
    "en-US,en;q=0.8",
    "en-CA,en;q=0.9,fr-CA;q=0.8,fr;q=0.7,en-US;q=0.6",
    "en-AU,en;q=0.9",
    "en-US,en;q=0.9,de;q=0.7",
]


def random_ua() -> str:
    return random.choice(USER_AGENTS)


def random_headers(referer: str | None = None, include_encoding: bool = False) -> dict:
    """
    Build a plausible browser request header set.

    include_encoding=False: omit Accept-Encoding so that requests/urllib3 manages
    transparent decompression itself — setting it manually in a requests.Session
    causes compressed response bodies to arrive un-decoded and breaks parsers.
    Pass include_encoding=True for yt-dlp, which handles raw bytes itself.
    """
    ua = random_ua()
    is_firefox = "Firefox" in ua

    headers = {
        "User-Agent": ua,
        "Accept-Language": random.choice(ACCEPT_LANGUAGES),
        "Connection": "keep-alive",
        "DNT": random.choice(["1", "0", "1", "1"]),  # most privacy-conscious users have DNT on
        "Upgrade-Insecure-Requests": "1",
    }

    if include_encoding:
        headers["Accept-Encoding"] = "gzip, deflate, br"

    if is_firefox:
        headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        )
    else:
        headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;"
            "q=0.8,application/signed-exchange;v=b3;q=0.7"
        )

    ref = referer if referer is not None else random.choice(REFERERS)
    if ref:
        headers["Referer"] = ref

    return headers


def make_requests_session() -> "requests.Session":
    """
    Build a requests.Session that looks like a real browser:
    consistent UA + headers for the lifetime of the session (same-tab behaviour).
    """
    session = requests.Session()
    session.headers.update(random_headers(referer="https://www.youtube.com/"))
    return session


def ydl_base_opts(extra: dict | None = None) -> dict:
    """
    Base yt-dlp options that look like a real browser session.
    Includes Accept-Encoding (yt-dlp handles raw bytes itself) and
    randomised internal sleep intervals.
    """
    hdrs = random_headers(referer="https://www.youtube.com/", include_encoding=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "http_headers": hdrs,
        # Randomise yt-dlp's own fragment-level request pacing
        "sleep_interval": round(random.uniform(0.5, 1.5), 2),
        "max_sleep_interval": round(random.uniform(2.0, 4.0), 2),
        "sleep_interval_requests": round(random.uniform(0.3, 1.0), 2),
    }
    if extra:
        opts.update(extra)
    return opts


# ── human timing ──────────────────────────────────────────────────────────────

def _lognormal_sleep(mean_s: float, sigma: float = 0.5,
                     min_s: float = 0.3, max_s: float = 120.0) -> float:
    """
    Draw a sleep duration from a log-normal distribution.
    Log-normal matches observed human inter-action timing better than uniform:
    most actions happen quickly, but there's a long right tail for distraction.
    """
    mu = math.log(mean_s) - (sigma ** 2) / 2
    return max(min_s, min(max_s, random.lognormvariate(mu, sigma)))


def pause_between_items(no_delay: bool = False, label: str = "pause") -> None:
    """
    Gap between processing items — simulates a human clicking to the next video.
    Mean 3–7 s, occasional distraction break (25–75 s, 8% chance).
    """
    if no_delay:
        return
    if random.random() < 0.08:
        duration = random.uniform(25, 75)
        print(f"  [{label} {duration:.0f}s]", flush=True)
        time.sleep(duration)
        return
    duration = _lognormal_sleep(mean_s=random.uniform(3.0, 7.0), sigma=0.6)
    print(f"  [{label} {duration:.1f}s]", flush=True)
    time.sleep(duration)


def pause_reading(no_delay: bool = False) -> None:
    """Short pause as if skimming the video title before clicking (0.8–6 s)."""
    if no_delay:
        return
    time.sleep(_lognormal_sleep(mean_s=1.2, sigma=0.5, min_s=0.4, max_s=6.0))


def pause_after_listing(no_delay: bool = False) -> None:
    """Pause after channel page loads — human scrolls through the video list."""
    if no_delay:
        return
    time.sleep(_lognormal_sleep(mean_s=2.5, sigma=0.7, min_s=1.0, max_s=10.0))


def pause_pre_download(no_delay: bool = False) -> None:
    """
    Pause before a download starts — simulates clicking play, letting the
    video buffer for a moment, then triggering save.  2–8 s.
    """
    if no_delay:
        return
    time.sleep(_lognormal_sleep(mean_s=3.5, sigma=0.6, min_s=1.5, max_s=12.0))
