"""SQLite memory: what we've already shown (dedupe), the Instagram hashtag budget, and a small cache."""
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

DB = Path(os.environ.get("TREND_SCOUT_DB", Path.home() / "Library/Application Support/trend-scout/scout.db"))

SCHEMA = """
create table if not exists seen (
  url text primary key, source text, line text, title text,
  first_seen text, last_seen text, times_seen integer default 1,
  briefed_at text, metrics text);
create table if not exists ig_tags (tag text, used_at text);
create table if not exists cache (key text primary key, saved_at text, value text);
"""


def db() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def remember(items: list[dict], line: str) -> None:
    """Record every item fetched; bump times_seen on repeats. Adds item['seen_before'] and item['times_seen']."""
    with db() as c:
        for it in items:
            row = c.execute("select times_seen, briefed_at from seen where url=?", (it["url"],)).fetchone()
            m = json.dumps(it.get("metrics", {}))
            if row:
                c.execute("update seen set last_seen=?, times_seen=times_seen+1, metrics=? where url=?", (_now(), m, it["url"]))
                it["times_seen"], it["briefed_before"] = row["times_seen"] + 1, bool(row["briefed_at"])
            else:
                c.execute("insert into seen(url,source,line,title,first_seen,last_seen,metrics) values(?,?,?,?,?,?,?)",
                          (it["url"], it["source"], line, (it.get("title") or "")[:300], _now(), _now(), m))
                it["times_seen"], it["briefed_before"] = 1, False


def mark_briefed(urls: list[str]) -> None:
    with db() as c:
        c.executemany("update seen set briefed_at=? where url=?", [(_now(), u) for u in urls])


def ig_tag_budget(tags: list[str], limit: int = 30) -> tuple[list[str], list[str]]:
    """Split tags into (allowed, refused) under Meta's 30 unique hashtags per rolling 7 days.
    A tag already searched in the window is free to search again."""
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
    with db() as c:
        used = {r["tag"] for r in c.execute("select distinct tag from ig_tags where used_at>=?", (since,))}
    allowed, refused = [], []
    for t in tags:
        if t in used or len(used) < limit:
            allowed.append(t)
            used.add(t)
        else:
            refused.append(t)
    return allowed, refused


def ig_tag_used(tag: str) -> None:
    with db() as c:
        c.execute("insert into ig_tags values(?,?)", (tag, _now()))


def cache_get(key: str, max_age_hours: float):
    with db() as c:
        r = c.execute("select saved_at, value from cache where key=?", (key,)).fetchone()
    if not r:
        return None
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(r["saved_at"])
    return json.loads(r["value"]) if age.total_seconds() < max_age_hours * 3600 else None


def cache_put(key: str, value) -> None:
    with db() as c:
        c.execute("insert or replace into cache values(?,?,?)", (key, _now(), json.dumps(value)))
