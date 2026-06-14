"""Reference (correct) implementation — never shown to LLM mutator."""

import hashlib
import hmac
import json
import time

_SECRET = "tdes-repair-2024"


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def create_token(user_id: int, role: str, ttl: int = 3600) -> str:
    payload = {"sub": user_id, "role": role, "exp": int(time.time()) + ttl}
    data = json.dumps(payload, sort_keys=True)
    sig = hmac.new(_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}||{sig}"


def validate_token(token: str) -> dict:
    """Validate token signature and expiry; return payload or raise AuthError."""
    try:
        data_part, sig = token.rsplit("||", 1)
        expected = hmac.new(_SECRET.encode(), data_part.encode(), hashlib.sha256).hexdigest()
        if sig != expected:
            raise AuthError("invalid signature")
        payload = json.loads(data_part)
        if payload.get("exp", 0) < time.time():
            raise AuthError("token expired")
        return payload
    except AuthError:
        raise
    except Exception:
        raise AuthError("malformed token")
