"""The hook printed on a cover: on-device OCR (Apple Vision via ocrmac) of a thumbnail or post image.

The image goes to a temp folder and is deleted right after; only the words come back. No cloud OCR."""
import re
import tempfile
from pathlib import Path

from . import store
from .common import client

HANDLE = re.compile(r"^@\w|\b(www\.|\.com\b|\.co\b|https?://)", re.I)
WATERMARK = re.compile(r"^(tiktok|instagram|youtube|reels?|shorts|subscribe|follow)$", re.I)


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", t.lower())


def clean(lines: list[tuple]) -> str | None:
    """Keep what reads like a hook: big, confident 1-12 word lines, no @handles, links, platform watermarks or lone
    numbers. `lines` are (text, confidence[, height]) in reading order; height is the share of the image's height,
    and cover hooks are big type (small text is usually a screenshot's UI, which OCR garbles)."""
    keep = []
    for row in lines:
        text, conf = row[0], row[1]
        h = row[2] if len(row) > 2 else None
        t = " ".join(str(text).split())
        if (h is not None and h < 0.055) or conf < 0.6 or not t or HANDLE.search(t) or WATERMARK.match(t) or re.fullmatch(r"[\d:.,%$ ]+", t):
            continue
        if not 1 <= len(t.split()) <= 12 or len(t) < 4:
            continue
        # OCR often re-reads part of a big word (a "HIS" or "ANK" under "HIS BOAT SANK"): skip echoes of kept lines
        if any(_norm(t) in _norm(k) or _norm(k) in _norm(t) for k in keep) or (len(t.split()) == 1 and not t.isupper() and len(t) < 5):
            continue
        keep.append(t)
    out = " / ".join(keep[:4]).strip()
    return out[:140] or None


def _ocr(path: Path) -> list[tuple[str, float]]:
    from ocrmac import ocrmac
    res = ocrmac.OCR(str(path), recognition_level="accurate").recognize()
    # each result is (text, confidence, bbox[x, y, w, h]) with y measured from the bottom: read top to bottom
    res = sorted(res, key=lambda r: -(r[2][1] + r[2][3]))
    return [(r[0], float(r[1]), float(r[2][3])) for r in res]


def cover_text(image_url: str | None) -> str | None:
    """Words on the cover image, cleaned. Cached per image URL for 30 days ("" = looked, nothing found)."""
    if not image_url:
        return None
    key = "cover:" + image_url
    hit = store.cache_get(key, 24 * 30)
    if hit is not None:
        return hit.get("text") or None
    text = None
    try:
        r = client().get(image_url, timeout=15)
        r.raise_for_status()
        with tempfile.TemporaryDirectory(prefix="trend-scout-") as tmp:
            p = Path(tmp) / "cover.jpg"
            p.write_bytes(r.content)
            text = clean(_ocr(p))
    except Exception:
        return None  # not cached: a network blip shouldn't stick for a month
    store.cache_put(key, {"text": text or ""})
    return text
