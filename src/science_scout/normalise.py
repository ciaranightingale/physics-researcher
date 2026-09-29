"""Pure helpers: no I/O, so everything here is deterministic and easy to test."""

import html
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

_TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|mc_cid|mc_eid|ref|rss)$", re.I)


def canonical_url(raw: str) -> str:
    """Canonical form of a URL, so the same story always gets the same key."""
    try:
        parts = urlsplit(raw.strip())
        host = (parts.hostname or "").lower().removeprefix("www.")
        if not host:
            return raw.strip()
        query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k))
        path = parts.path.rstrip("/") if len(parts.path) > 1 else parts.path
        return urlunsplit(("https", host, path, urlencode(query), ""))
    except ValueError:
        return raw.strip()


# ---------------------------------------------------------------------------
# Identifiers: DOIs and arXiv IDs are how we know two stories are about the same paper.
# ---------------------------------------------------------------------------

_ARXIV_URL = re.compile(r"arxiv\.org/(?:abs|pdf|html)/((?:[a-z\-]+(?:\.[a-z]{2})?/\d{7})|\d{4}\.\d{4,5})(?:v\d+)?", re.I)
_ARXIV_TEXT = re.compile(r"\barxiv:\s?(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>?#]+)", re.I)
_NATURE_ARTICLE = re.compile(r"nature\.com/articles/([a-z]+\d[a-z0-9.\-]*)", re.I)
_DOI_TRAILING = re.compile(r"(/(?:full|abstract|pdf|epdf|meta))+$|[.,;:)\]}]+$", re.I)
_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$", re.I)


def extract_identifiers(text: str) -> list[str]:
    """Finds DOIs and arXiv IDs in a URL or text, in order of appearance, without duplicates.

    Returns keys like "doi:10.1038/s41567-026-00001-x" and "arxiv:2609.04567" (version-less).
    """
    text = unquote(html.unescape(text))
    found: list[tuple[int, str]] = []
    for m in _ARXIV_URL.finditer(text):
        found.append((m.start(), f"arxiv:{m.group(1).lower()}"))
    for m in _ARXIV_TEXT.finditer(text):
        found.append((m.start(), f"arxiv:{m.group(1)}"))
    for m in _NATURE_ARTICLE.finditer(text):
        # Nature article slugs are the DOI suffix: nature.com/articles/s41567-... == doi:10.1038/s41567-...
        found.append((m.start(), f"doi:10.1038/{m.group(1).lower()}"))
    for m in _DOI.finditer(text):
        doi = m.group(1)
        while True:
            cleaned = _DOI_TRAILING.sub("", doi)
            if cleaned == doi:
                break
            doi = cleaned
        arxiv = _ARXIV_DOI.match(doi)
        found.append((m.start(), f"arxiv:{arxiv.group(1)}" if arxiv else f"doi:{doi.lower()}"))

    seen: set[str] = set()
    out: list[str] = []
    for _, ident in sorted(found, key=lambda f: f[0]):
        if ident not in seen:
            seen.add(ident)
            out.append(ident)
    return out


def arxiv_id_from_url(url: str) -> str | None:
    m = _ARXIV_URL.search(url)
    return m.group(1).lower() if m else None


def item_key(url: str) -> str:
    """Key for one link: `arxiv:<id>` for arXiv (so abs/pdf/versions all match), else `url:<canonical url>`."""
    arxiv = arxiv_id_from_url(url)
    return f"arxiv:{arxiv}" if arxiv else f"url:{canonical_url(url)}"


def is_identifier(key: str) -> bool:
    return bool(re.fullmatch(r"doi:10\.\d{4,9}/\S+|arxiv:\S+", key))


# ---------------------------------------------------------------------------
# Text and dates
# ---------------------------------------------------------------------------

def plain_text(raw: str, max_chars: int = 300) -> str:
    """Strips HTML, decodes entities, collapses whitespace and truncates on a word boundary."""
    s = re.sub(r"<[^>]*>", " ", raw or "")
    s = re.sub(r"\s+", " ", html.unescape(s)).strip()
    if len(s) <= max_chars:
        return s
    cut = s[:max_chars]
    space = cut.rfind(" ")
    return (cut[:space] if space > max_chars * 0.6 else cut) + "\u2026"


def struct_to_iso(t: time.struct_time | None) -> str | None:
    """feedparser gives UTC struct_time; we want ISO 8601."""
    if not t:
        return None
    return datetime(*t[:6], tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def within_days(iso: str, days: int, now: datetime) -> bool:
    age = now - parse_iso(iso)
    return timedelta(days=-1) <= age <= timedelta(days=days)  # a day of slack for future-dated items


def days_since(iso: str, now: datetime) -> int:
    """Whole days between an ISO timestamp and now (0 if it's in the future)."""
    return max(0, (now - parse_iso(iso)).days)


def iso_now(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Headline similarity (the fallback when stories don't share a paper link)
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    """a an the and or but of in on at to for from by with into onto over under about as is are was were be been being
    it its this that these those than then there their they them we our you your he she his her not no yes can could may
    might will would should shall do does did has have had how why what when where who which new study studies research
    researchers scientists physicists team teams finds find found reveal reveals revealed show shows shown suggests
    first ever yet just now more most less very way ways help helps make makes made say says said could here after
    before up down out one two""".split()
)


def headline_tokens(title: str) -> frozenset[str]:
    """Content words of a headline, lower-cased, with simple plural folding."""
    words = re.findall(r"[a-z0-9]+", html.unescape(title).lower())
    out = set()
    for w in words:
        if w in _STOPWORDS or (len(w) < 3 and not w.isdigit()):
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return frozenset(out)


def headline_overlap(a: frozenset[str], b: frozenset[str]) -> tuple[float, frozenset[str]]:
    """Overlap coefficient: shared words / size of the smaller headline."""
    if not a or not b:
        return 0.0, frozenset()
    shared = a & b
    return len(shared) / min(len(a), len(b)), shared
