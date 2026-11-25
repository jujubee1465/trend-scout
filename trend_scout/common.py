"""Shared bits: niches, secrets (macOS Keychain, never files), HTTP, time."""
import datetime as dt
import os
import subprocess
import tomllib
from pathlib import Path

import httpx

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
