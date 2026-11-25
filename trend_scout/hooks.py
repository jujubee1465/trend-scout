"""The first ~3 seconds of a video, in words.
YouTube: captions first (no download). Anything else the user pastes (a public TikTok or Reel), or a video with no
captions: yt-dlp fetches only the first 10 s of audio to a temp folder, mlx-whisper transcribes it on this Mac,
and the audio is deleted. One link per call; no bulk downloading."""
import re
import tempfile
from pathlib import Path

SECONDS, MAX_WORDS = 3.5, 14
WHISPER_MODEL = "mlx-community/whisper-small-mlx"


def youtube_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def _words(segments: list[tuple[float, str]]) -> str:
    out = []
    for start, text in segments:
        if start > SECONDS and out:
            break
        out += text.split()
    return " ".join(out[:MAX_WORDS])


class CaptionsBlocked(Exception):
    """YouTube refused caption reads from this machine (too many requests). We back off; no proxies or workarounds."""


BLOCK_HOURS = 24


def captions(vid: str) -> list[tuple[float, str]] | None:
    """Timed caption lines, None when the video has none. Raises CaptionsBlocked while YouTube is limiting us
    (then nothing is asked again for BLOCK_HOURS)."""
    from . import store
    if store.cache_get("yt-captions-blocked", BLOCK_HOURS):
        raise CaptionsBlocked
    from youtube_transcript_api import YouTubeTranscriptApi
    try:
        fetched = YouTubeTranscriptApi().fetch(vid, languages=["en", "en-US", "en-GB"])
        return [(s.start, " ".join(s.text.split())) for s in fetched]
    except Exception as e:
        if type(e).__name__ in ("IpBlocked", "RequestBlocked", "TooManyRequests", "YouTubeRequestFailed"):
            store.cache_put("yt-captions-blocked", {"why": type(e).__name__})
            raise CaptionsBlocked from None
        return None


def from_captions(vid: str) -> str | None:
    try:
        segs = captions(vid)
    except CaptionsBlocked:
        return None
    return _words(segs) if segs else None


def from_audio(url: str) -> str | None:
    try:
        import mlx_whisper
        import yt_dlp
        from yt_dlp.utils import download_range_func
    except ImportError:
        return None
    with tempfile.TemporaryDirectory(prefix="trend-scout-") as tmp:
        opts = {"format": "bestaudio/best", "outtmpl": str(Path(tmp) / "a.%(ext)s"), "quiet": True, "noprogress": True,
                "no_warnings": True, "noplaylist": True, "download_ranges": download_range_func(None, [(0, 10)]),
                "force_keyframes_at_cuts": False}
        try:
            with yt_dlp.YoutubeDL(opts) as y:
                y.download([url])
        except Exception:
            return None
        files = list(Path(tmp).glob("a.*"))
        if not files:
            return None
        res = mlx_whisper.transcribe(str(files[0]), path_or_hf_repo=WHISPER_MODEL, word_timestamps=True, language="en")
        words = [(w["start"], w["word"]) for seg in res.get("segments", []) for w in seg.get("words", [])]
        text = _words(words) or None
        # on music or silence Whisper tends to invent a sign-off ("Thanks for watching"): treat as no speech
        if text and text.strip(" .!,").lower() in {"thanks", "thank you", "thanks for watching", "thank you for watching", "you", "bye"}:
            return None
        return text


def hook(url: str, allow_audio: bool = True) -> dict:
    vid = youtube_id(url)
    if vid:
        text = from_captions(vid)
        if text:
            return {"url": url, "hook": text, "method": "captions"}
    if not allow_audio:
        return {"url": url, "hook": None, "method": "none", "note": "no captions; audio transcription is off here"}
    text = from_audio(url)
    if text:
        return {"url": url, "hook": text, "method": "whisper (on device)"}
    return {"url": url, "hook": None, "method": "none", "note": "no captions and no speech found (or the link isn't public)"}


if __name__ == "__main__":  # python -m trend_scout.hooks URL  →  one JSON line (used by a dashboard's "Get spoken hook")
    import json
    import sys
    print(json.dumps(hook(sys.argv[1])))
