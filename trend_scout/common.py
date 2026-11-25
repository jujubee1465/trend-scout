"""Shared bits: niches, secrets (macOS Keychain, never files), HTTP, time."""
import datetime as dt
import os
import subprocess
import tomllib
from pathlib import Path

import logging

import httpx

# httpx logs every request URL at INFO; never let a key or token reach a log or a tool result
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

ROOT = Path(__file__).resolve().parent.parent
UA = "trend-scout/0.1 (personal read-only research tool; macOS)"
KEYCHAIN_SERVICE = os.environ.get("TREND_SCOUT_KEYCHAIN", "enterprise-os")


def niches() -> dict:
    return tomllib.loads((ROOT / "niches.toml").read_text())


def line_cfg(line: str) -> dict:
    n = niches()
    if line not in n:
        raise ValueError(f"unknown line '{line}'. Known: {', '.join(n)}")
    return n[line]


def secret(name: str) -> str | None:
    """Env var first (for tests/CI), then Keychain: service enterprise-os, account <name>."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", name, "-w"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def client(**kw) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA}, timeout=20, follow_redirects=True, **kw)


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def hours_since(ts: dt.datetime) -> float:
    return max((now() - ts).total_seconds() / 3600, 1.0)


def iso(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def redact(text: str) -> str:
    """Strip any stored secret (and key=/token= query values) out of an error message."""
    import re
    text = re.sub(r"((?:key|access_token|input_token|client_secret|fb_exchange_token)=)[^&\s'\"]+", r"\1***", str(text))
    for name in ("YOUTUBE_API_KEY", "IG_ACCESS_TOKEN", "IG_APP_SECRET", "REDDIT_CLIENT_SECRET"):
        try:
            v = secret(name)
        except Exception:
            v = None
        if v and len(v) > 8:
            text = text.replace(v, "***")
    return text
