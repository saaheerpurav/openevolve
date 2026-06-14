"""Reference (correct) implementation — never shown to LLM mutator."""

ROUTES = {
    "GET /users": "list_users",
    "POST /users": "create_user",
    "GET /users/<id>": "get_user",
    "DELETE /users/<id>": "delete_user",
}


def _normalize_path(path: str) -> str:
    parts = path.rstrip("/").split("/")
    return "/" + "/".join("<id>" if p.isdigit() else p for p in parts if p)


def resolve(method: str, path: str) -> str:
    normalized = _normalize_path(path)
    key = f"{method.upper()} {normalized}"
    if key in ROUTES:
        return ROUTES[key]
    raise ValueError(f"No handler for {method} {path}")
