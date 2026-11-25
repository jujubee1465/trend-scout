"""Instagram through Meta's official Graph API (no scraping, no login automation).
Needs an Instagram Business/Creator account linked to a Facebook Page and a free Meta developer app.
Keychain: IG_ACCESS_TOKEN (long-lived user token, ~60 days) and IG_USER_ID (the Instagram business account id).
Limits: 30 unique hashtags per rolling 7 days (tracked in store.py), and Business Discovery sees only
business/creator accounts."""
import datetime as dt

from . import score, store
from .common import client, hours_since, iso, line_cfg, secret, redact

GRAPH = "https://graph.facebook.com/v21.0"
MEDIA_FIELDS = "id,caption,like_count,comments_count,media_type,permalink,timestamp,media_url,children{media_url,media_type}"


def _creds():
    tok, uid = secret("IG_ACCESS_TOKEN"), secret("IG_USER_ID")
    return (tok, uid) if tok and uid else (None, None)


def _get(http, path, access_token=None, **params):
    # the token goes in a header, not the URL, so it never shows up in logs or errors
    r = http.get(f"{GRAPH}/{path}", params=params,
                 headers={"Authorization": f"Bearer {access_token}"} if access_token else None)
    j = r.json() if r.headers.get("content-type", "").startswith(("application/json", "text/javascript")) else {}
    if r.status_code != 200 or "error" in j:
        raise RuntimeError(f"Instagram {path.split('/')[-1]}: {j.get('error', {}).get('message', r.text[:120])}")
    return j


def token_status() -> dict:
    tok, uid = _creds()
    if not tok:
        return {"connected": False, "note": "IG_ACCESS_TOKEN / IG_USER_ID not in Keychain (see README: Instagram setup)"}
    try:
        d = _get(client(), "debug_token", input_token=tok, access_token=tok).get("data", {})
    except Exception as e:
        return {"connected": False, "note": redact(e)}
    exp = d.get("expires_at") or d.get("data_access_expires_at")
    out = {"connected": bool(d.get("is_valid")), "scopes": d.get("scopes", [])}
    if exp:
        when = dt.datetime.fromtimestamp(exp, dt.timezone.utc)
        days = (when - dt.datetime.now(dt.timezone.utc)).days
        out |= {"expires": when.date().isoformat(), "days_left": days}
        if days <= 7:
            out["warning"] = f"Instagram token expires in {days} days: refresh it (README: Instagram setup)."
    return out


def _media_item(m: dict, extra: dict) -> dict:
    ts = dt.datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")) if m.get("timestamp") else None
    h = hours_since(ts) if ts else None
    likes, comments = m.get("like_count"), m.get("comments_count")
    cap = (m.get("caption") or "").strip()
    return {
        "source": "instagram", "id": m["id"], "url": m.get("permalink") or f"https://www.instagram.com/p/{m['id']}",
        "title": cap.split("\n")[0][:160], "hook": cap.split("\n")[0][:160] or None, "type": m.get("media_type"),
        "caption": cap[:2200] or None, "thumb": _cover(m),
        "posted": iso(ts) if ts else None, "hours_old": round(h, 1) if h else None,
        "metrics": {"likes": likes, "comments": comments},
        "velocity": score.velocity(likes or 0, comments or 0, 0, h) if h and likes is not None else None, **extra,
    }


def _cover(m: dict) -> str | None:
    """An image URL to read cover text from. Hashtag results give media_url for images and carousels' first
    image; videos usually give none (the API hides other accounts' video covers), so those return None."""
    if m.get("media_type") == "IMAGE" and m.get("media_url"):
        return m["media_url"]
    for ch in (m.get("children") or {}).get("data", []):
        if ch.get("media_type") == "IMAGE" and ch.get("media_url"):
            return ch["media_url"]
    return m.get("thumbnail_url")


def hashtag_top(line: str, limit: int = 25, tags: list[str] | None = None,
                min_age_hours: float = 12, min_likes: int = 50) -> dict:
    tok, uid = _creds()
    if not tok:
        return {"line": line, "items": [], "errors": ["Instagram: not connected (README: Instagram setup)"]}
    tags = [t.lstrip("#").lower() for t in (tags or line_cfg(line).get("instagram", []))]
    allowed, refused = store.ig_tag_budget(tags)
    http, items, errors = client(), [], []
    if refused:
        errors.append(f"Instagram weekly hashtag limit (30) reached; skipped: {', '.join('#' + t for t in refused)}")
    for tag in allowed:
        try:
            hid = _get(http, "ig_hashtag_search", user_id=uid, q=tag, access_token=tok)["data"][0]["id"]
            store.ig_tag_used(tag)
            for edge in ("top_media", "recent_media"):
                res = _get(http, f"{hid}/{edge}", user_id=uid, fields=MEDIA_FIELDS, limit=limit, access_token=tok)
                items += [_media_item(m, {"hashtag": tag, "edge": edge}) for m in res.get("data", [])]
        except Exception as e:
            errors.append(f"#{tag}: {redact(e)}")
    uniq = {}
    for it in items:
        uniq.setdefault(it["url"], it)
    # an hour-old post with 3 likes isn't a trend yet, and giveaways collect comments from entries, not interest
    items = [i for i in uniq.values()
             if (i.get("hours_old") or 0) >= min_age_hours and (i["metrics"].get("likes") or 0) >= min_likes
             and not score.is_giveaway(i.get("title"))]
    items = sorted(items, key=lambda x: x.get("velocity") or 0, reverse=True)[:limit]
    st = token_status()
    if st.get("warning"):
        errors.append(st["warning"])
    return {"line": line, "items": items, "errors": errors}


def creator(username: str, posts: int = 25) -> dict:
    tok, uid = _creds()
    if not tok:
        return {"username": username, "items": [], "errors": ["Instagram: not connected (README: Instagram setup)"]}
    u = username.lstrip("@")
    fields = f"business_discovery.username({u}){{username,name,followers_count,media_count,media.limit({posts}){{{MEDIA_FIELDS}}}}}"
    try:
        bd = _get(client(), uid, fields=fields, access_token=tok)["business_discovery"]
    except Exception as e:
        hint = ("the token needs the read-only instagram_manage_insights permission (README: Instagram setup)"
                if "(#10)" in str(e) else "Business Discovery only sees business/creator accounts")
        return {"username": u, "items": [], "errors": [f"{redact(e)} ({hint})"]}
    media = bd.get("media", {}).get("data", [])
    items = [_media_item(m, {"account": u}) for m in media]
    eng = [(it["metrics"]["likes"] or 0) + 2 * (it["metrics"]["comments"] or 0) for it in items]
    hot = set(score.median_outliers(eng, 3.0))
    for i, it in enumerate(items):
        it["engagement"] = eng[i]
        it["outlier"] = i in hot
    return {"username": u, "followers": bd.get("followers_count"), "media_count": bd.get("media_count"),
            "items": items, "outliers": [items[i] for i in sorted(hot)], "errors": []}
