"""
Request validation module.

BUG A: EMAIL_RE is too permissive — matches "user@nodomain" (no TLD required).
       Fix: use a strict pattern requiring a dot-separated TLD.

BUG B: REQUIRED_FIELDS is missing "email".
       Fix: add "email" to the set.

Both bugs are independent.
"""

import re

# BUG: too permissive — allows any non-@ chars on both sides; no TLD required
EMAIL_RE = re.compile(r"[^@]+@[^@]+")

# BUG: "email" missing from required fields
REQUIRED_FIELDS = ["username", "password"]


def validate_email(email: str) -> bool:
    return bool(EMAIL_RE.fullmatch(email)) if email else False


def validate_request(data: dict) -> list:
    """Return a list of validation error strings (empty means valid)."""
    errors = []
    for field in REQUIRED_FIELDS:
        if not data.get(field):
            errors.append(f"missing required field: {field}")
    if "email" in data:
        if not validate_email(data["email"]):
            errors.append("invalid email format")
    return errors
