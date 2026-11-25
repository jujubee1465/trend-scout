"""Write each line's current top 10 to a JSON file that a dashboard can show without calling any API itself.

  python -m trend_scout.snapshot --out PATH [--lines a,b,c]

Doesn't mark anything as briefed (that stays with the weekly brief). Items not in the previous snapshot get new=True.
Exit 0 when at least one source answered."""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import brief, hooks, store, thumbs
from .common import niches

KEEP = ("source", "title", "url", "channel", "sub", "hashtag", "type", "posted", "hours_old", "hook",
        "outlier", "velocity", "intent", "metrics", "top_comments", "caption", "thumb", "thumb_hook", "spoken_hook")


def _spoken(url: str) -> str | None:
    """First ~3 s of speech from YouTube captions (no download). Cached 30 days; "" = no captions."""
    vid = hooks.youtube_id(url)
    if not vid:
        return None
    hit = store.cache_get("spoken:" + vid, 24 * 30)
    if hit is not None:
        return hit.get("text") or None
    try:
        segs = hooks.captions(vid)
    except hooks.CaptionsBlocked:
        return None  # YouTube is limiting caption reads: try again next refresh, don't cache "none"
    text = hooks._words(segs) if segs else None
    store.cache_put("spoken:" + vid, {"text": text or ""})
    return text


def enrich(items: list[dict]) -> None:
    """The hook can sit on the cover, in the caption or in the first words spoken: read all three for the top items.
    Instagram/TikTok audio is never fetched here (that only happens when the user taps for one)."""
    for i in items:
        i["thumb_hook"] = thumbs.cover_text(i.get("thumb"))
        if i.get("source") == "youtube":
            i["spoken_hook"] = _spoken(i["url"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--lines", default="", help="comma-separated; default every line in niches.toml")
    a = ap.parse_args(argv)
    out = Path(a.out)
    lines = [x for x in a.lines.split(",") if x] or list(niches())
    try:
        before = {i["url"] for ln in json.loads(out.read_text()).get("lines", {}).values() for i in ln.get("items", [])}
    except (OSError, ValueError, AttributeError):
        before = set()
    snap = {"updated": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "lines": {}, "sources": {}}
    for line in lines:
        b = brief.build(line, include_seen=True, mark=False)
        enrich(b["top"])
        items = [{k: i[k] for k in KEEP if i.get(k) is not None} | {"new": i["url"] not in before} for i in b["top"]]
        snap["lines"][line] = {"items": items, "errors": b["errors"]}
        for src, st in b["sources"].items():  # a source counts as working if it worked for any line
            if snap["sources"].get(src) != "ok":
                snap["sources"][src] = st
    tt = store.cache_get("tiktok:hashtag:7", 24 * 7)
    snap["sources"]["tiktok"] = "ok" if tt else "blocked"
    snap["captions_limited"] = bool(store.cache_get("yt-captions-blocked", hooks.BLOCK_HOURS))
    snap["tiktok_hashtags"] = (tt or {}).get("items", [])[:20]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, indent=1, ensure_ascii=False))
    os.replace(tmp, out)
    ok = any(v == "ok" for v in snap["sources"].values())
    print(f"trend snapshot: {sum(len(v['items']) for v in snap['lines'].values())} items, {len(lines)} lines, "
          f"sources {snap['sources']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
