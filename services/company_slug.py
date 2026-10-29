"""Shared company-slug logic — used by both the admin Companies CRUD
(routers/companies.py, where a slug is auto-derived from the name an admin
types) and the referral-link auto-detection flow (main.py's /register,
where the slug itself is the input). Keeping this in one place means the
normalization rule can never drift between the two call sites."""
import re

_DISALLOWED_RUN = re.compile(r"[^a-z0-9]+")

MAX_SLUG_LENGTH = 100


def normalize_company_slug(raw: str | None) -> str:
    """Lowercases, trims, and collapses any run of non-alphanumeric
    characters into a single '-', with leading/trailing '-' stripped.
    Returns "" if nothing usable is left (caller's responsibility to reject
    that as invalid input)."""
    if not raw:
        return ""
    slug = _DISALLOWED_RUN.sub("-", raw.strip().lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH]


def slug_to_display_name(slug: str) -> str:
    """A reasonable human-readable name for a company auto-created from a
    slug alone (no display name was ever typed by a person) — e.g.
    "test-life" -> "Test Life". Purely cosmetic; the slug itself, not this
    name, is what every future lookup matches on."""
    return " ".join(word.capitalize() for word in slug.split("-") if word)
