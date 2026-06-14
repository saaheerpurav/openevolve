"""Reference (correct) implementation — never shown to LLM mutator."""

import re

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

REQUIRED_FIELDS = ["email", "password", "username"]


def validate_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email)) if email else False


def validate_request(data: dict) -> list:
    errors = []
    for field in REQUIRED_FIELDS:
        if not data.get(field):
            errors.append(f"missing required field: {field}")
    if "email" in data:
        if not validate_email(data["email"]):
            errors.append("invalid email format")
    return errors
