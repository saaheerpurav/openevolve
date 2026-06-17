"""Router module: pattern compilation, precedence, and method dispatch.

Patterns are ``/``-separated. A ``{name}`` segment binds one path segment,
``{name:int}`` binds a decimal segment as an int, and ``*`` matches one
segment without binding. ``dispatch(routes, method, path)`` resolves a
request against ``(method, pattern, handler)`` triples and returns
``(status, handler, extra)``: ``(200, handler, params)`` on a match,
``(405, None, {"allow": [...]})`` when the path exists under other methods,
and ``(404, None, {})`` otherwise.
"""

_RANKS = {"lit": 3, "int": 2, "param": 1, "wild": 0}


def split_path(path):
    """Path string -> list of segments (query string and fragment dropped)."""
    for sep in ("?", "#"):
        path = path.split(sep, 1)[0]
    return [seg for seg in path.split("/") if seg]


def compile_pattern(pattern):
    """Pattern string -> list of ``(kind, value)`` segment matchers."""
    compiled = []
    for seg in split_path(pattern):
        if seg == "*":
            compiled.append(("wild", None))
        elif seg.startswith("{") and seg.endswith("}"):
            name = seg[1:-1]
            if name.endswith(":int"):
                compiled.append(("int", name[: -len(":int")]))
            else:
                compiled.append(("param", name))
        else:
            compiled.append(("lit", seg))
    return compiled


def match_pattern(compiled, segments):
    """Match compiled segments against a path -> params dict or None."""
    if len(compiled) != len(segments):
        return None
    params = {}
    for (kind, value), seg in zip(compiled, segments):
        if kind == "lit":
            if seg != value:
                return None
        elif kind == "int":
            if not seg.isdigit():
                return None
            params[value] = int(seg)
        elif kind == "param":
            params[value] = seg
        # a "wild" segment matches anything and binds nothing
    return params


def precedence(compiled):
    """Sort key ranking a compiled pattern for overlap resolution."""
    return tuple(_RANKS[kind] for kind, _ in compiled)


def candidates(routes, segments):
    """All routes whose pattern matches ``segments``, best precedence first."""
    found = []
    for method, pattern, handler in routes:
        compiled = compile_pattern(pattern)
        params = match_pattern(compiled, segments)
        if params is not None:
            found.append((precedence(compiled), method, handler, params))
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def dispatch(routes, method, path):
    """Resolve a request to ``(status, handler, extra)``."""
    segments = split_path(path)
    found = candidates(routes, segments)
    if not found:
        return 404, None, {}
    for _prec, route_method, handler, params in found:
        if route_method == method:
            return 200, handler, params
    if method == "HEAD":
        for _prec, route_method, handler, params in found:
            if route_method == "GET":
                return 200, handler, params
    allow = sorted({route_method for _prec, route_method, _h, _p in found})
    return 405, None, {"allow": allow}
