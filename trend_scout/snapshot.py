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

from . import brief, store
from .common import niches

KEEP = ("source", "title", "url", "channel", "sub", "hashtag", "type", "posted", "hours_old", "hook",
        "outlier", "velocity", "intent", "metrics", "top_comments")


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
        items = [{k: i[k] for k in KEEP if i.get(k) is not None} | {"new": i["url"] not in before} for i in b["top"]]
        snap["lines"][line] = {"items": items, "errors": b["errors"]}
        for src, st in b["sources"].items():  # a source counts as working if it worked for any line
            if snap["sources"].get(src) != "ok":
                snap["sources"][src] = st
    tt = store.cache_get("tiktok:hashtag:7", 24 * 7)
    snap["sources"]["tiktok"] = "ok" if tt else "blocked"
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
