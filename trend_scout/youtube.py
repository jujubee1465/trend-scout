"""YouTube Data API v3: recent videos that beat their channel's size (views / subscribers).
Needs YOUTUBE_API_KEY (free, 10,000 units a day; one search = 100 units, details = 1 unit per 50 ids)."""
import datetime as dt

from . import score
from .common import client, hours_since, iso, line_cfg, now, secret, redact

API = "https://www.googleapis.com/youtube/v3"


def _get(http, path, key=None, **params):
    # the key goes in a header, not the URL, so it never shows up in logs or errors
    r = http.get(f"{API}/{path}", params=params, headers={"X-Goog-Api-Key": key} if key else None)
    if r.status_code != 200:
        msg = r.json().get("error", {}).get("message", r.text[:120]) if r.headers.get("content-type", "").startswith("application/json") else r.text[:120]
        raise RuntimeError(f"YouTube {path}: {r.status_code} {msg}")
    return r.json()


def _chunks(xs, n=50):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def outliers(line: str, days: int = 30, min_ratio: float = 3.0, per_query: int = 25, comments_for: int = 5,
             min_views: int | None = None) -> dict:
    key = secret("YOUTUBE_API_KEY")
    if not key:
        return {"line": line, "items": [], "errors": ["YouTube: no YOUTUBE_API_KEY in Keychain (see README: Keys)"]}
    cfg, http, errors = line_cfg(line), client(), []
    if min_views is None:  # niches.toml can set a lower floor for small niches (e.g. coaching)
        min_views = int(cfg.get("min_views", 1000))
    after = iso(now() - dt.timedelta(days=days))
    ids = []
    for q in cfg.get("youtube", []):
        try:
            res = _get(http, "search", part="id", type="video", q=q, order="viewCount", publishedAfter=after,
                       maxResults=per_query, relevanceLanguage="en", key=key)
            ids += [i["id"]["videoId"] for i in res.get("items", []) if i.get("id", {}).get("videoId")]
        except Exception as e:
            errors.append(redact(e))
    ids = list(dict.fromkeys(ids))
    vids, chans = {}, {}
    for chunk in _chunks(ids):
        try:
            for v in _get(http, "videos", part="snippet,statistics,contentDetails", id=",".join(chunk), key=key).get("items", []):
                vids[v["id"]] = v
        except Exception as e:
            errors.append(redact(e))
    cids = list({v["snippet"]["channelId"] for v in vids.values()})
    for chunk in _chunks(cids):
        try:
            for c in _get(http, "channels", part="statistics,snippet", id=",".join(chunk), key=key).get("items", []):
                chans[c["id"]] = c
        except Exception as e:
            errors.append(redact(e))
    items = []
    for vid, v in vids.items():
        st, sn = v.get("statistics", {}), v["snippet"]
        ch = chans.get(sn["channelId"], {})
        cst = ch.get("statistics", {})
        subs = None if cst.get("hiddenSubscriberCount") else int(cst.get("subscriberCount", 0) or 0)
        views, likes, comments = (int(st.get(k, 0) or 0) for k in ("viewCount", "likeCount", "commentCount"))
        posted = dt.datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
        h = hours_since(posted)
        ratio = score.outlier_ratio(views, subs)
        # a 3-subscriber channel with 90 views is noise, not a trend: require real reach too
        if ratio is None or ratio < min_ratio or views < min_views or score.is_giveaway(sn.get("title")):
            continue
        items.append({
            "source": "youtube", "id": vid, "title": sn.get("title", ""), "channel": sn.get("channelTitle", ""),
            "url": f"https://www.youtube.com/watch?v={vid}", "posted": iso(posted), "hours_old": round(h, 1),
            "duration": v.get("contentDetails", {}).get("duration"),
            "metrics": {"views": views, "likes": likes, "comments": comments, "subscribers": subs,
                        "views_per_hour": round(views / h, 1)},
            "outlier": ratio, "velocity": score.velocity(likes, comments, 0, h),
        })
    items.sort(key=lambda x: (x["outlier"], x["metrics"]["views_per_hour"]), reverse=True)
    for it in items[:comments_for]:
        try:
            res = _get(http, "commentThreads", part="snippet", videoId=it["id"], order="relevance", maxResults=10,
                       textFormat="plainText", key=key)
            cs = [c["snippet"]["topLevelComment"]["snippet"].get("textDisplay", "") for c in res.get("items", [])]
            it["top_comments"] = [c[:240] for c in cs]
            it["intent"] = score.intent_ratio(cs)
        except Exception as e:
            errors.append(f"comments {it['id']}: {redact(e)[:80]}")
    return {"line": line, "items": items, "errors": errors,
            "quota_note": f"about {100 * len(cfg.get('youtube', [])) + len(ids) // 50 + len(cids) // 50 + 2 + comments_for} units used"}
