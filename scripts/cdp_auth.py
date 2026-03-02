#!/usr/bin/env python3
"""
Dynamic cookie fetching from OpenClaw browser via CDP.

Instead of relying on a manually-exported state.json (which expires),
this module fetches fresh YouMind cookies from the OpenClaw browser
(a running Chromium instance at CDP port 18800) on every call.

Behavior:
  - Cookies are cached locally in data/cdp_cache.json with a 5-hour TTL
  - Falls back to state.json if the browser is not running
  - No extra dependencies: uses patchright (already required)

Similar to how birdx reads Twitter cookies from Chrome, this reads YouMind
cookies from the live OpenClaw browser via CDP.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────────

CDP_HTTP = "http://127.0.0.1:18800"
CACHE_TTL_SECONDS = 5 * 3600  # 5 hours

_SKILL_DIR = Path(__file__).parent.parent
_DATA_DIR = _SKILL_DIR / "data"
CACHE_FILE = _DATA_DIR / "cdp_cache.json"

YOUMIND_DOMAINS = ("youmind.com", "gooo.ai")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_cache() -> Optional[str]:
    """Return cached cookie string if still within TTL, else None."""
    try:
        if not CACHE_FILE.exists():
            return None
        data = json.loads(CACHE_FILE.read_text())
        age = time.time() - data.get("saved_at", 0)
        if age < CACHE_TTL_SECONDS:
            return data.get("cookie_str") or None
    except Exception:
        pass
    return None


def _save_cache(cookie_str: str) -> None:
    """Persist cookie string with current timestamp."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps({"cookie_str": cookie_str, "saved_at": time.time()}, indent=2)
        )
    except Exception:
        pass


def _fetch_from_cdp() -> Optional[str]:
    """
    Connect to the OpenClaw browser via CDP and extract YouMind cookies.
    Uses patchright's connect_over_cdp() which accepts an HTTP endpoint
    and handles the WebSocket upgrade internally.
    """
    try:
        from patchright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_HTTP)
            try:
                contexts = browser.contexts
                if not contexts:
                    return None
                cookies = contexts[0].cookies(["https://youmind.com"])
                pairs = [
                    f"{c['name']}={c['value']}"
                    for c in cookies
                    if c.get("name") and c.get("value") is not None
                    and any(d in c.get("domain", "") for d in YOUMIND_DOMAINS)
                ]
                return "; ".join(pairs) if pairs else None
            finally:
                browser.close()

    except Exception as exc:
        print(f"[cdp_auth] CDP fetch failed: {exc}", file=sys.stderr)
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def is_cdp_available() -> bool:
    """Return True if the OpenClaw browser CDP endpoint is reachable."""
    try:
        with urllib.request.urlopen(f"{CDP_HTTP}/json/version", timeout=2) as resp:
            data = json.loads(resp.read())
            return bool(data.get("Browser"))
    except Exception:
        return False


def get_cdp_cookie_str(force_refresh: bool = False) -> Optional[str]:
    """
    Return a 'name=value; ...' cookie string for youmind.com.

    Strategy:
      1. Return cached value if within TTL (unless force_refresh=True)
      2. Fetch live cookies from CDP
      3. Cache and return, or None if browser is unavailable

    Args:
        force_refresh: Skip cache and always hit CDP.
    """
    if not force_refresh:
        cached = _load_cache()
        if cached:
            return cached

    cookie_str = _fetch_from_cdp()
    if cookie_str:
        _save_cache(cookie_str)

    return cookie_str


def invalidate_cache() -> None:
    """Remove the CDP cookie cache (forces fresh fetch on next call)."""
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
    except Exception:
        pass


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CDP cookie manager for YouMind skill")
    parser.add_argument("--refresh", action="store_true", help="Force refresh from CDP")
    parser.add_argument("--status", action="store_true", help="Show CDP + cache status")
    args = parser.parse_args()

    if args.status:
        cdp_ok = is_cdp_available()
        print(f"CDP ({CDP_HTTP}): {'✅ available' if cdp_ok else '❌ not available'}")
        if CACHE_FILE.exists():
            try:
                cache_data = json.loads(CACHE_FILE.read_text())
                age_min = (time.time() - cache_data.get("saved_at", 0)) / 60
                preview = (cache_data.get("cookie_str") or "")[:60]
                print(f"Cache: {age_min:.0f} min old | {preview}...")
            except Exception:
                print("Cache: unreadable")
        else:
            print("Cache: none")
    else:
        cookie_str = get_cdp_cookie_str(force_refresh=args.refresh)
        if cookie_str:
            print(f"✅ Cookies ({len(cookie_str)} chars): {cookie_str[:80]}...")
        else:
            print("❌ No cookies available via CDP")
