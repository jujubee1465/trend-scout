"""TikTok Creative Center, public pages only (no login, no stealth, no proxies).
Opens the public trending page in headless Chromium and keeps the JSON the page itself loads.
If TikTok shows a captcha, a login wall or nothing, it stops and says so: then use the attended Chrome check."""
from . import store

PAGES = {
    "hashtag": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en",
    "song": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/music/pc/en",
    "creator": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/creator/pc/en",
    "video": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/pc/en",
}
BLOCKED = "blocked: TikTok asked for a check or showed nothing. Use the attended Chrome check (content-week)."


def _rows(payload: dict) -> list:
    d = payload.get("data") or {}
    for k in ("list", "videos", "sound_list", "creators", "hashtag_list"):
        if isinstance(d.get(k), list):
            return d[k]
    return []


def _clean(kind: str, r: dict) -> dict:
    if kind == "hashtag":
        return {"name": "#" + str(r.get("hashtag_name", "")), "rank": r.get("rank"), "posts": r.get("publish_cnt"),
                "views": r.get("video_views"), "industry": (r.get("industry_info") or {}).get("value"),
                "rank_change": r.get("rank_diff"), "new": r.get("rank_diff_type") == 4}
    if kind == "song":
        return {"name": r.get("title"), "artist": r.get("author"), "rank": r.get("rank"),
                "rank_change": r.get("rank_diff"), "link": r.get("link")}
    if kind == "creator":
        return {"name": r.get("nick_name"), "followers": r.get("follower_cnt"), "likes": r.get("liked_cnt"),
                "link": r.get("tt_link")}
    return {"title": r.get("title"), "duration": r.get("duration"), "link": r.get("item_url") or r.get("item_id"),
            "region": r.get("country_code")}


def trending(kind: str = "hashtag", days: int = 7, max_age_hours: float = 72) -> dict:
    """kind: hashtag | song | creator | video. Cached for max_age_hours so the page is opened rarely."""
    if kind not in PAGES:
        return {"kind": kind, "items": [], "errors": [f"kind must be one of {', '.join(PAGES)}"]}
    key = f"tiktok:{kind}:{days}"
    hit = store.cache_get(key, max_age_hours)
    if hit:
        return hit | {"cached": True}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"kind": kind, "items": [], "errors": ["playwright not installed (uv run playwright install chromium)"]}
    got: list = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(locale="en-US")

        def on_resp(r):
            if "creative_radar_api" in r.url and r.request.resource_type in ("xhr", "fetch"):
                try:
                    rows = _rows(r.json())
                    if rows:
                        got.append(rows)
                except Exception:
                    pass

        page.on("response", on_resp)
        try:
            page.goto(f"{PAGES[kind]}?period={days}&countryCode=US", wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(2500)
            text = (page.inner_text("body") or "")[:4000].lower()
        except Exception as e:
            b.close()
            return {"kind": kind, "items": [], "errors": [f"TikTok page didn't load: {type(e).__name__}"]}
        b.close()
    if not got:
        note = BLOCKED + (" (verify/captcha seen)" if ("verify" in text or "captcha" in text) else "")
        return {"kind": kind, "items": [], "errors": [note]}
    items = [_clean(kind, r) for r in max(got, key=len)]
    out = {"kind": kind, "country": "US", "days": days, "items": items, "errors": [],
           "note": "Ranks from TikTok's public Creative Center (top list only without a business sign-in). "
                   "Ranks aren't engagement counts, so these stay out of the velocity ranking."}
    store.cache_put(key, out)
    return out
