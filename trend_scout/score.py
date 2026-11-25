"""Scoring. Pure functions, no I/O, so they're easy to test and to reason about."""
import re
import statistics

INTENT = re.compile(r"\b(how (do|did|does|can|to)|tutorial|need this|link|where (did|do|can|is)|what (app|brand|shoes|watch)|"
                    r"which (one|app|brand)|save(d)? this|sauce)\b|(^|\s)@\w", re.I)


GIVEAWAY = re.compile(r"\b(giveaway|give away|contest|sweepstakes?|enter to win|chance to win|win (a|an|2|two)\b|concurso|sorteo|"
                      r"gana[rs]?\b|tag (a|\d+|two|three) friends? to)|\b(gewinnspiel|concours)\b", re.I)


def is_giveaway(text: str | None) -> bool:
    """Contests and giveaways rack up comments from entries, not interest: leave them out of trends."""
    return bool(text and GIVEAWAY.search(text))


def velocity(likes: float, comments: float = 0, shares: float = 0, hours: float = 1.0) -> float:
    """(shares*3 + comments*2 + likes) / hours^1.5. Newer posts with the same engagement score higher."""
    return round((shares * 3 + comments * 2 + likes) / max(hours, 1.0) ** 1.5, 3)


def outlier_ratio(views: float | None, subscribers: float | None) -> float | None:
    """Views per subscriber. None when either is unknown (hidden subscriber counts), never a guess."""
    if not views or not subscribers:
        return None
    return round(views / subscribers, 2)


def intent_ratio(comments: list[str]) -> float | None:
    """Share of comments asking how/where/which or tagging a friend. None with no comments."""
    if not comments:
        return None
    return round(sum(1 for c in comments if INTENT.search(c or "")) / len(comments), 2)


def median_outliers(values: list[float], factor: float = 3.0) -> list[int]:
    """Indexes of values at factor x the median or more (for an account's own posts)."""
    vals = [v for v in values if v is not None]
    if len(vals) < 3:
        return []
    med = statistics.median(vals)
    if med <= 0:
        return []
    return [i for i, v in enumerate(values) if v is not None and v >= factor * med]


def rank_norm(items: list[dict], key: str) -> None:
    """Adds item['rank_score'] in 0..1 within one source (1 = best), so sources can be interleaved fairly."""
    ordered = sorted(items, key=lambda x: x.get(key) or 0, reverse=True)
    n = len(ordered)
    for i, it in enumerate(ordered):
        it["rank_score"] = round(1 - i / n, 3) if n else 0
