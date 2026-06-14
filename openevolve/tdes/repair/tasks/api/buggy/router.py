"""
HTTP request router.

BUG A: resolve() lowercases the method before building the lookup key, but
       ROUTES keys use uppercase — so every lookup misses.
       Fix: use method.upper().

BUG B: "GET /users/<id>" route is missing from ROUTES.
       Fix: add the entry pointing to "get_user".

Both bugs are independent.
"""

ROUTES = {
    "GET /users": "list_users",
    "POST /users": "create_user",
    # BUG: "GET /users/<id>" entry is missing
    "DELETE /users/<id>": "delete_user",
}


def _normalize_path(path: str) -> str:
    """Replace numeric path segments with the <id> placeholder."""
    parts = path.rstrip("/").split("/")
    return "/" + "/".join("<id>" if p.isdigit() else p for p in parts if p)


def resolve(method: str, path: str) -> str:
    """Return the handler name for a given HTTP method and path."""
    normalized = _normalize_path(path)
    key = f"{method.lower()} {normalized}"    # BUG: lowercase; keys are uppercase
    if key in ROUTES:
        return ROUTES[key]
    raise ValueError(f"No handler for {method} {path}")
