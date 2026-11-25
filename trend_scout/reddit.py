"""Reddit: top posts of the week per line, read-only.
With REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET (a personal "script" app) it uses the official OAuth API
(app-only token). Without them it falls back to the public .json pages, slowly (one request every 2 s)."""
import datetime as dt
import time

from . import score
from .common import client, hours_since, iso, line_cfg, secret

_last = [0.0]


def _pace(seconds: float) -> None:
    wait = _last[0] + seconds - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()


class Reddit:
    def __init__(self):
        self.http = client()
        cid, sec = secret("REDDIT_CLIENT_ID"), secret("REDDIT_CLIENT_SECRET")
        self.oauth = False
        if cid and sec:
            r = self.http.post("https://www.reddit.com/api/v1/access_token", auth=(cid, sec),
                               data={"grant_type": "client_credentials"})
            if r.status_code == 200 and r.json().get("access_token"):
                self.http.headers["Authorization"] = "Bearer " + r.json()["access_token"]
                self.oauth = True
        self.base = "https://oauth.reddit.com" if self.oauth else "https://www.reddit.com"

    def get(self, path: str, **params):
        _pace(0.7 if self.oauth else 2.0)
        url = self.base + path + ("" if self.oauth else ".json")
        r = self.http.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def top(self, sub: str, t: str, limit: int) -> list[dict]:
        data = self.get(f"/r/{sub}/top", t=t, limit=limit, raw_json=1)
        return [c["data"] for c in data.get("data", {}).get("children", [])]

    def comments(self, post_id: str, n: int = 10) -> list[str]:
        data = self.get(f"/comments/{post_id}", sort="top", limit=n, depth=1, raw_json=1)
        if not isinstance(data, list) or len(data) < 2:
            return []
        return [c["data"].get("body", "") for c in data[1]["data"]["children"] if c.get("kind") == "t1"][:n]


def top(line: str, days: int = 7, limit: int = 25, comments_for: int = 8) -> dict:
    cfg = line_cfg(line)
    t = "day" if days <= 1 else "week" if days <= 7 else "month"
    rd, items, errors = Reddit(), [], []
    if not rd.oauth:  # Reddit answers 403 to every keyless read: don't hammer it, just say so once
        return {"line": line, "mode": "off", "items": [],
                "errors": ["Reddit not connected yet: needs REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET (README: Keys)"]}
    for sub in cfg.get("subs", []):
        try:
            posts = rd.top(sub, t, limit)
        except Exception as e:  # one bad sub never sinks the run
            errors.append(f"r/{sub}: {type(e).__name__} {getattr(getattr(e, 'response', None), 'status_code', '')}".strip())
            continue
        for p in posts:
            if p.get("stickied") or p.get("over_18"):
                continue
            created = dt.datetime.fromtimestamp(p["created_utc"], dt.timezone.utc)
            h = hours_since(created)
            items.append({
                "source": "reddit", "sub": sub, "id": p["id"], "title": p.get("title", ""),
                "url": "https://www.reddit.com" + p.get("permalink", ""),
                "posted": iso(created), "hours_old": round(h, 1),
                "metrics": {"score": p.get("score", 0), "comments": p.get("num_comments", 0),
                            "upvote_ratio": p.get("upvote_ratio")},
                "velocity": score.velocity(p.get("score", 0), p.get("num_comments", 0), 0, h),
                "text": (p.get("selftext") or "")[:400],
            })
    items.sort(key=lambda x: x["velocity"], reverse=True)
    items = items[:limit]
    for it in items[:comments_for]:  # comments cost a request each: only the leaders
        try:
            cs = rd.comments(it["id"])
            it["top_comments"] = [c[:240] for c in cs]
            it["intent"] = score.intent_ratio(cs)
        except Exception as e:
            errors.append(f"comments {it['id']}: {type(e).__name__}")
    if not rd.oauth and errors and not items:
        errors.insert(0, "Reddit refuses keyless reads: add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET (README: Keys)")
    return {"line": line, "mode": "oauth" if rd.oauth else "public-json", "items": items, "errors": errors}
