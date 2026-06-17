"""Regenerate the buggy module files from the references (dev helper).

Each planted bug is a small, realistic edit applied to the reference source;
docstrings and everything else stay byte-identical. Run from anywhere:

    python -m openevolve.tdes.repair.benchmarks.api._make_buggy
"""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))

U1 = (
    """    bucket = [t for t in history.get(user, []) if t > now - WINDOW]
    if len(bucket) >= LIMIT:
        history[user] = bucket
        return False, bucket[0] + WINDOW - now
    bucket.append(now)
    history[user] = bucket
    return True, 0
""",
    """    bucket = [t for t in history.get(user, []) if t > now - WINDOW]
    bucket.append(now)
    history[user] = bucket
    if len(bucket) > LIMIT:
        return False, bucket[0] + WINDOW - now
    return True, 0
""",
)

U2 = (
    """    granted = set()
    while pending:
        scope = pending.pop()
        if scope in granted:
            continue
        granted.add(scope)
        pending.extend(IMPLIES.get(scope, ()))
    return granted - denied
""",
    """    pending = [scope for scope in pending if scope not in denied]
    granted = set()
    while pending:
        scope = pending.pop()
        if scope in granted:
            continue
        granted.add(scope)
        pending.extend(IMPLIES.get(scope, ()))
    return granted
""",
)

R1 = (
    "    return tuple(_RANKS[kind] for kind, _ in compiled)\n",
    "    return sum(_RANKS[kind] for kind, _ in compiled)\n",
)

R2 = (
    """    segments = split_path(path)
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
""",
    """    segments = split_path(path)
    if method == "HEAD":
        method = "GET"
    found = candidates(routes, segments)
    if not found:
        return 404, None, {}
    for _prec, route_method, handler, params in found:
        if route_method == method:
            return 200, handler, params
    allow = sorted({route_method for _prec, route_method, _h, _p in found})
""",
)

V1 = (
    "    errors.extend(check_rules(coerced, rules))\n",
    "    errors.extend(check_rules(payload, rules))\n",
)

V2 = (
    """        ok, value = coerce(value, spec.get("kind"))
        if not ok:
            errors.append(path + ": not a " + str(spec.get("kind")))
            continue
""",
    """        ok, value = coerce(value, spec.get("kind"))
        if not ok:
            errors.append(path + ": not a " + str(spec.get("kind")))
            return errors, coerced
""",
)

FILES = {
    "auth_u1.py": ("auth", [U1]),
    "auth_u2.py": ("auth", [U2]),
    "auth_u1_u2.py": ("auth", [U1, U2]),
    "router_r1.py": ("router", [R1]),
    "router_r2.py": ("router", [R2]),
    "validator_v1.py": ("validator", [V1]),
    "validator_v2.py": ("validator", [V2]),
    "validator_v1_v2.py": ("validator", [V1, V2]),
}


def main():
    for fname, (module, edits) in FILES.items():
        with open(os.path.join(_HERE, "reference", module + ".py"), encoding="utf-8") as f:
            source = f.read()
        for search, replace in edits:
            if search not in source:
                raise SystemExit(f"{fname}: edit anchor not found in reference {module}.py")
            source = source.replace(search, replace)
        with open(os.path.join(_HERE, "buggy", fname), "w", encoding="utf-8") as f:
            f.write(source)
        print("wrote", fname)


if __name__ == "__main__":
    main()
