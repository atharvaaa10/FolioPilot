"""Pure utilities for normalizing, escaping, and classifying fund search queries."""

import re
from dataclasses import dataclass

from app.services.fund_classification import normalize_name


@dataclass(frozen=True)
class ParsedSearchQuery:
    """Classified search query representation."""

    raw_query: str
    is_scheme_code: bool
    is_isin: bool
    scheme_code: int | None
    isin: str | None
    tokens: list[str]


_ISIN_RE = re.compile(r"^[A-Za-z]{2}[A-Za-z0-9]{10}$")


def escape_like_wildcards(text: str) -> str:
    """Escape SQL LIKE wildcard characters so user input % and _ are treated literally.

    Backslash is escaped first, followed by % and _.
    """
    escaped = text.replace("\\", "\\\\")
    escaped = escaped.replace("%", "\\%")
    escaped = escaped.replace("_", "\\_")
    return escaped


def is_scheme_code_query(text: str) -> bool:
    """Return True if query consists entirely of digits."""
    cleaned = text.strip()
    return bool(cleaned and cleaned.isdigit())


def is_isin_query(text: str) -> bool:
    """Return True if query matches 12-character alphanumeric ISIN format."""
    cleaned = text.strip()
    return bool(_ISIN_RE.match(cleaned))


def parse_search_query(query: str) -> ParsedSearchQuery:
    """Parse search query into structured tokens and query classification."""
    cleaned = query.strip()
    if not cleaned:
        return ParsedSearchQuery(
            raw_query="",
            is_scheme_code=False,
            is_isin=False,
            scheme_code=None,
            isin=None,
            tokens=[],
        )

    if is_scheme_code_query(cleaned):
        try:
            code = int(cleaned)
            return ParsedSearchQuery(
                raw_query=cleaned,
                is_scheme_code=True,
                is_isin=False,
                scheme_code=code,
                isin=None,
                tokens=[cleaned],
            )
        except ValueError:
            pass

    if is_isin_query(cleaned):
        return ParsedSearchQuery(
            raw_query=cleaned,
            is_scheme_code=False,
            is_isin=True,
            scheme_code=None,
            isin=cleaned.upper(),
            tokens=[cleaned.lower()],
        )

    normalized = normalize_name(cleaned)
    tokens = [t for t in normalized.split() if t]

    return ParsedSearchQuery(
        raw_query=cleaned,
        is_scheme_code=False,
        is_isin=False,
        scheme_code=None,
        isin=None,
        tokens=tokens,
    )
