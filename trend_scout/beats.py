"""Timed caption lines from the start of a YouTube video, for writing a beat outline (hook, setup, payoff, CTA).
For the outline writer only: never shown or published as-is."""
from .hooks import CaptionsBlocked, captions, youtube_id


def transcript(url: str, seconds: int = 90) -> list[dict] | None:
    vid = youtube_id(url)
    if not vid:
        return None
    segs = captions(vid)  # raises CaptionsBlocked while YouTube is limiting caption reads
    lines = [{"t": round(t, 1), "text": text} for t, text in (segs or []) if t <= seconds]
    return lines or None


if __name__ == "__main__":  # python -m trend_scout.beats  < ["url", ...]  →  {"url": [lines] | null}
    import json
    import sys
    urls, out = json.load(sys.stdin), {}
    for u in urls[:10]:
        try:
            out[u] = transcript(u)
        except CaptionsBlocked:
            out = {"_blocked": True}
            break
    print(json.dumps(out))
