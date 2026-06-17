"""Auth module: bearer-token parsing, scope grants, and request throttling.

Tokens arrive as ``"Bearer <user>|<scope1+scope2+...>|<exp>"``. A scope may
imply further scopes (see ``IMPLIES``) and a leading ``!`` marks a denial.
Expired tokens get a short grace period. ``throttle`` keeps a per-user
sliding window of request timestamps. ``authenticate`` ties everything
together and returns ``(ok, reason)`` with reason one of ``"no_token"``,
``"expired"``, ``"throttled"``, ``"forbidden"``, or ``None`` on success.
"""

_PREFIX = "Bearer "

GRACE = 30  # ticks after expiry during which a token is in its grace period
LIMIT = 3  # requests allowed per sliding window
WINDOW = 10  # sliding-window length in ticks

IMPLIES = {
    "admin": ("write", "audit"),
    "write": ("read",),
    "audit": ("read", "metrics"),
}


def parse_token(header):
    """Parse a bearer header into ``{"user", "scopes", "exp"}`` (or None)."""
    if not isinstance(header, str) or not header.startswith(_PREFIX):
        return None
    parts = header[len(_PREFIX) :].split("|")
    if len(parts) != 3:
        return None
    user, scope_text, exp_text = parts
    if not user:
        return None
    scopes = [s for s in scope_text.split("+") if s]
    if not scopes:
        return None
    try:
        exp = int(exp_text)
    except ValueError:
        return None
    return {"user": user, "scopes": scopes, "exp": exp}


def grants(scopes):
    """The set of scopes a declared scope list actually grants."""
    denied = set()
    pending = []
    for scope in scopes:
        if scope.startswith("!"):
            denied.add(scope[1:])
        else:
            pending.append(scope)
    pending = [scope for scope in pending if scope not in denied]
    granted = set()
    while pending:
        scope = pending.pop()
        if scope in granted:
            continue
        granted.add(scope)
        pending.extend(IMPLIES.get(scope, ()))
    return granted


def token_state(token, now):
    """Classify a token's lifecycle stage at ``now``."""
    if now < token["exp"]:
        return "active"
    if now < token["exp"] + GRACE:
        return "grace"
    return "expired"


def effective_grants(token, now):
    """The scopes a token may exercise at ``now``."""
    state = token_state(token, now)
    if state == "expired":
        return set()
    granted = grants(token["scopes"])
    if state == "grace":
        granted = granted & {"read"}
    return granted


def throttle(history, user, now):
    """Per-user sliding-window rate limit; returns ``(allowed, retry_after)``."""
    bucket = [t for t in history.get(user, []) if t > now - WINDOW]
    bucket.append(now)
    history[user] = bucket
    if len(bucket) > LIMIT:
        return False, bucket[0] + WINDOW - now
    return True, 0


def authenticate(header, now, required_scope=None, history=None):
    """Authenticate a request; ``(True, None)`` or ``(False, reason)``."""
    token = parse_token(header)
    if token is None:
        return False, "no_token"
    state = token_state(token, now)
    if state == "expired":
        return False, "expired"
    if history is not None:
        allowed, _retry = throttle(history, token["user"], now)
        if not allowed:
            return False, "throttled"
    if required_scope is not None and required_scope not in effective_grants(token, now):
        return False, ("expired" if state == "grace" else "forbidden")
    return True, None
