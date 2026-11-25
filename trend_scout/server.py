"""trend-scout MCP server. Every tool only reads public or official data; nothing posts, follows or messages."""
import os

from mcp.server.fastmcp import FastMCP

from . import hooks, instagram, reddit, score, store, tiktok, youtube
from .common import niches

mcp = FastMCP("trend-scout")
UNATTENDED = os.environ.get("ENTERPRISE_HEADLESS") == "1"


def _lines() -> str:
    return ", ".join(niches())


@mcp.tool()
def reddit_top(line: str, days: int = 7, limit: int = 25) -> dict:
    """Top Reddit posts of the last `days` across one line's subreddits, ranked by velocity
    ((comments*2 + score) / hours^1.5). The leaders carry their top 10 comments and an intent ratio
    (share asking how/where/which or tagging a friend). Lines: see niches.toml."""
    out = reddit.top(line, days, limit)
    store.remember(out["items"], line)
    return out


@mcp.tool()
def youtube_outliers(line: str, days: int = 30, min_ratio: float = 3.0, min_views: int | None = None) -> dict:
    """Videos from the last `days` for one line whose views are at least `min_ratio` x the channel's
    subscribers (and at least `min_views` views; default from niches.toml, else 1,000), with views per hour, the top comments and an intent ratio. Costs ~100 API units per search phrase."""
    out = youtube.outliers(line, days, min_ratio, min_views=min_views)
    store.remember(out["items"], line)
    return out


@mcp.tool()
def video_hook(url: str) -> dict:
    """The first ~3 seconds of speech in a video, as words. YouTube uses captions. A public TikTok or Instagram
    Reel link (one at a time, pasted by the user) is transcribed on this Mac with Whisper; the audio is deleted after.
    Returns hook=None with a note rather than guessing."""
    if UNATTENDED and not hooks.youtube_id(url):
        return {"url": url, "hook": None, "note": "non-YouTube links are transcribed only in an attended session"}
    return hooks.hook(url)


@mcp.tool()
def ig_hashtag_top(line: str, limit: int = 25) -> dict:
    """Instagram top and recent posts for one line's hashtags (official Graph API): likes, comments, caption hook,
    link. Meta allows 30 different hashtags per rolling 7 days; extra tags are refused, not sent."""
    out = instagram.hashtag_top(line, limit)
    store.remember(out["items"], line)
    return out


@mcp.tool()
def ig_creator(username: str) -> dict:
    """An Instagram business/creator account's followers and recent posts (official Business Discovery),
    flagging posts at 3x or more of that account's median engagement."""
    return instagram.creator(username)


@mcp.tool()
def tiktok_trending(kind: str = "hashtag", days: int = 7) -> dict:
    """TikTok Creative Center public trending list (kind: hashtag, song, creator, video), US. No login. Cached 3 days.
    If TikTok blocks the read it says so; then use the attended Chrome check."""
    return tiktok.trending(kind, days)


@mcp.tool()
def scout_brief(line: str, include_seen: bool = False) -> dict:
    """The week's top 10 for one line across Reddit, YouTube and Instagram, interleaved by rank within each source,
    leaving out anything shown in an earlier brief (include_seen=True to keep them). Plus this week's cached TikTok
    trending hashtags (listed apart: ranks, not counts). Each item keeps its numbers and its link."""
    sources, errors = [], []
    for name, fn, key in (("reddit", lambda: reddit.top(line), "velocity"),
                          ("youtube", lambda: youtube.outliers(line), "outlier"),
                          ("instagram", lambda: instagram.hashtag_top(line), "velocity")):
        try:
            out = fn()
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
            continue
        errors += out.get("errors", [])
        items = out["items"]
        store.remember(items, line)
        if not include_seen:
            items = [i for i in items if not i.get("briefed_before")]
        score.rank_norm(items, key)
        for i in items:
            i["rank_score"] = round(i["rank_score"] + 0.25 * (i.get("intent") or 0), 3)
        sources.append(items)
    top = sorted((i for s in sources for i in s), key=lambda x: x["rank_score"], reverse=True)[:10]
    store.mark_briefed([i["url"] for i in top])
    for i in top:
        i.pop("text", None)
        i["top_comments"] = i.get("top_comments", [])[:3]
    tt = store.cache_get("tiktok:hashtag:7", 24 * 7)
    return {"line": line, "top": top, "tiktok_hashtags_this_week": (tt or {}).get("items", [])[:20] or None,
            "errors": errors, "lines": _lines()}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
