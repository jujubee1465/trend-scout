"""One line's top 10 across Reddit, YouTube and Instagram, shared by the scout_brief tool and the snapshot command."""
from . import instagram, reddit, score, store, youtube
from .common import redact


def build(line: str, include_seen: bool = False, mark: bool = True, limit: int = 10) -> dict:
    """Interleave the sources by rank within each one (so a huge YouTube number can't drown Instagram), nudged up by
    comment intent. mark=True records the items as briefed, so the next brief skips them unless include_seen."""
    sources, errors, status = [], [], {}
    for name, fn, key in (("reddit", lambda: reddit.top(line), "velocity"),
                          ("youtube", lambda: youtube.outliers(line), "outlier"),
                          ("instagram", lambda: instagram.hashtag_top(line), "velocity")):
        try:
            out = fn()
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {redact(e)[:120]}")
            status[name] = "error"
            continue
        errors += out.get("errors", [])
        items = out["items"]
        status[name] = "off" if out.get("mode") == "off" else "ok"
        store.remember(items, line)
        if not include_seen:
            items = [i for i in items if not i.get("briefed_before")]
        score.rank_norm(items, key)
        for i in items:
            i["rank_score"] = round(i["rank_score"] + 0.25 * (i.get("intent") or 0), 3)
        sources.append(items)
    top = sorted((i for s in sources for i in s), key=lambda x: x["rank_score"], reverse=True)[:limit]
    if mark:
        store.mark_briefed([i["url"] for i in top])
    for i in top:
        i.pop("text", None)
        i["top_comments"] = i.get("top_comments", [])[:3]
    return {"line": line, "top": top, "errors": errors, "sources": status}
